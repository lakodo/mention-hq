from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from pathlib import Path

import structlog
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import SessionLocal, get_db
from app.routers import admin, buckets, catchup, items, people, sync, tasks, triage
from app.services.app_config import get_app_name
from app.services.sync import sync_all

log = structlog.get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    background: set[asyncio.Task] = set()
    if settings.sync_on_startup:
        # asyncio only holds a weak reference to running tasks, so a task nobody keeps
        # can be garbage-collected mid-flight. Hold it until it finishes.
        task = asyncio.create_task(_startup_sync())
        background.add(task)
        task.add_done_callback(background.discard)
    yield


async def _startup_sync() -> None:
    settings = get_settings()
    async with SessionLocal() as db:
        try:
            result = await sync_all(db, settings)
            log.info("startup_sync_done", added=result.tasks_added, updated=result.tasks_updated)
        except Exception as exc:
            log.warning("startup_sync_failed", error=str(exc))


app = FastAPI(title="Personal HQ", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Everything the browser calls lives under /api, so the SPA owns every other path and a
# reverse proxy can split the two by prefix alone — no route-by-route collision list.
API_PREFIX = "/api"

app.include_router(tasks.router, prefix=API_PREFIX)
app.include_router(buckets.router, prefix=API_PREFIX)
app.include_router(catchup.router, prefix=API_PREFIX)
app.include_router(items.router, prefix=API_PREFIX)
app.include_router(people.router, prefix=API_PREFIX)
app.include_router(triage.router, prefix=API_PREFIX)
app.include_router(sync.router, prefix=API_PREFIX)
app.include_router(admin.router, prefix=API_PREFIX)


@app.get("/api/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/manifest.webmanifest", tags=["meta"])
async def manifest(db: AsyncSession = Depends(get_db)) -> JSONResponse:
    """The PWA manifest, served live so the installed app carries your own app name rather than
    a value baked in at build time. Under /api so the same route answers in dev (through the
    Vite proxy) and in production (the API serving the built SPA)."""
    name = await get_app_name(db)
    return JSONResponse(
        {
            "name": name,
            "short_name": name,
            "description": "Your activity across GitHub, Linear, Slack, Notion and local files, "
            "grouped by subject.",
            "start_url": "/",
            "scope": "/",
            "display": "standalone",
            "theme_color": "#ffffff",
            "background_color": "#f8f9fa",
            "icons": [
                {"src": "/icon.svg", "sizes": "any", "type": "image/svg+xml", "purpose": "any"},
                {
                    "src": "/icon-maskable.svg",
                    "sizes": "any",
                    "type": "image/svg+xml",
                    "purpose": "maskable",
                },
            ],
        },
        media_type="application/manifest+json",
    )


def _serve_frontend(app: FastAPI) -> None:
    """Serve the built frontend, so a production run is one process on one origin.

    Built output only: hot reload is a websocket Vite owns, so in dev the two run side by
    side and this does nothing. check_dir is off for exactly that reason — no build is a
    normal state here, not a misconfiguration.
    """
    dist = get_settings().frontend_dist
    index = dist / "index.html"
    if not index.exists():
        return

    app.frontend("/", directory=dist, check_dir=False)
    log.info("frontend_served", directory=str(dist), stale=_is_stale(index))


def _is_stale(index: Path) -> bool:
    """Whether the build predates the source it was built from.

    A stale dist serves an old UI with no visible sign, which reads as a bug that won't
    reproduce in dev. Worth a word in the log rather than an afternoon.
    """
    source = get_settings().frontend_dist.parent / "src"
    if not source.is_dir():
        return False

    newest = max((path.stat().st_mtime for path in source.rglob("*") if path.is_file()), default=0)
    stale = newest > index.stat().st_mtime
    if stale:
        log.warning("frontend_build_is_stale", hint="run `task front:build` to rebuild it")
    return stale


_serve_frontend(app)
