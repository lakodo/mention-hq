from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import ItemWithLinks
from app.services import catchup

router = APIRouter(prefix="/items", tags=["items"])


@router.get("", response_model=list[ItemWithLinks])
async def list_items(db: AsyncSession = Depends(get_db), limit: int = 200):
    """All items, newest first — the timeline. Each carries its links, so the UI can show
    (and link to) whatever tasks an item was filed under, or none."""
    return await catchup.all_items(db, limit=limit)
