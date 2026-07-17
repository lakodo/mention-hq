from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import CONFIRMED, REJECTED, Item, Link, Task
from app.schemas import TaskCreate, TaskOut, TaskPatch
from app.services.buckets import UNCATEGORIZED, load_matcher

router = APIRouter(prefix="/tasks", tags=["tasks"])


async def _load(db: AsyncSession, task_id: str) -> Task | None:
    stmt = select(Task).where(Task.id == task_id).execution_options(populate_existing=True)
    return (await db.execute(stmt)).scalars().one_or_none()


@router.get("", response_model=list[TaskOut])
async def list_tasks(
    db: AsyncSession = Depends(get_db),
    bucket: str | None = None,
    status: str | None = None,
    source: str | None = None,
    unread: bool | None = None,
    archived: bool = Query(False, description="Return archived tasks instead of active ones"),
    q: str | None = Query(None, description="Free-text match on title"),
) -> list[Task]:
    stmt = select(Task)
    # Archived tasks are hidden from every list unless asked for by name.
    stmt = stmt.where(Task.archived_at.isnot(None) if archived else Task.archived_at.is_(None))
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
                select(Link.task_id)
                .join(Item, Item.id == Link.item_id)
                .where(Item.source == source, Link.state != REJECTED)
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
        description=payload.description,
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
    # A relationship on a just-added instance is unloaded rather than empty, so
    # serialising it would trigger a lazy load, which raises under async.
    return await _load(db, task.id)


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
    if patch.description is not None:
        task.description = patch.description or None
    if patch.tags is not None:
        task.tags = patch.tags
    if patch.unread is not None:
        task.unread = patch.unread
    if patch.status is not None:
        task.status = patch.status
    if patch.archived is not None:
        task.archived_at = datetime.now(UTC) if patch.archived else None

    await db.commit()
    return await _load(db, task_id)


@router.delete("/{task_id}", status_code=204)
async def delete_task(task_id: str, db: AsyncSession = Depends(get_db)) -> None:
    """Delete a task and free its items.

    The items themselves are never deleted — they belong to their source, not to the task.
    Deleting drops the task's links, and any item left on no other task returns to catch-up
    untriaged, so it is triaged again rather than lost. Archive is the alternative that keeps
    the items filed.
    """
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    freed = [link.item_id for link in task.links if link.state != REJECTED]
    await db.delete(task)
    await db.flush()

    for item_id in freed:
        still_attached = await db.scalar(
            select(func.count()).select_from(Link).where(Link.item_id == item_id, Link.state == CONFIRMED)
        )
        if not still_attached:
            item = await db.get(Item, item_id)
            if item is not None:
                item.triaged = False

    await db.commit()
