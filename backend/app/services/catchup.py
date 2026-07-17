"""Catch-up: the inbox of items you haven't ruled on yet.

Everything here writes a decision — a Link in the confirmed or rejected state — which sync
then treats as untouchable. That is the whole contract between you and the engine: it
guesses as often as it likes, you answer once, and your answer sticks.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CONFIRMED, PROPOSED, REJECTED, Item, Link, Task
from app.services.buckets import load_matcher
from app.sources.keys import all_reference_keys


async def untriaged(db: AsyncSession, limit: int = 100) -> list[Item]:
    stmt = select(Item).where(Item.triaged.is_(False)).order_by(Item.occurred_at.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


async def all_items(db: AsyncSession, limit: int = 200) -> list[Item]:
    """Every item, newest first — the timeline feed, independent of any task."""
    stmt = select(Item).order_by(Item.occurred_at.desc()).limit(limit)
    return list((await db.execute(stmt)).scalars().all())


async def skipped_items(db: AsyncSession, since: datetime | None = None) -> list[Item]:
    """Items that were skipped (triaged with no task attachment) — the skipped view."""
    stmt = select(Item).where(Item.triaged.is_(True), Item.triage_reason.isnot(None))
    if since is not None:
        stmt = stmt.where(Item.triaged_at >= since)
    stmt = stmt.order_by(Item.triaged_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def confirm(db: AsyncSession, item_id: str, task_ids: list[str]) -> Item:
    """Attach an item to one or more tasks, for good."""
    item = await _require_item(db, item_id)
    for task_id in task_ids:
        if await db.get(Task, task_id) is None:
            raise LookupError(f"Task not found: {task_id}")
        await _decide(db, item_id, task_id, CONFIRMED)
    item.triaged = True
    # Filing an item means it is handled, not skipped: clearing the reason lifts a skipped
    # item off the skipped list and onto its task.
    item.triage_reason = None
    await db.commit()
    return await _reload(db, item_id)


async def reject(db: AsyncSession, item_id: str, task_id: str) -> Item:
    """Say no to a link. Remembered, so the engine can't propose it again."""
    await _require_item(db, item_id)
    await _decide(db, item_id, task_id, REJECTED)
    await db.commit()
    return await _reload(db, item_id)


async def _decide(db: AsyncSession, item_id: str, task_id: str, state: str) -> None:
    link = await db.get(Link, {"task_id": task_id, "item_id": item_id})
    if link is None:
        db.add(
            Link(
                task_id=task_id,
                item_id=item_id,
                state=state,
                engine=None,
                confidence=1.0,
                reason="You said so",
                decided_at=datetime.now(UTC),
            )
        )
        return
    # A decision overwrites an engine proposal, and a later decision overwrites an
    # earlier one — the most recent answer always wins.
    link.state = state
    link.decided_at = datetime.now(UTC)
    if link.engine is None:
        link.reason = "You said so"


async def create_task_from_item(
    db: AsyncSession, item_id: str, title: str, bucket: str | None, priority: int = 50
) -> Task:
    item = await _require_item(db, item_id)
    matcher = await load_matcher(db)

    resolved_title = title.strip() or item.label
    task = Task(
        id=f"task:{uuid.uuid4().hex[:12]}",
        title=resolved_title,
        bucket=bucket or matcher.assign(resolved_title, []),
        bucket_override=bucket is not None,
        status="open",
        priority=priority,
        tags=[],
        unread=False,
        origin="manual",
        title_override=True,
        updated_at=item.occurred_at,
        synced_at=datetime.now(UTC),
    )
    db.add(task)
    await db.flush()

    await _decide(db, item_id, task.id, CONFIRMED)
    # Not triaged here on purpose: New task seeds a task from the item and stages it in the
    # attach box, but the item stays in the inbox until the user clicks Attach — that is what
    # files it, and lets them attach it to other tasks first.
    await db.commit()

    stmt = select(Task).where(Task.id == task.id).execution_options(populate_existing=True)
    return (await db.execute(stmt)).scalars().one()


async def create_note(db: AsyncSession, text: str, task_ids: list[str]) -> Item:
    """A brain-dump: a hand-typed item. With no tasks it lands in catch-up like anything
    else; with tasks it is filed straight onto them. It has no source instance, so a sync
    keeps it (nothing re-fetches it) and the engine can still propose tasks for it."""
    body = text.strip()
    now = datetime.now(UTC)
    item_id = f"note:{uuid.uuid4().hex[:12]}"
    item = Item(
        id=item_id,
        source="note",
        instance_id=None,
        label=body[:1000],
        url=None,
        context=None,
        occurred_at=now,
        first_seen_at=now,
        triaged=bool(task_ids),
        extra={
            "text": body,
            "identity_keys": [],
            "reference_keys": sorted(all_reference_keys(body)),
        },
    )
    db.add(item)
    await db.flush()

    for task_id in task_ids:
        if await db.get(Task, task_id) is None:
            raise LookupError(f"Task not found: {task_id}")
        await _decide(db, item_id, task_id, CONFIRMED)

    await db.commit()
    return await _reload(db, item_id)


async def delete_item(db: AsyncSession, item_id: str) -> None:
    """Remove an item outright — its links cascade. For clearing out leftovers, e.g. items a
    since-deleted source left behind."""
    item = await db.get(Item, item_id)
    if item is None:
        raise LookupError(f"Item not found: {item_id}")
    await db.delete(item)
    await db.commit()


async def mark_triaged(db: AsyncSession, item_id: str, triaged: bool = True) -> Item:
    item = await _require_item(db, item_id)
    item.triaged = triaged
    if triaged:
        item.triage_reason = "Skipped"
        item.triaged_at = datetime.now(UTC)
    else:
        item.triage_reason = None
        item.triaged_at = None
    await db.commit()
    return await _reload(db, item_id)


async def reset_matched_at(db: AsyncSession) -> int:
    """Clear matched_at for every untriaged item so the auto-matcher re-runs them all."""
    items = list((await db.execute(select(Item).where(Item.triaged.is_(False)))).scalars().all())
    for item in items:
        item.matched_at = None
    await db.commit()
    return len(items)


async def proposals_for(db: AsyncSession, item_id: str) -> list[Link]:
    stmt = select(Link).where(Link.item_id == item_id, Link.state == PROPOSED)
    return list((await db.execute(stmt)).scalars().all())


async def _require_item(db: AsyncSession, item_id: str) -> Item:
    item = await db.get(Item, item_id)
    if item is None:
        raise LookupError(f"Item not found: {item_id}")
    return item


async def _reload(db: AsyncSession, item_id: str) -> Item:
    """Re-read an item and its links after a write.

    The identity map still holds the links as they were *before* the write, so returning
    the same object would answer a confirm with the state from before it.
    """
    stmt = select(Item).where(Item.id == item_id).execution_options(populate_existing=True)
    return (await db.execute(stmt)).scalars().one()
