from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db
from app.models import SyncLog
from app.schemas import SyncLogOut, SyncRequest, SyncResult
from app.services.sync import sync_all

router = APIRouter(prefix="/sync", tags=["sync"])

# A sync is idempotent: run it twice in a row and it lands on the same state. Run it twice
# at once and it doesn't, because each run decides what to insert from a snapshot taken
# before the other had committed. Both then insert the same item ids and the loser fails on
# `UNIQUE constraint failed: items.id`. The end state was never in danger — the run is. The
# two also spend the same rate-limited API calls to compute the same answer.
# One process serves this app, so an in-process lock covers it.
_running = asyncio.Lock()


@router.post("", response_model=SyncResult)
async def trigger_sync(
    request: SyncRequest | None = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SyncResult:
    if _running.locked():
        # Refuse rather than queue: the caller wants a fresh answer, and the run already
        # under way is about to give them one.
        raise HTTPException(status_code=409, detail="A sync is already running")

    async with _running:
        try:
            return await sync_all(db, settings, only=request.source if request else None)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/status", response_model=list[SyncLogOut])
async def sync_status(db: AsyncSession = Depends(get_db), limit: int = 50) -> list[SyncLog]:
    stmt = select(SyncLog).order_by(SyncLog.started_at.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())
