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
from app.services.sources_factory import build_configured_sources
from app.sources.base import STATUS_PRIORITY, TITLE_PRIORITY, RawItem, Source

log = structlog.get_logger(__name__)

# A proposal this strong stands in for a task of the item's own. Below it, the item gets
# its own task and keeps the proposal as a suggestion — so a weak candidate is something to
# review, never something that hides an item until someone notices.
TRUSTED_ENOUGH_TO_HOME = 0.9

# Which source adapter owns each kind of item — "pr" and "issue" both come from GitHub.
OWNER_BY_ITEM_SOURCE = {
    "pr": "github",
    "issue": "github",
    "linear": "linear",
    "slack": "slack",
    "branch": "git",
    "todo": "todo",
    "markdown": "markdown",
    "dust": "dust",
}


@dataclass
class _FetchOutcome:
    source_id: str
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
    started_at = datetime.now(UTC)
    started = time.perf_counter()
    sources = await build_configured_sources(db, settings)
    if only is not None:
        sources = [s for s in sources if s.id == only]
        if not sources:
            raise ValueError(f"Unknown source: {only}")

    # Concurrently: these are independent network calls, and run in series the sync takes
    # as long as every source added together. _fetch never raises, so gather is safe.
    outcomes = list(await asyncio.gather(*(_fetch(source) for source in sources)))

    fetched: list[RawItem] = []
    for outcome in outcomes:
        fetched.extend(outcome.items)

    refreshed = {o.source_id for o in outcomes if o.authoritative}
    kept = await _stored_items_to_keep(db, refreshed)

    added, updated = await _persist(db, _merge(kept, fetched))

    duration = round(time.perf_counter() - started, 2)
    _write_log(db, outcomes, added, updated, started_at, duration)
    await db.commit()

    return SyncResult(
        sources_synced=[o.source_id for o in outcomes if o.authoritative],
        tasks_added=added,
        tasks_updated=updated,
        duration_seconds=duration,
        errors=[f"{o.source_id}: {o.error}" for o in outcomes if o.error],
        results=[
            SyncSourceResult(source=o.source_id, items_fetched=len(o.items), error=o.error) for o in outcomes
        ],
    )


async def _fetch(source: Source) -> _FetchOutcome:
    if not source.is_configured():
        return _FetchOutcome(source.id, [], configured=False)
    try:
        return _FetchOutcome(source.id, await source.fetch())
    except Exception as exc:  # one broken source must not fail the others
        log.warning("source_fetch_failed", source=source.id, error=str(exc))
        return _FetchOutcome(source.id, [], error=str(exc))


def _merge(kept: list[RawItem], fetched: list[RawItem]) -> list[RawItem]:
    by_id = {item.id: item for item in kept}
    by_id.update({item.id: item for item in fetched})
    return list(by_id.values())


async def _stored_items_to_keep(db: AsyncSession, refreshed: set[str]) -> list[RawItem]:
    rows = (await db.execute(select(Item))).scalars().all()
    return [_row_to_raw(row) for row in rows if OWNER_BY_ITEM_SOURCE.get(row.source) not in refreshed]


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


async def _persist(db: AsyncSession, items: list[RawItem]) -> tuple[int, int]:
    await _upsert_items(db, items)
    await _clear_stale_proposals(db)

    # Best title source first, then oldest first: whichever item ends up creating a task
    # should be the one that names it best.
    ordered = sorted(items, key=lambda i: (_rank(TITLE_PRIORITY, i.source), i.occurred_at))

    matcher = await load_matcher(db)
    # Read once and carry through the loop. Re-reading per item would be a query per item
    # against tables only this loop is writing to.
    decisions = await _decisions_by_item(db)
    views = await _task_views(db)

    added = 0
    for raw in ordered:
        created = await _route(db, raw, views, decisions.get(raw.id, {}), matcher)
        if created is not None:
            views.append(created)
            added += 1

    updated = await _refresh_tasks(db, {i.id: i for i in items}, matcher)
    await _drop_orphan_tasks(db)
    return added, updated


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


async def _upsert_items(db: AsyncSession, items: list[RawItem]) -> None:
    existing = {row.id: row for row in (await db.execute(select(Item))).scalars().all()}
    incoming = {item.id for item in items}

    for raw in items:
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
                    label=raw.label,
                    url=raw.url,
                    context=raw.context,
                    occurred_at=raw.occurred_at,
                    triaged=False,
                    first_seen_at=datetime.now(UTC),
                    extra=payload,
                )
            )
        else:
            row.label = raw.label
            row.url = raw.url
            row.context = raw.context
            row.extra = payload
            # New activity un-triages it: catch-up should resurface a thread that moved
            # since you last dealt with it.
            if raw.occurred_at > row.occurred_at:
                row.triaged = False
            row.occurred_at = raw.occurred_at

    gone = set(existing) - incoming
    if gone:
        await db.execute(delete(Item).where(Item.id.in_(gone)))
    await db.flush()


async def _clear_stale_proposals(db: AsyncSession) -> None:
    """Proposals are the engine's to rebuild; decisions are not ours to touch."""
    await db.execute(delete(Link).where(Link.state == PROPOSED))
    await db.flush()


async def _route(
    db: AsyncSession,
    raw: RawItem,
    tasks: list[TaskView],
    decided: dict[str, str],
    matcher,
) -> TaskView | None:
    """Send one item through the engine. Returns a view of the task it created, if any."""
    if any(state == CONFIRMED for state in decided.values()):
        # The user already placed this item. The engine has nothing to add.
        return None

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

    if any(p.confidence >= TRUSTED_ENOUGH_TO_HOME for p, _ in proposals):
        return None

    # Every other case gives the item a task of its own: a weak proposal is a suggestion,
    # not a home. Rejecting a link likewise says "not this task", not "not anywhere".
    return await _create_task_for(db, raw, matcher)


async def _create_task_for(db: AsyncSession, raw: RawItem, matcher) -> Task:
    title = raw.task_title()
    task = Task(
        id=raw.id,
        title=title,
        bucket=matcher.assign(title, raw.tags),
        status=raw.status or "open",
        tags=sorted(raw.tags),
        unread=True,
        origin="auto",
        updated_at=raw.occurred_at,
        synced_at=datetime.now(UTC),
    )
    db.add(task)
    await db.flush()
    # An item that had to invent a task obviously belongs to it — that isn't a guess.
    db.add(
        Link(
            task_id=task.id,
            item_id=raw.id,
            state=CONFIRMED,
            engine=None,
            confidence=1.0,
            reason="This item created the task",
            decided_at=datetime.now(UTC),
        )
    )
    await db.flush()
    return TaskView(
        id=task.id,
        title=task.title,
        identity_keys=frozenset(raw.identity_keys),
        reference_keys=frozenset(raw.reference_keys),
    )


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


async def _drop_orphan_tasks(db: AsyncSession) -> None:
    """Auto tasks exist only to hold items; manual ones are yours and stay."""
    tasks = (await db.execute(select(Task))).scalars().all()
    orphans = [t.id for t in tasks if t.origin == "auto" and not t.items]
    if orphans:
        await db.execute(delete(Task).where(Task.id.in_(orphans)))
        await db.flush()


def _rank(order: list[str], value: str) -> int:
    try:
        return order.index(value)
    except ValueError:
        return len(order)


def _write_log(
    db: AsyncSession,
    outcomes: list[_FetchOutcome],
    added: int,
    updated: int,
    started_at: datetime,
    duration: float,
) -> None:
    errors = [f"{o.source_id}: {o.error}" for o in outcomes if o.error]
    db.add(
        SyncLog(
            started_at=started_at,
            finished_at=datetime.now(UTC),
            sources=[
                {
                    "source": o.source_id,
                    "items_fetched": len(o.items),
                    "configured": o.configured,
                    "error": o.error,
                }
                for o in outcomes
            ],
            items_fetched=sum(len(o.items) for o in outcomes),
            tasks_added=added,
            tasks_updated=updated,
            duration_seconds=duration,
            error="; ".join(errors) or None,
        )
    )
