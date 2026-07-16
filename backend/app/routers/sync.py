from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings, get_settings
from app.database import get_db
from app.models import SyncLog
from app.schemas import SyncLogOut, SyncRequest, SyncResult
from app.services.sync import sync_all

router = APIRouter(prefix="/sync", tags=["sync"])


@router.post("", response_model=SyncResult)
async def trigger_sync(
    request: SyncRequest | None = None,
    db: AsyncSession = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> SyncResult:
    try:
        return await sync_all(db, settings, only=request.source if request else None)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/status", response_model=list[SyncLogOut])
async def sync_status(db: AsyncSession = Depends(get_db), limit: int = 50) -> list[SyncLog]:
    stmt = select(SyncLog).order_by(SyncLog.started_at.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())
