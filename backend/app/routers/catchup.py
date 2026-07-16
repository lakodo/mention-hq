from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import (
    ConfirmRequest,
    CreateTaskFromItemRequest,
    ItemWithLinks,
    TaskOut,
    TriageRequest,
)
from app.services import catchup

router = APIRouter(prefix="/catchup", tags=["catchup"])


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
