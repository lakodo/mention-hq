from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import (
    AIKeyUpdate,
    AIStatusOut,
    AppSettingsOut,
    AppSettingsPatch,
    ConfigFieldOut,
    DetectionOut,
    SourceConfigUpdate,
    SourceStatusOut,
)
from app.security import get_secret_store
from app.services import ai
from app.services.app_config import get_app_name, set_app_name, set_value
from app.services.sources_factory import SOURCE_CLASSES, resolve_config, source_class_by_id
from app.sources.base import Source

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/settings", response_model=AppSettingsOut)
async def get_settings_(db: AsyncSession = Depends(get_db)) -> AppSettingsOut:
    store = get_secret_store()
    return AppSettingsOut(
        app_name=await get_app_name(db),
        secret_backend=store.backend_name,
        secret_backend_is_keychain=store.is_keychain,
    )


@router.patch("/settings", response_model=AppSettingsOut)
async def patch_settings(patch: AppSettingsPatch, db: AsyncSession = Depends(get_db)) -> AppSettingsOut:
    if patch.app_name is not None:
        await set_app_name(db, patch.app_name)
        await db.commit()
    return await get_settings_(db)


@router.get("/ai", response_model=AIStatusOut)
async def ai_status() -> AIStatusOut:
    current = ai.status()
    return AIStatusOut(
        available=current.available, source=current.source, detail=current.detail, model=ai.MODEL
    )


@router.put("/ai/key", response_model=AIStatusOut)
async def set_ai_key(update: AIKeyUpdate) -> AIStatusOut:
    store = get_secret_store()
    if update.api_key:
        store.set(ai.SECRET_NAMESPACE, "api_key", update.api_key)
    else:
        # Clearing falls back to `ant auth login` or the environment, which is the
        # better setup on a machine that has one — so this is a real choice, not a reset.
        store.delete(ai.SECRET_NAMESPACE, "api_key")
    return await ai_status()


@router.get("/sources", response_model=list[SourceStatusOut])
async def list_sources(db: AsyncSession = Depends(get_db)) -> list[SourceStatusOut]:
    built = [(cls, cls(await resolve_config(db, cls))) for cls in SOURCE_CLASSES]
    return list(await asyncio.gather(*(_status(source) for _, source in built)))


@router.post("/sources/{source_id}/test", response_model=SourceStatusOut)
async def test_source(source_id: str, db: AsyncSession = Depends(get_db)) -> SourceStatusOut:
    source = await _build(db, source_id)
    return await _status(source)


@router.post("/sources/{source_id}/detect", response_model=DetectionOut)
async def detect_source(source_id: str, db: AsyncSession = Depends(get_db)) -> DetectionOut:
    """Fill in what a local CLI already knows.

    A detected secret goes straight to the keychain: it is never sent to the browser, so
    reading it back out of HQ is no easier than reading it out of the CLI it came from.
    """
    source_class = source_class_by_id(source_id)
    if source_class is None:
        raise HTTPException(status_code=404, detail=f"Unknown source: {source_id}")

    detection = await source_class.detect()
    if not detection.available:
        return DetectionOut(available=False, detail=detection.detail)

    secrets = get_secret_store()
    secret_keys = {f.key for f in source_class.fields if f.kind == "secret"}
    applied: dict[str, str] = {}

    for key, value in detection.values.items():
        if key in secret_keys:
            secrets.set(source_id, key, value)
            applied[key] = "saved"
        else:
            await set_value(db, source_id, key, value)
            applied[key] = value
    await db.commit()

    return DetectionOut(
        available=True,
        detail=detection.detail,
        applied=applied,
        choices=detection.choices,
        source=await _status(await _build(db, source_id)),
    )


@router.put("/sources/{source_id}/config", response_model=SourceStatusOut)
async def update_source_config(
    source_id: str, update: SourceConfigUpdate, db: AsyncSession = Depends(get_db)
) -> SourceStatusOut:
    source_class = source_class_by_id(source_id)
    if source_class is None:
        raise HTTPException(status_code=404, detail=f"Unknown source: {source_id}")

    known = {spec.key: spec for spec in source_class.fields}
    secrets = get_secret_store()

    for key, value in update.values.items():
        spec = known.get(key)
        if spec is None:
            raise HTTPException(status_code=400, detail=f"Unknown field: {key}")
        if spec.kind == "secret":
            # Straight to the keychain; a secret must never reach the DB or a log line.
            if value:
                secrets.set(source_id, key, value)
            else:
                secrets.delete(source_id, key)
        else:
            await set_value(db, source_id, key, value)

    await db.commit()
    return await _status(await _build(db, source_id))


@router.delete("/sources/{source_id}/config", response_model=SourceStatusOut)
async def clear_source_config(source_id: str, db: AsyncSession = Depends(get_db)) -> SourceStatusOut:
    source_class = source_class_by_id(source_id)
    if source_class is None:
        raise HTTPException(status_code=404, detail=f"Unknown source: {source_id}")

    secrets = get_secret_store()
    for spec in source_class.fields:
        if spec.kind == "secret":
            secrets.delete(source_id, spec.key)
        else:
            await set_value(db, source_id, spec.key, None)

    await db.commit()
    return await _status(await _build(db, source_id))


async def _build(db: AsyncSession, source_id: str) -> Source:
    source_class = source_class_by_id(source_id)
    if source_class is None:
        raise HTTPException(status_code=404, detail=f"Unknown source: {source_id}")
    return source_class(await resolve_config(db, source_class))


async def _status(source: Source) -> SourceStatusOut:
    configured = source.is_configured()
    error: str | None = None
    if configured:
        try:
            await source.check()
        except Exception as exc:
            error = str(exc)

    if not configured:
        status = "unconfigured"
    elif error:
        status = "error"
    else:
        status = "connected"

    secrets = get_secret_store()
    fields = [
        ConfigFieldOut(
            key=spec.key,
            label=spec.label,
            kind=spec.kind,
            required=spec.required,
            placeholder=spec.placeholder,
            help=spec.help,
            help_url=spec.help_url,
            value=(
                secrets.hint(source.id, spec.key) if spec.kind == "secret" else source.get(spec.key) or None
            ),
            is_set=bool(source.get(spec.key)),
        )
        for spec in source.fields
    ]

    return SourceStatusOut(
        id=source.id,
        name=source.name,
        description=source.description,
        status=status,
        detail=source.detail(),
        last_checked_at=datetime.now(UTC) if configured else None,
        error=error,
        fields=fields,
        setup=source.setup,
        setup_url=source.setup_url,
        detectable=_can_detect(type(source)),
    )


def _can_detect(source_class: type[Source]) -> bool:
    # __func__, because accessing a classmethod builds a new bound method every time and
    # `is not` between two of those is always true.
    return source_class.detect.__func__ is not Source.detect.__func__
