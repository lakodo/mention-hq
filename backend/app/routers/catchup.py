from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import (
    AttachRequest,
    CreateTaskFromMentionRequest,
    MentionWithTasks,
    TaskOut,
    TriageRequest,
)
from app.services import catchup

router = APIRouter(prefix="/catchup", tags=["catchup"])


@router.get("", response_model=list[MentionWithTasks])
async def list_untriaged(db: AsyncSession = Depends(get_db), limit: int = 100):
    return await catchup.untriaged(db, limit=limit)


@router.post("/{mention_id}/attach", response_model=MentionWithTasks)
async def attach_mention(mention_id: str, request: AttachRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await catchup.attach(db, mention_id, request.task_ids)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{mention_id}/attach/{task_id}", response_model=MentionWithTasks)
async def detach_mention(mention_id: str, task_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await catchup.detach(db, mention_id, task_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{mention_id}/new-task", response_model=TaskOut)
async def create_task(
    mention_id: str,
    request: CreateTaskFromMentionRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await catchup.create_task_from_mention(db, mention_id, request.title, request.bucket)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{mention_id}/triage", response_model=MentionWithTasks)
async def triage(mention_id: str, request: TriageRequest, db: AsyncSession = Depends(get_db)):
    try:
        return await catchup.mark_triaged(db, mention_id, request.triaged)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
