from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import get_settings
from app.database import SessionLocal
from app.routers import admin, buckets, catchup, sync, tasks
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

app.include_router(tasks.router)
app.include_router(buckets.router)
app.include_router(catchup.router)
app.include_router(sync.router)
app.include_router(admin.router)


@app.get("/health", tags=["meta"])
async def health() -> dict[str, str]:
    return {"status": "ok"}


def _serve_frontend(app: FastAPI) -> None:
    """Serve the built frontend, so a production run is one process on one origin.

    Built output only: hot reload is a websocket Vite owns, so in dev the two run side by
    side and this does nothing. check_dir is off for exactly that reason — no build is a
    normal state here, not a misconfiguration.
    """
    dist = get_settings().frontend_dist
    if not (dist / "index.html").exists():
        return

    app.frontend("/", directory=dist, check_dir=False)
    log.info("frontend_served", directory=str(dist))


_serve_frontend(app)
