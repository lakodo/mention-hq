"""The catch-up inbox: untriaged mentions, and attaching them to tasks.

Attaching writes a permanent override rather than just a link row, so the decision
survives the next sync rebuilding every automatic link.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Mention, Task, TaskMention
from app.services.buckets import load_matcher
from app.services.links import ATTACH, DETACH, record_override


async def untriaged(db: AsyncSession, limit: int = 100) -> list[Mention]:
    stmt = select(Mention).where(Mention.triaged.is_(False)).order_by(Mention.occurred_at.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


async def attach(db: AsyncSession, mention_id: str, task_ids: list[str]) -> Mention:
    mention = await _require_mention(db, mention_id)
    for task_id in task_ids:
        if await db.get(Task, task_id) is None:
            raise LookupError(f"Task not found: {task_id}")
        await record_override(db, mention_id, task_id, ATTACH)
        if await db.get(TaskMention, {"task_id": task_id, "mention_id": mention_id}) is None:
            db.add(TaskMention(task_id=task_id, mention_id=mention_id, linked_by="manual"))
    mention.triaged = True
    await db.commit()
    return await _require_mention(db, mention_id)


async def detach(db: AsyncSession, mention_id: str, task_id: str) -> Mention:
    await _require_mention(db, mention_id)  # 404s before we write an override
    await record_override(db, mention_id, task_id, DETACH)
    link = await db.get(TaskMention, {"task_id": task_id, "mention_id": mention_id})
    if link is not None:
        await db.delete(link)
    await db.commit()
    return await _require_mention(db, mention_id)


async def create_task_from_mention(db: AsyncSession, mention_id: str, title: str, bucket: str | None) -> Task:
    mention = await _require_mention(db, mention_id)
    matcher = await load_matcher(db)

    task = Task(
        id=f"task:{uuid.uuid4().hex[:12]}",
        title=title.strip() or mention.label,
        bucket=bucket or matcher.assign(title, []),
        bucket_override=bucket is not None,
        status="open",
        tags=[],
        unread=False,
        origin="manual",
        title_override=True,
        updated_at=mention.occurred_at,
        synced_at=datetime.now(UTC),
    )
    db.add(task)
    await db.flush()

    await record_override(db, mention_id, task.id, ATTACH)
    db.add(TaskMention(task_id=task.id, mention_id=mention_id, linked_by="manual"))
    mention.triaged = True

    await db.commit()
    return await db.get(Task, task.id)


async def mark_triaged(db: AsyncSession, mention_id: str, triaged: bool = True) -> Mention:
    mention = await _require_mention(db, mention_id)
    mention.triaged = triaged
    await db.commit()
    return await _require_mention(db, mention_id)


async def _require_mention(db: AsyncSession, mention_id: str) -> Mention:
    mention = await db.get(Mention, mention_id)
    if mention is None:
        raise LookupError(f"Mention not found: {mention_id}")
    return mention
