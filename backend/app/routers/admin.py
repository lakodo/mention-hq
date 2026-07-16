from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Item, SourceInstance
from app.schemas import (
    AIKeyUpdate,
    AIStatusOut,
    AppSettingsOut,
    AppSettingsPatch,
    ConfigFieldOut,
    DetectionOut,
    SourceConfigUpdate,
    SourceCreate,
    SourceKindOut,
    SourcePatch,
    SourceStatusOut,
)
from app.security import get_secret_store
from app.services import ai
from app.services.app_config import get_app_name, set_app_name, set_value
from app.services.sources_factory import (
    BY_KIND,
    SOURCE_CLASSES,
    Connected,
    build_connected,
    new_instance_id,
    resolve_config,
)
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


@router.get("/source-kinds", response_model=list[SourceKindOut])
async def list_source_kinds() -> list[SourceKindOut]:
    """What you can connect. The Add-a-source picker is built from this."""
    return [
        SourceKindOut(
            kind=cls.id,
            name=cls.name,
            description=cls.description,
            setup=cls.setup,
            setup_url=cls.setup_url,
            manifest=cls.manifest,
            manifest_hint=cls.manifest_hint,
            detectable=_can_detect(cls),
            needs_credentials=any(f.kind == "secret" for f in cls.fields),
        )
        for cls in SOURCE_CLASSES
    ]


@router.get("/sources", response_model=list[SourceStatusOut])
async def list_sources(db: AsyncSession = Depends(get_db)) -> list[SourceStatusOut]:
    connected = await build_connected(db)
    return list(await asyncio.gather(*(_status(c) for c in connected)))


@router.post("/sources", response_model=SourceStatusOut, status_code=201)
async def add_source(payload: SourceCreate, db: AsyncSession = Depends(get_db)) -> SourceStatusOut:
    source_class = BY_KIND.get(payload.kind)
    if source_class is None:
        raise HTTPException(status_code=400, detail=f"Unknown kind: {payload.kind}")

    name = payload.name.strip() or source_class.name
    instance_id = new_instance_id(payload.kind, name)
    if await db.get(SourceInstance, instance_id) is not None:
        raise HTTPException(status_code=409, detail=f"You already have a source called {name}")

    highest = (await db.execute(select(SourceInstance.position))).scalars().all()
    instance = SourceInstance(
        id=instance_id, kind=payload.kind, name=name, position=(max(highest, default=0) + 1)
    )
    db.add(instance)
    await db.commit()

    return await _status(Connected(instance=instance, source=source_class({})))


@router.patch("/sources/{instance_id}", response_model=SourceStatusOut)
async def rename_source(
    instance_id: str, payload: SourcePatch, db: AsyncSession = Depends(get_db)
) -> SourceStatusOut:
    instance = await _require(db, instance_id)
    if payload.name is not None and payload.name.strip():
        instance.name = payload.name.strip()
    if payload.position is not None:
        instance.position = payload.position
    await db.commit()
    return await _status(await _connected(db, instance_id))


@router.delete("/sources/{instance_id}", status_code=204)
async def remove_source(instance_id: str, db: AsyncSession = Depends(get_db)) -> None:
    instance = await _require(db, instance_id)
    source_class = BY_KIND[instance.kind]

    secrets = get_secret_store()
    for spec in source_class.fields:
        if spec.kind == "secret":
            secrets.delete(instance_id, spec.key)
        else:
            await set_value(db, instance_id, spec.key, None)

    # Items outlive the connection: they may be attached to tasks the user cares about,
    # and the next sync drops them once nothing fetches them.
    for item in (await db.execute(select(Item).where(Item.instance_id == instance_id))).scalars().all():
        item.instance_id = None

    await db.delete(instance)
    await db.commit()


@router.post("/sources/{instance_id}/test", response_model=SourceStatusOut)
async def test_source(instance_id: str, db: AsyncSession = Depends(get_db)) -> SourceStatusOut:
    return await _status(await _connected(db, instance_id))


@router.post("/sources/{instance_id}/detect", response_model=DetectionOut)
async def detect_source(instance_id: str, db: AsyncSession = Depends(get_db)) -> DetectionOut:
    """Fill in what a local CLI already knows.

    A detected secret goes straight to the keychain: it is never sent to the browser, so
    reading it back out of HQ is no easier than reading it out of the CLI it came from.
    """
    instance = await _require(db, instance_id)
    source_class = BY_KIND[instance.kind]

    detection = await source_class.detect()
    if not detection.available:
        return DetectionOut(available=False, detail=detection.detail)

    secrets = get_secret_store()
    secret_keys = {f.key for f in source_class.fields if f.kind == "secret"}
    applied: dict[str, str] = {}

    for key, value in detection.values.items():
        if key in secret_keys:
            secrets.set(instance_id, key, value)
            applied[key] = "saved"
        else:
            await set_value(db, instance_id, key, value)
            applied[key] = value
    await db.commit()

    return DetectionOut(
        available=True,
        detail=detection.detail,
        applied=applied,
        choices=detection.choices,
        source=await _status(await _connected(db, instance_id)),
    )


@router.put("/sources/{instance_id}/config", response_model=SourceStatusOut)
async def update_source_config(
    instance_id: str, update: SourceConfigUpdate, db: AsyncSession = Depends(get_db)
) -> SourceStatusOut:
    instance = await _require(db, instance_id)
    known = {spec.key: spec for spec in BY_KIND[instance.kind].fields}
    secrets = get_secret_store()

    for key, value in update.values.items():
        spec = known.get(key)
        if spec is None:
            raise HTTPException(status_code=400, detail=f"Unknown field: {key}")
        if spec.kind == "secret":
            # Straight to the keychain; a secret must never reach the DB or a log line.
            if value:
                secrets.set(instance_id, key, value)
            else:
                secrets.delete(instance_id, key)
        else:
            await set_value(db, instance_id, key, value)

    await db.commit()
    return await _status(await _connected(db, instance_id))


async def _require(db: AsyncSession, instance_id: str) -> SourceInstance:
    instance = await db.get(SourceInstance, instance_id)
    if instance is None or instance.kind not in BY_KIND:
        raise HTTPException(status_code=404, detail=f"No source: {instance_id}")
    return instance


async def _connected(db: AsyncSession, instance_id: str) -> Connected:
    instance = await _require(db, instance_id)
    return Connected(instance=instance, source=BY_KIND[instance.kind](await resolve_config(db, instance)))


def _can_detect(source_class: type[Source]) -> bool:
    # __func__, because accessing a classmethod builds a new bound method every time and
    # `is not` between two of those is always true.
    return source_class.detect.__func__ is not Source.detect.__func__


async def _status(connected: Connected) -> SourceStatusOut:
    instance, source = connected.instance, connected.source
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
                secrets.hint(instance.id, spec.key) if spec.kind == "secret" else source.get(spec.key) or None
            ),
            is_set=bool(source.get(spec.key)),
        )
        for spec in source.fields
    ]

    return SourceStatusOut(
        id=instance.id,
        kind=instance.kind,
        name=instance.name,
        position=instance.position,
        description=source.description,
        status=status,
        detail=source.detail(),
        last_checked_at=datetime.now(UTC) if configured else None,
        error=error,
        fields=fields,
        setup=source.setup,
        setup_url=source.setup_url,
        manifest=source.manifest,
        manifest_hint=source.manifest_hint,
        detectable=_can_detect(type(source)),
    )
