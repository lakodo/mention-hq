"""Precomputed, brain-derived task fields.

The task screen wants a next action and a sensible bucket the moment it opens, not after a
click and a wait. So when a task's items change we compute them in the background and store
them. Like the auto-matcher, this never holds a DB transaction across the slow brain call:
it reads and asks in one short-lived session, then writes in another.
"""

from __future__ import annotations

import asyncio

import structlog
from sqlalchemy import select

from app.database import SessionLocal
from app.models import Task
from app.services import ai

log = structlog.get_logger(__name__)

UNCATEGORIZED = "Uncategorized"
_BUCKET_FLOOR = 0.6

_background: set[asyncio.Task] = set()


def schedule_enrich(task_id: str) -> None:
    """Recompute a task's next action (and, if it's unfiled, a recommended bucket) in the
    background. A no-op when there's no brain configured."""
    if not ai.status().available:
        return
    task = asyncio.create_task(_enrich(task_id))
    _background.add(task)
    task.add_done_callback(_background.discard)


async def _enrich(task_id: str) -> None:
    try:
        action, bucket = await _compute(task_id)
        if action is None and bucket is None:
            return
        async with SessionLocal() as db:
            task = await db.get(Task, task_id)
            if task is None:
                return
            if action is not None:
                task.next_action = action
            # Only fill a bucket that's still unset and not hand-picked.
            if bucket is not None and task.bucket == UNCATEGORIZED and not task.bucket_override:
                task.bucket = bucket
            await db.commit()
    except Exception as exc:
        log.warning("enrich_failed", task=task_id, error=str(exc))


async def _compute(task_id: str) -> tuple[str | None, str | None]:
    """The brain phase, in its own read session so no write is held across it."""
    async with SessionLocal() as db:
        task = await db.get(Task, task_id)
        if task is None or task.archived_at is not None:
            return None, None
        want_bucket = task.bucket == UNCATEGORIZED and not task.bucket_override

        action: str | None = None
        try:
            action = (await ai.next_action(task)).action
        except Exception:
            log.warning("enrich_next_action_failed", task=task_id)

        bucket: str | None = None
        if want_bucket:
            try:
                suggestion = await ai.suggest_bucket(db, task)
                # Never auto-create a bucket — only adopt one that already exists.
                if not suggestion.is_new and suggestion.confidence >= _BUCKET_FLOOR:
                    bucket = suggestion.bucket
            except Exception:
                log.warning("enrich_bucket_failed", task=task_id)

        return action, bucket


async def backfill(db) -> int:
    """Schedule enrichment for every active task that has no next action yet — the one-time
    fill for tasks that predate this feature. Returns how many were scheduled."""
    ids = (
        (await db.execute(select(Task.id).where(Task.next_action.is_(None), Task.archived_at.is_(None))))
        .scalars()
        .all()
    )
    for task_id in ids:
        schedule_enrich(task_id)
    return len(ids)
