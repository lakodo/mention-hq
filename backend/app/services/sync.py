"""Sync orchestration: fetch every source, group into tasks, persist.

Grouping runs across *all* sources at once, not per source — a PR only merges with its
Slack thread if both are on the table. So a partial sync (`source=github`) still reads the
other sources' stored mentions back out of the DB before regrouping.
"""

from __future__ import annotations

import time
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime

import structlog
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import Mention, SyncLog, Task, TaskMention
from app.schemas import SyncResult, SyncSourceResult
from app.services.buckets import load_matcher
from app.services.grouping import group_mentions
from app.services.links import Links, apply_overrides, load_overrides
from app.services.sources_factory import build_configured_sources
from app.sources.base import RawMention, Source

log = structlog.get_logger(__name__)

OWNER_BY_MENTION_SOURCE = {
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
    mentions: list[RawMention]
    error: str | None = None
    configured: bool = True

    @property
    def authoritative(self) -> bool:
        """Whether this run can be trusted to have the full picture for the source.

        A source that errored still has valid mentions in the DB from last time; dropping
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

    outcomes = [await _fetch(source) for source in sources]

    fetched: list[RawMention] = []
    for outcome in outcomes:
        fetched.extend(outcome.mentions)

    refreshed = {o.source_id for o in outcomes if o.authoritative}
    kept = await _stored_mentions_to_keep(db, refreshed)

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
            SyncSourceResult(source=o.source_id, mentions_fetched=len(o.mentions), error=o.error)
            for o in outcomes
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


def _merge(kept: list[RawMention], fetched: list[RawMention]) -> list[RawMention]:
    by_id = {m.id: m for m in kept}
    by_id.update({m.id: m for m in fetched})
    return list(by_id.values())


async def _stored_mentions_to_keep(db: AsyncSession, refreshed: set[str]) -> list[RawMention]:
    """Stored mentions from sources this run didn't authoritatively refresh.

    They're read back so grouping still sees every source at once: a partial `?source=github`
    sync must still be able to merge a PR with the Slack thread that references it.
    """
    rows = (await db.execute(select(Mention))).scalars().all()
    return [_row_to_raw(row) for row in rows if OWNER_BY_MENTION_SOURCE.get(row.source) not in refreshed]


def _row_to_raw(row: Mention) -> RawMention:
    return RawMention(
        source=row.source,
        external_id=row.id.split(":", 1)[1],
        label=row.label,
        occurred_at=row.occurred_at,
        url=row.url,
        context=row.context,
        identity_keys=set(row.extra.get("identity_keys", [])),
        reference_keys=set(row.extra.get("reference_keys", [])),
        extra=row.extra,
    )


async def _persist(db: AsyncSession, mentions: list[RawMention]) -> tuple[int, int]:
    grouped = group_mentions(mentions)

    await _upsert_mentions(db, mentions)

    auto_links: Links = defaultdict(set)
    for group in grouped:
        auto_links[group.id] = {m.id for m in group.mentions}

    attached, detached = await load_overrides(db)
    resolved = apply_overrides(auto_links, attached, detached)

    added, updated = await _upsert_tasks(db, grouped, resolved)
    await _rebuild_links(db, resolved, attached)
    await _drop_orphan_tasks(db, resolved)
    return added, updated


async def _upsert_mentions(db: AsyncSession, mentions: list[RawMention]) -> None:
    existing = {m.id: m for m in (await db.execute(select(Mention))).scalars().all()}
    incoming = {m.id for m in mentions}

    for raw in mentions:
        payload = {
            **raw.extra,
            "identity_keys": sorted(raw.identity_keys),
            "reference_keys": sorted(raw.reference_keys),
        }
        row = existing.get(raw.id)
        if row is None:
            db.add(
                Mention(
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
            # New activity un-triages it: the catch-up screen should resurface a thread
            # that moved since you last dealt with it.
            if raw.occurred_at > row.occurred_at:
                row.triaged = False
            row.occurred_at = raw.occurred_at

    gone = set(existing) - incoming
    if gone:
        await db.execute(delete(Mention).where(Mention.id.in_(gone)))
    await db.flush()


async def _upsert_tasks(db: AsyncSession, grouped, resolved: Links) -> tuple[int, int]:
    matcher = await load_matcher(db)
    existing = {t.id: t for t in (await db.execute(select(Task))).scalars().all()}
    added = updated = 0

    for group in grouped:
        if group.id not in resolved:
            continue
        bucket = matcher.assign(group.title, group.tags)
        task = existing.get(group.id)

        if task is None:
            db.add(
                Task(
                    id=group.id,
                    title=group.title,
                    bucket=bucket,
                    status=group.status,
                    tags=group.tags,
                    unread=True,
                    origin="auto",
                    updated_at=group.updated_at,
                    synced_at=datetime.now(UTC),
                )
            )
            added += 1
            continue

        changed = task.status != group.status
        if not task.title_override:
            changed = changed or task.title != group.title
            task.title = group.title
        task.status = group.status
        task.tags = sorted(set(task.tags) | set(group.tags)) if task.origin == "manual" else group.tags
        if not task.bucket_override:
            task.bucket = bucket
        # New activity on a read task makes it unread again — resurfacing subjects that
        # moved is the whole point of the board.
        if group.updated_at > task.updated_at:
            task.unread = True
            changed = True
        task.updated_at = group.updated_at
        task.synced_at = datetime.now(UTC)
        updated += int(changed)

    await db.flush()
    return added, updated


async def _rebuild_links(db: AsyncSession, resolved: Links, attached: Links) -> None:
    await db.execute(delete(TaskMention))
    await db.flush()

    known_tasks = {t.id for t in (await db.execute(select(Task))).scalars().all()}
    known_mentions = {m.id for m in (await db.execute(select(Mention))).scalars().all()}

    for task_id, mention_ids in resolved.items():
        if task_id not in known_tasks:
            continue
        for mention_id in mention_ids:
            # An override can name a mention that no longer exists (deleted PR, edited
            # todo). Skip rather than fail the whole sync on a dangling reference.
            if mention_id not in known_mentions:
                continue
            db.add(
                TaskMention(
                    task_id=task_id,
                    mention_id=mention_id,
                    linked_by="manual" if mention_id in attached.get(task_id, set()) else "auto",
                )
            )
    await db.flush()


async def _drop_orphan_tasks(db: AsyncSession, resolved: Links) -> None:
    """Auto tasks exist only to hold mentions; manual ones are the user's and stay."""
    rows = (await db.execute(select(Task))).scalars().all()
    orphans = [t.id for t in rows if t.origin == "auto" and not resolved.get(t.id)]
    if orphans:
        await db.execute(delete(Task).where(Task.id.in_(orphans)))


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
                    "mentions_fetched": len(o.mentions),
                    "configured": o.configured,
                    "error": o.error,
                }
                for o in outcomes
            ],
            mentions_fetched=sum(len(o.mentions) for o in outcomes),
            tasks_added=added,
            tasks_updated=updated,
            duration_seconds=duration,
            error="; ".join(errors) or None,
        )
    )
