from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Mention, Task, TaskMention
from app.schemas import TaskCreate, TaskOut, TaskPatch
from app.services.buckets import UNCATEGORIZED, load_matcher

router = APIRouter(prefix="/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    bucket: str | None = None,
    status: str | None = None,
    source: str | None = None,
    unread: bool | None = None,
    q: str | None = Query(None, description="Free-text match on title"),
) -> list[Task]:
    stmt = select(Task)
    if bucket:
        stmt = stmt.where(Task.bucket == bucket)
    if status:
        stmt = stmt.where(Task.status == status)
    if unread is not None:
        stmt = stmt.where(Task.unread.is_(unread))
    if q:
        stmt = stmt.where(Task.title.ilike(f"%{q}%"))
    if source:
        stmt = stmt.where(
            Task.id.in_(
                select(TaskMention.task_id)
                .join(Mention, Mention.id == TaskMention.mention_id)
                .where(Mention.source == source)
            )
        )
    stmt = stmt.order_by(Task.updated_at.desc())
    return list((await db.execute(stmt)).scalars().all())


@router.post("", response_model=TaskOut, status_code=201)
async def create_task(payload: TaskCreate, db: AsyncSession = Depends(get_db)) -> Task:
    title = payload.title.strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required")

    matcher = await load_matcher(db)
    now = datetime.now(UTC)
    task = Task(
        id=f"task:{uuid.uuid4().hex[:12]}",
        title=title,
        bucket=payload.bucket or matcher.assign(title, payload.tags),
        bucket_override=payload.bucket is not None,
        status="open",
        tags=payload.tags,
        unread=False,
        origin="manual",
        title_override=True,
        updated_at=now,
        synced_at=now,
    )
    db.add(task)
    await db.commit()
    return await db.get(Task, task.id)


@router.get("/{task_id}", response_model=TaskOut)
async def get_task(task_id: str, db: AsyncSession = Depends(get_db)) -> Task:
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.patch("/{task_id}", response_model=TaskOut)
async def patch_task(task_id: str, patch: TaskPatch, db: AsyncSession = Depends(get_db)) -> Task:
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    if patch.bucket is not None:
        task.bucket = patch.bucket or UNCATEGORIZED
        # Remember the override so the next sync's keyword match doesn't overwrite it.
        task.bucket_override = True
    if patch.title is not None and patch.title.strip():
        task.title = patch.title.strip()
        task.title_override = True
    if patch.tags is not None:
        task.tags = patch.tags
    if patch.unread is not None:
        task.unread = patch.unread
    if patch.status is not None:
        task.status = patch.status

    await db.commit()
    await db.refresh(task)
    return task


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: str, db: AsyncSession = Depends(get_db)) -> None:
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    if task.origin != "manual":
        # An auto task would just come back on the next sync; detaching its mentions in
        # the catch-up screen is the honest way to make it go away.
        raise HTTPException(status_code=400, detail="Only manually created tasks can be deleted")
    await db.delete(task)
    await db.commit()
