from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import BrainDumpRequest, ItemWithLinks, NoteUpdate
from app.services import catchup

router = APIRouter(prefix="/items", tags=["items"])


@router.get("", response_model=list[ItemWithLinks])
async def list_items(db: AsyncSession = Depends(get_db), limit: int = 200):
    """All items, newest first — the timeline. Each carries its links, so the UI can show
    (and link to) whatever tasks an item was filed under, or none."""
    return await catchup.all_items(db, limit=limit)


@router.post("", response_model=ItemWithLinks, status_code=201)
async def create_note(request: BrainDumpRequest, db: AsyncSession = Depends(get_db)):
    """A brain dump: turn typed text into an item. It flows through catch-up like any item,
    unless tasks are given, in which case it is filed straight onto them."""
    try:
        return await catchup.create_note(
            db, request.text, request.task_ids, url=request.url, title=request.title
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch("/{item_id}", response_model=ItemWithLinks)
async def update_note(item_id: str, request: NoteUpdate, db: AsyncSession = Depends(get_db)):
    """Edit a brain-dump note's text."""
    try:
        return await catchup.update_note(db, item_id, request.text)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{item_id}", status_code=204)
async def delete_item(item_id: str, db: AsyncSession = Depends(get_db)) -> None:
    """Remove an item and its links — for clearing out leftovers a deleted source left behind."""
    try:
        await catchup.delete_item(db, item_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/skipped", response_model=list[ItemWithLinks])
async def list_skipped(
    db: AsyncSession = Depends(get_db),
    since: datetime | None = Query(None, description="Only items skipped at or after this timestamp"),
):
    """Skipped items — triaged but never attached to a task — with the reason recorded."""
    return await catchup.skipped_items(db, since=since)
