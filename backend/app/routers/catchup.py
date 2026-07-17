from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Item, Task
from app.schemas import (
    ConfirmRequest,
    CreateTaskFromItemRequest,
    ItemWithLinks,
    TaskMatchOut,
    TaskOut,
    TriageRequest,
)
from app.services import ai, catchup
from app.services.sync import schedule_auto_match

router = APIRouter(prefix="/catchup", tags=["catchup"])


@router.post("/match-all", status_code=204)
async def match_all(db: AsyncSession = Depends(get_db)) -> None:
    """Re-attempt a brain match on every inbox item, in the background.

    Clears the per-item match flag (which commits), then kicks off a detached matching pass
    so the button returns at once — the matches land as proposals over the next minute.
    """
    await catchup.reset_matched_at(db)
    schedule_auto_match()


@router.post("/{item_id}/suggest-tasks", response_model=list[TaskMatchOut])
async def suggest_tasks(item_id: str, db: AsyncSession = Depends(get_db)):
    """Ask the brain which existing tasks this item belongs to. On-demand; suggests only."""
    item = await db.get(Item, item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Item not found: {item_id}")
    try:
        matches = await ai.suggest_tasks(db, item)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    rows = (await db.execute(select(Task).where(Task.id.in_([m.task_id for m in matches])))).scalars()
    tasks = {task.id: task for task in rows.all()}
    return [
        TaskMatchOut(task=tasks[m.task_id], confidence=m.confidence, reason=m.reason)
        for m in matches
        if m.task_id in tasks
    ]


@router.get("", response_model=list[ItemWithLinks])
async def list_untriaged(db: AsyncSession = Depends(get_db), limit: int = 100):
    return await catchup.untriaged(db, limit=limit)


@router.post("/{item_id}/confirm", response_model=ItemWithLinks)
async def confirm(item_id: str, request: ConfirmRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await catchup.confirm(db, item_id, request.task_ids)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{item_id}/reject/{task_id}", response_model=ItemWithLinks)
async def reject(item_id: str, task_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await catchup.reject(db, item_id, task_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{item_id}/new-task", response_model=TaskOut)
async def create_task(
    item_id: str,
    request: CreateTaskFromItemRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await catchup.create_task_from_item(db, item_id, request.title, request.bucket)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{item_id}/triage", response_model=ItemWithLinks)
async def triage(item_id: str, request: TriageRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await catchup.mark_triaged(db, item_id, request.triaged)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
