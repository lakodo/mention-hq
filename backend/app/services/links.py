"""Resolving which mentions belong to which tasks.

Automatic links come from grouping and are recomputed from scratch on every sync. User
decisions live in `link_overrides` and are replayed on top. Keeping the two apart is what
lets sync be destructive about its own guesses while never destroying a human's.
"""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import LinkOverride

ATTACH = "attach"
DETACH = "detach"

Links = dict[str, set[str]]  # task_id -> mention_ids


async def load_overrides(db: AsyncSession) -> tuple[Links, Links]:
    rows = (await db.execute(select(LinkOverride))).scalars().all()
    attached: Links = defaultdict(set)
    detached: Links = defaultdict(set)
    for row in rows:
        target = attached if row.action == ATTACH else detached
        target[row.task_id].add(row.mention_id)
    return attached, detached


def apply_overrides(auto: Links, attached: Links, detached: Links) -> Links:
    resolved: Links = defaultdict(set)
    for task_id, mention_ids in auto.items():
        resolved[task_id] |= set(mention_ids)
    for task_id, mention_ids in attached.items():
        resolved[task_id] |= set(mention_ids)
    for task_id, mention_ids in detached.items():
        if task_id in resolved:
            resolved[task_id] -= set(mention_ids)
    return {task_id: ids for task_id, ids in resolved.items() if ids}


async def record_override(db: AsyncSession, mention_id: str, task_id: str, action: str) -> None:
    existing = (
        await db.execute(
            select(LinkOverride).where(LinkOverride.mention_id == mention_id, LinkOverride.task_id == task_id)
        )
    ).scalar_one_or_none()

    if existing is None:
        db.add(LinkOverride(mention_id=mention_id, task_id=task_id, action=action))
    else:
        # One decision per pair: attaching something you detached just flips it.
        existing.action = action
