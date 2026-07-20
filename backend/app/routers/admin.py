from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path
from secrets import token_urlsafe

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.models import Item, SourceInstance
from app.schemas import (
    AIKeyUpdate,
    AIStatusOut,
    AppSettingsOut,
    AppSettingsPatch,
    BackupOut,
    BrowseEntryOut,
    BrowseOut,
    ConfigFieldOut,
    DetectionOut,
    NotionAuthorizeOut,
    NotionOAuthOut,
    SourceConfigUpdate,
    SourceCreate,
    SourceKindOut,
    SourcePatch,
    SourceStatusOut,
)
from app.security import get_secret_store
from app.services import ai
from app.services.app_config import (
    get_app_name,
    get_auto_sync,
    get_value,
    set_app_name,
    set_auto_sync,
    set_value,
)
from app.services.backup import backup_database
from app.services.sources_factory import (
    BY_KIND,
    SOURCE_CLASSES,
    Connected,
    build_connected,
    new_instance_id,
    persist_config,
    resolve_config,
)
from app.sources.base import Source
from app.sources.notion import NotionSource
from app.sources.notion_mcp import NotionMcpSource, pkce_pair

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get("/settings", response_model=AppSettingsOut)
async def get_settings_(db: AsyncSession = Depends(get_db)) -> AppSettingsOut:
    store = get_secret_store()
    return AppSettingsOut(
        app_name=await get_app_name(db),
        auto_sync=await get_auto_sync(db),
        secret_backend=store.backend_name,
        secret_backend_is_keychain=store.is_keychain,
    )


@router.patch("/settings", response_model=AppSettingsOut)
async def patch_settings(patch: AppSettingsPatch, db: AsyncSession = Depends(get_db)) -> AppSettingsOut:
    changed = False
    if patch.app_name is not None:
        await set_app_name(db, patch.app_name)
        changed = True
    if patch.auto_sync is not None:
        await set_auto_sync(db, patch.auto_sync)
        changed = True
    if changed:
        await db.commit()
    return await get_settings_(db)


@router.post("/backup", response_model=BackupOut)
async def backup_now() -> BackupOut:
    """Drop a timestamped copy of the database into `backups/` beside the live file."""
    try:
        path = backup_database(get_settings())
    except FileNotFoundError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    stat = path.stat()
    return BackupOut(
        filename=path.name,
        path=str(path),
        size_bytes=stat.st_size,
        created_at=datetime.fromtimestamp(stat.st_mtime, UTC),
    )


@router.get("/browse", response_model=BrowseOut)
async def browse(path: str | None = None) -> BrowseOut:
    """List the sub-directories of a path so a source's path field can be filled by clicking.
    Flags which are git repositories. Local-only, like every source that reads this machine."""
    base = (Path(path).expanduser() if path else Path.home()).resolve()
    if not base.is_dir():
        raise HTTPException(status_code=404, detail=f"Not a directory: {base}")

    entries = []
    try:
        children = sorted(base.iterdir(), key=lambda c: c.name.lower())
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=f"Permission denied: {base}") from exc
    for child in children:
        if child.name.startswith("."):
            continue
        try:
            if not child.is_dir():
                continue
            is_repo = (child / ".git").exists()
        except OSError:
            continue
        entries.append(BrowseEntryOut(name=child.name, path=str(child), is_repo=is_repo))

    parent = str(base.parent) if base.parent != base else None
    return BrowseOut(path=str(base), parent=parent, entries=entries)


@router.get("/emoji", response_model=dict[str, str])
async def emoji_map(db: AsyncSession = Depends(get_db)) -> dict[str, str]:
    """Custom emoji name → image URL, merged across configured Slack sources. The frontend
    renders these :shortcodes: as images in any item label, so no re-sync is needed."""
    merged: dict[str, str] = {}
    for connected in await build_connected(db):
        source = connected.source
        if hasattr(source, "emoji_map"):
            merged.update(source.emoji_map())
    return merged


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


_OAUTH_STATE_NS = "notion_oauth_state"


def _oauth_redirect_uri(request: Request, provider: str) -> str:
    """The callback URL, from the origin the browser is actually on — so a user behind a
    proxy (a Caddy host, a domain) registers and receives the redirect on that same host,
    not a hardcoded localhost the redirect would never reach."""
    origin = request.headers.get("origin")
    if origin:
        base = origin.rstrip("/")
    else:
        proto = request.headers.get("x-forwarded-proto") or request.url.scheme
        host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
        base = f"{proto}://{host}"
    return f"{base}/api/admin/oauth/{provider}/callback"


async def _notion_source(db: AsyncSession, instance_id: str) -> NotionSource:
    instance = await _require(db, instance_id)
    if instance.kind != "notion":
        raise HTTPException(status_code=400, detail="Not a Notion source")
    return BY_KIND["notion"](await resolve_config(db, instance))


@router.get("/sources/{instance_id}/notion", response_model=NotionOAuthOut)
async def notion_oauth_info(
    instance_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> NotionOAuthOut:
    source = await _notion_source(db, instance_id)
    return NotionOAuthOut(
        redirect_uri=_oauth_redirect_uri(request, "notion"),
        connected=source.is_configured(),
        oauth_ready=source.oauth_configured(),
    )


@router.post("/sources/{instance_id}/notion/authorize", response_model=NotionAuthorizeOut)
async def notion_oauth_authorize(
    instance_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> NotionAuthorizeOut:
    source = await _notion_source(db, instance_id)
    if not source.oauth_configured():
        raise HTTPException(status_code=400, detail="Save the client ID and secret first")
    redirect_uri = _oauth_redirect_uri(request, "notion")
    # A single-use nonce the callback trades back for the source and redirect URI, so a stray
    # callback can't attach a token to a source it was never authorised for.
    nonce = token_urlsafe(24)
    await set_value(
        db, _OAUTH_STATE_NS, nonce, json.dumps({"sid": instance_id, "redirect_uri": redirect_uri})
    )
    await db.commit()
    return NotionAuthorizeOut(authorize_url=source.authorize_url(redirect_uri, nonce))


@router.get("/oauth/notion/callback")
async def notion_oauth_callback(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    params = request.query_params
    if params.get("error"):
        return _oauth_page(f"Notion returned an error: {params['error']}", ok=False)

    raw_state = await get_value(db, _OAUTH_STATE_NS, params.get("state", ""))
    code = params.get("code")
    if not raw_state or not code:
        return _oauth_page("This login could not be verified. Start again from Connect.", ok=False)
    await set_value(db, _OAUTH_STATE_NS, params["state"], None)  # burn the nonce
    await db.commit()

    claims = json.loads(raw_state)
    instance = await db.get(SourceInstance, claims["sid"])
    if instance is None or instance.kind != "notion":
        return _oauth_page("That Notion source no longer exists.", ok=False)

    source = BY_KIND["notion"](await resolve_config(db, instance))
    try:
        updates = await source.exchange_code(code, claims["redirect_uri"])
    except httpx.HTTPError as exc:
        return _oauth_page(f"Notion refused the token exchange: {exc}", ok=False)

    await persist_config(db, instance, updates)
    return _oauth_page("Connected to Notion — you can close this tab.", ok=True)


async def _notion_mcp_source(db: AsyncSession, instance_id: str) -> NotionMcpSource:
    instance = await _require(db, instance_id)
    if instance.kind != "notion_mcp":
        raise HTTPException(status_code=400, detail="Not a Notion MCP source")
    return BY_KIND["notion_mcp"](await resolve_config(db, instance))


@router.get("/sources/{instance_id}/notion-mcp", response_model=NotionOAuthOut)
async def notion_mcp_info(
    instance_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> NotionOAuthOut:
    source = await _notion_mcp_source(db, instance_id)
    # No credentials to enter — the flow registers HQ itself — so it's always ready to start.
    return NotionOAuthOut(
        redirect_uri=_oauth_redirect_uri(request, "notion-mcp"),
        connected=source.is_configured(),
        oauth_ready=True,
    )


@router.post("/sources/{instance_id}/notion-mcp/authorize", response_model=NotionAuthorizeOut)
async def notion_mcp_authorize(
    instance_id: str, request: Request, db: AsyncSession = Depends(get_db)
) -> NotionAuthorizeOut:
    source = await _notion_mcp_source(db, instance_id)
    redirect_uri = _oauth_redirect_uri(request, "notion-mcp")
    try:
        client_id = await source.register_client(redirect_uri)
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail=f"MCP client registration failed: {exc}") from exc
    verifier, challenge = pkce_pair()
    nonce = token_urlsafe(24)
    # The verifier stays server-side until the callback: it, not the code, is what proves the
    # token request comes from whoever started the login.
    await set_value(
        db,
        _OAUTH_STATE_NS,
        nonce,
        json.dumps(
            {"sid": instance_id, "redirect_uri": redirect_uri, "verifier": verifier, "client_id": client_id}
        ),
    )
    await db.commit()
    return NotionAuthorizeOut(authorize_url=source.authorize_url(redirect_uri, nonce, challenge, client_id))


@router.get("/oauth/notion-mcp/callback")
async def notion_mcp_callback(request: Request, db: AsyncSession = Depends(get_db)) -> HTMLResponse:
    params = request.query_params
    if params.get("error"):
        return _oauth_page(f"Notion returned an error: {params['error']}", ok=False)

    raw_state = await get_value(db, _OAUTH_STATE_NS, params.get("state", ""))
    code = params.get("code")
    if not raw_state or not code:
        return _oauth_page("This login could not be verified. Start again from Connect.", ok=False)
    await set_value(db, _OAUTH_STATE_NS, params["state"], None)
    await db.commit()

    claims = json.loads(raw_state)
    instance = await db.get(SourceInstance, claims["sid"])
    if instance is None or instance.kind != "notion_mcp":
        return _oauth_page("That Notion MCP source no longer exists.", ok=False)

    source = BY_KIND["notion_mcp"](await resolve_config(db, instance))
    try:
        updates = await source.exchange_code(
            code, claims["redirect_uri"], claims["verifier"], claims["client_id"]
        )
    except httpx.HTTPError as exc:
        return _oauth_page(f"Notion refused the token exchange: {exc}", ok=False)

    await persist_config(db, instance, updates)
    return _oauth_page("Connected to Notion MCP — you can close this tab.", ok=True)


def _oauth_page(message: str, ok: bool) -> HTMLResponse:
    colour = "#2b8a3e" if ok else "#c92a2a"
    # Only self-close on success. On failure the message is the whole point — the redirect
    # URI mismatch, the refused exchange — so leave it up for the user to read and close.
    closer = "<script>setTimeout(()=>window.close(),1500)</script>" if ok else ""
    hint = "" if ok else "<p style='color:#868e96;font-size:.85rem'>You can close this tab.</p>"
    body = (
        "<!doctype html><meta charset='utf-8'><title>Notion</title>"
        "<body style='font-family:system-ui;display:flex;flex-direction:column;height:100vh;"
        "margin:0;gap:.5rem;align-items:center;justify-content:center;text-align:center;padding:1rem'>"
        f"<p style='color:{colour};font-size:1rem'>{message}</p>{hint}{closer}</body>"
    )
    return HTMLResponse(body)


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
            browse=spec.browse,
            value=(
                secrets.hint(instance.id, spec.key) if spec.kind == "secret" else source.get(spec.key) or None
            ),
            is_set=bool(source.get(spec.key)),
        )
        for spec in source.fields
        if not spec.hidden
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
