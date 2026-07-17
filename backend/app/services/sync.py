"""Sync: fetch every source, run each item through the engine, persist.

The engine sees every task at once, not just the ones from this source — a PR can only be
proposed against a task built from a Slack thread if that task is on the table. So a
partial sync (`?source=github`) still reads the other sources' stored items back out of
the DB first.

Order matters and is deliberate. Items are processed best-title-source first (a Linear
issue makes a better task title than a Slack message), so that when an item has to create
a task, the task gets the best name available.
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app import engine as engine_registry
from app.config import Settings
from app.engine import TaskView
from app.models import CONFIRMED, PROPOSED, REJECTED, Item, Link, SyncLog, Task
from app.schemas import SyncResult, SyncSourceResult
from app.services.buckets import load_matcher
from app.services.sources_factory import Connected, build_connected
from app.sources.base import STATUS_PRIORITY, TITLE_PRIORITY, RawItem

log = structlog.get_logger(__name__)

# A proposal this strong stands in for a task of the item's own. Below it, the item gets
# its own task and keeps the proposal as a suggestion — so a weak candidate is something to
# review, never something that hides an item until someone notices.
TRUSTED_ENOUGH_TO_HOME = 0.9


@dataclass
class _FetchOutcome:
    instance_id: str
    name: str
    kind: str
    items: list[RawItem]
    error: str | None = None
    configured: bool = True

    @property
    def authoritative(self) -> bool:
        """Whether this run can be trusted to have the full picture for the source.

        A source that errored still has valid items in the DB from last time; dropping
        them because GitHub 500'd once would empty the board.
        """
        return self.configured and self.error is None


async def sync_all(db: AsyncSession, settings: Settings, only: str | None = None) -> SyncResult:
    del settings  # connections carry their own settings
    started_at = datetime.now(UTC)
    started = time.perf_counter()

    connected = await build_connected(db)
    if only is not None:
        connected = [c for c in connected if only in (c.instance.id, c.instance.kind)]
        if not connected:
            raise ValueError(f"Unknown source: {only}")

    # Concurrently: these are independent network calls, and run in series the sync takes
    # as long as every source added together. _fetch never raises, so gather is safe.
    outcomes = list(await asyncio.gather(*(_fetch(c) for c in connected)))

    fetched = [(o.instance_id, item) for o in outcomes for item in o.items]

    refreshed = {o.instance_id for o in outcomes if o.authoritative}
    kept = await _stored_items_to_keep(db, refreshed)

    result = await _persist(db, _merge(kept, fetched))

    duration = round(time.perf_counter() - started, 2)
    _write_log(db, outcomes, result, started_at, duration)
    await db.commit()

    return SyncResult(
        sources_synced=[o.name for o in outcomes if o.authoritative],
        items_added=result.items_added,
        items_updated=result.items_updated,
        proposals=result.proposals,
        tasks_updated=result.tasks_updated,
        duration_seconds=duration,
        errors=[f"{o.name}: {o.error}" for o in outcomes if o.error],
        results=[
            SyncSourceResult(source=o.name, items_fetched=len(o.items), error=o.error) for o in outcomes
        ],
    )


async def _fetch(connected: Connected) -> _FetchOutcome:
    instance, source = connected.instance, connected.source
    common = {"instance_id": instance.id, "name": instance.name, "kind": instance.kind}
    if not source.is_configured():
        return _FetchOutcome(**common, items=[], configured=False)
    try:
        return _FetchOutcome(**common, items=await source.fetch())
    except Exception as exc:  # one broken connection must not fail the others
        log.warning("source_fetch_failed", instance=instance.id, error=str(exc))
        return _FetchOutcome(**common, items=[], error=str(exc))


def _merge(
    kept: list[tuple[str | None, RawItem]], fetched: list[tuple[str | None, RawItem]]
) -> list[tuple[str | None, RawItem]]:
    by_id = {item.id: (instance_id, item) for instance_id, item in kept}
    by_id.update({item.id: (instance_id, item) for instance_id, item in fetched})
    return list(by_id.values())


async def _stored_items_to_keep(db: AsyncSession, refreshed: set[str]) -> list[tuple[str | None, RawItem]]:
    """Items from connections this run didn't authoritatively refresh.

    Keyed by connection rather than by kind: with two GitHub accounts connected, one of
    them erroring must not drop the other's items.
    """
    rows = (await db.execute(select(Item))).scalars().all()
    return [(row.instance_id, _row_to_raw(row)) for row in rows if row.instance_id not in refreshed]


def _row_to_raw(row: Item) -> RawItem:
    return RawItem(
        source=row.source,
        external_id=row.id.split(":", 1)[1],
        label=row.label,
        occurred_at=row.occurred_at,
        url=row.url,
        context=row.context,
        title=row.extra.get("title"),
        status=row.extra.get("status"),
        tags=row.extra.get("tags", []),
        identity_keys=set(row.extra.get("identity_keys", [])),
        reference_keys=set(row.extra.get("reference_keys", [])),
        extra=row.extra,
    )


@dataclass
class _PersistResult:
    items_added: int
    items_updated: int
    proposals: int
    tasks_updated: int


async def _persist(db: AsyncSession, owned: list[tuple[str | None, RawItem]]) -> _PersistResult:
    items = [item for _, item in owned]
    items_added, items_updated = await _upsert_items(db, owned)
    await _clear_stale_proposals(db)
    await _purge_auto_tasks(db)

    matcher = await load_matcher(db)
    # Read once and carry through the loop. Re-reading per item would be a query per item
    # against tables only this loop is writing to.
    decisions = await _decisions_by_item(db)
    views = await _task_views(db)

    proposals = 0
    for raw in items:
        proposals += await _propose(db, raw, views, decisions.get(raw.id, {}))

    tasks_updated = await _refresh_tasks(db, {i.id: i for i in items}, matcher)
    return _PersistResult(items_added, items_updated, proposals, tasks_updated)


async def _decisions_by_item(db: AsyncSession) -> dict[str, dict[str, str]]:
    rows = (await db.execute(select(Link).where(Link.state.in_([CONFIRMED, REJECTED])))).scalars().all()
    decisions: dict[str, dict[str, str]] = {}
    for row in rows:
        decisions.setdefault(row.item_id, {})[row.task_id] = row.state
    return decisions


async def _task_views(db: AsyncSession) -> list[TaskView]:
    """Snapshot every task and the keys of the items on it, in two queries."""
    tasks = (await db.execute(select(Task))).scalars().all()
    rows = (
        await db.execute(
            select(Link.task_id, Item.extra).join(Item, Item.id == Link.item_id).where(Link.state != REJECTED)
        )
    ).all()

    identity: dict[str, set[str]] = {}
    reference: dict[str, set[str]] = {}
    for task_id, extra in rows:
        identity.setdefault(task_id, set()).update(extra.get("identity_keys", []))
        reference.setdefault(task_id, set()).update(extra.get("reference_keys", []))

    return [
        TaskView(
            id=task.id,
            title=task.title,
            identity_keys=frozenset(identity.get(task.id, ())),
            reference_keys=frozenset(reference.get(task.id, ())),
        )
        for task in tasks
    ]


async def _upsert_items(db: AsyncSession, owned: list[tuple[str | None, RawItem]]) -> tuple[int, int]:
    existing = {row.id: row for row in (await db.execute(select(Item))).scalars().all()}
    incoming = {item.id for _, item in owned}
    added = updated = 0

    for instance_id, raw in owned:
        payload = {
            **raw.extra,
            "title": raw.title,
            "status": raw.status,
            "tags": raw.tags,
            "identity_keys": sorted(raw.identity_keys),
            "reference_keys": sorted(raw.reference_keys),
        }
        row = existing.get(raw.id)
        if row is None:
            db.add(
                Item(
                    id=raw.id,
                    source=raw.source,
                    instance_id=instance_id,
                    label=raw.label,
                    url=raw.url,
                    context=raw.context,
                    occurred_at=raw.occurred_at,
                    triaged=False,
                    first_seen_at=datetime.now(UTC),
                    extra=payload,
                )
            )
            added += 1
        else:
            changed = row.label != raw.label or row.occurred_at != raw.occurred_at
            row.label = raw.label
            row.url = raw.url
            row.context = raw.context
            row.extra = payload
            row.instance_id = instance_id
            # New activity un-triages it: catch-up should resurface a thread that moved
            # since you last dealt with it.
            if raw.occurred_at > row.occurred_at:
                row.triaged = False
            row.occurred_at = raw.occurred_at
            updated += int(changed)

    gone = set(existing) - incoming
    if gone:
        await db.execute(delete(Item).where(Item.id.in_(gone)))
    await db.flush()
    return added, updated


async def _clear_stale_proposals(db: AsyncSession) -> None:
    """Proposals are the engine's to rebuild; decisions are not ours to touch."""
    await db.execute(delete(Link).where(Link.state == PROPOSED))
    await db.flush()


async def _propose(
    db: AsyncSession,
    raw: RawItem,
    tasks: list[TaskView],
    decided: dict[str, str],
) -> int:
    """Propose which existing tasks an item might belong to. Never creates a task.

    An item is not a task. It lives in the timeline and the catch-up inbox until the user
    attaches it to a task or promotes it into one. All the engine does is suggest existing
    tasks to attach it to; on a board with no tasks yet, it suggests nothing.
    """
    if any(state == CONFIRMED for state in decided.values()):
        # The user already placed this item. The engine has nothing to add.
        return 0

    candidates = [t for t in tasks if decided.get(t.id) != REJECTED]

    proposals = engine_registry.propose(raw, candidates)
    for proposal, source_engine in proposals:
        db.add(
            Link(
                task_id=proposal.task_id,
                item_id=raw.id,
                state=PROPOSED,
                engine=source_engine.id,
                confidence=proposal.confidence,
                reason=proposal.reason,
            )
        )
    await db.flush()
    return len(proposals)


async def _refresh_tasks(db: AsyncSession, by_id: dict[str, RawItem], matcher) -> int:
    """Recompute each task's title, status, tags and bucket from the items on it."""
    tasks = (await db.execute(select(Task))).scalars().all()
    updated = 0

    for task in tasks:
        attached = [by_id[item.id] for item in task.items if item.id in by_id]
        if not attached:
            continue

        lead = min(attached, key=lambda i: _rank(TITLE_PRIORITY, i.source))
        statuses = [i.status for i in attached if i.status]
        status = min(statuses, key=lambda s: _rank(STATUS_PRIORITY, s)) if statuses else task.status
        tags = sorted({tag for i in attached for tag in i.tags})
        newest = max(i.occurred_at for i in attached)

        changed = task.status != status
        if not task.title_override and task.title != lead.task_title():
            task.title = lead.task_title()
            changed = True
        task.status = status
        task.tags = tags
        if not task.bucket_override:
            task.bucket = matcher.assign(task.title, tags)
        # New activity on a read task makes it unread again — resurfacing subjects that
        # moved is the whole point of the board.
        if newest > task.updated_at:
            task.unread = True
            changed = True
        task.updated_at = newest
        task.synced_at = datetime.now(UTC)
        updated += int(changed)

    await db.flush()
    return updated


async def _purge_auto_tasks(db: AsyncSession) -> None:
    """Remove tasks a past sync auto-created.

    An item is not a task. Earlier syncs made one per homeless item; that was wrong, so
    those are cleared here. Their items keep their triaged flag, so anything you'd already
    dealt with stays dealt with, and the rest returns to catch-up. Manual tasks are yours
    and are never touched.
    """
    await db.execute(delete(Task).where(Task.origin == "auto"))
    await db.flush()


def _rank(order: list[str], value: str) -> int:
    try:
        return order.index(value)
    except ValueError:
        return len(order)


def _write_log(
    db: AsyncSession,
    outcomes: list[_FetchOutcome],
    result: _PersistResult,
    started_at: datetime,
    duration: float,
) -> None:
    errors = [f"{o.name}: {o.error}" for o in outcomes if o.error]
    db.add(
        SyncLog(
            started_at=started_at,
            finished_at=datetime.now(UTC),
            sources=[
                {
                    "source": o.name,
                    "kind": o.kind,
                    "items_fetched": len(o.items),
                    "configured": o.configured,
                    "error": o.error,
                }
                for o in outcomes
            ],
            items_fetched=sum(len(o.items) for o in outcomes),
            items_added=result.items_added,
            items_updated=result.items_updated,
            proposals=result.proposals,
            tasks_updated=result.tasks_updated,
            duration_seconds=duration,
            error="; ".join(errors) or None,
        )
    )
