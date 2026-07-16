"""End-to-end sync: fetch → group → persist, and the guarantees around re-syncing."""

from __future__ import annotations

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import Settings
from app.models import Bucket, Mention, Task, TaskMention
from app.services import sync as sync_module
from app.services.sync import sync_all
from app.sources.base import RawMention, Source


class FakeSource(Source):
    id = "github"
    name = "Fake GitHub"

    def __init__(self, mentions: list[RawMention], fail: bool = False) -> None:
        super().__init__({})
        self._mentions = mentions
        self._fail = fail

    def is_configured(self) -> bool:
        return True

    async def fetch(self) -> list[RawMention]:
        if self._fail:
            raise RuntimeError("GitHub is down")
        return self._mentions


@pytest.fixture
def settings() -> Settings:
    return Settings(database_url="sqlite+aiosqlite:///:memory:")


@pytest.fixture
def use_sources(monkeypatch):
    def _install(*sources):
        async def fake_build(db, settings):
            return list(sources)

        monkeypatch.setattr(sync_module, "build_configured_sources", fake_build)

    return _install


async def test_sync_creates_a_task_per_group(db, settings, use_sources, mention):
    use_sources(FakeSource([mention("pr", "r#1", title="Add webhook handler"), mention("todo", "t1")]))

    result = await sync_all(db, settings)

    assert result.tasks_added == 2
    tasks = (await db.execute(select(Task))).scalars().all()
    assert {t.title for t in tasks} == {"Add webhook handler", "todo t1"}


async def test_linked_mentions_land_on_one_task(db, settings, use_sources, mention):
    use_sources(
        FakeSource(
            [
                mention("linear", "1", identity_keys={"PAY-88"}, title="Refund bug"),
                mention("slack", "C1:1", reference_keys={"PAY-88"}),
            ]
        )
    )

    await sync_all(db, settings)

    tasks = (await db.execute(select(Task))).scalars().all()
    assert len(tasks) == 1
    assert len(tasks[0].mentions) == 2


async def test_new_tasks_start_unread(db, settings, use_sources, mention):
    use_sources(FakeSource([mention("pr", "r#1")]))
    await sync_all(db, settings)

    task = (await db.execute(select(Task))).scalars().one()
    assert task.unread is True


async def test_resync_is_idempotent(db, settings, use_sources, mention):
    source = FakeSource([mention("pr", "r#1", title="Add webhook handler")])
    use_sources(source)

    await sync_all(db, settings)
    second = await sync_all(db, settings)

    assert second.tasks_added == 0
    assert len((await db.execute(select(Task))).scalars().all()) == 1


async def test_manual_bucket_survives_resync(db, settings, use_sources, mention):
    db.add(Bucket(name="Payments", keywords=["payments"], position=1))
    await db.flush()
    use_sources(FakeSource([mention("pr", "r#1", title="Something unmatched")]))
    await sync_all(db, settings)

    task = (await db.execute(select(Task))).scalars().one()
    task.bucket = "Payments"
    task.bucket_override = True
    await db.commit()

    await sync_all(db, settings)
    await db.refresh(task)
    assert task.bucket == "Payments"


async def test_read_task_becomes_unread_when_a_mention_moves(db, settings, use_sources, mention, now):
    use_sources(FakeSource([mention("pr", "r#1", occurred_at=now - timedelta(hours=2))]))
    await sync_all(db, settings)

    task = (await db.execute(select(Task))).scalars().one()
    task.unread = False
    await db.commit()

    use_sources(FakeSource([mention("pr", "r#1", occurred_at=now)]))
    await sync_all(db, settings)

    await db.refresh(task)
    assert task.unread is True, "new activity must resurface the task"


async def test_a_failing_source_does_not_erase_its_stored_mentions(db, settings, use_sources, mention):
    """A GitHub 500 must not empty the board."""
    use_sources(FakeSource([mention("pr", "r#1", title="Add webhook handler")]))
    await sync_all(db, settings)

    use_sources(FakeSource([], fail=True))
    result = await sync_all(db, settings)

    assert result.errors
    assert len((await db.execute(select(Task))).scalars().all()) == 1


async def test_vanished_mention_drops_its_auto_task(db, settings, use_sources, mention):
    use_sources(FakeSource([mention("pr", "r#1")]))
    await sync_all(db, settings)

    use_sources(FakeSource([]))
    await sync_all(db, settings)

    assert (await db.execute(select(Task))).scalars().all() == []
    assert (await db.execute(select(Mention))).scalars().all() == []


async def test_manual_task_outlives_its_mentions(db, settings, use_sources, mention):
    from datetime import UTC, datetime

    db.add(
        Task(
            id="task:manual",
            title="Mine",
            bucket="Uncategorized",
            status="open",
            tags=[],
            unread=False,
            origin="manual",
            updated_at=datetime.now(UTC),
        )
    )
    await db.flush()

    use_sources(FakeSource([]))
    await sync_all(db, settings)

    assert await db.get(Task, "task:manual") is not None


async def test_manual_attach_survives_resync(db, settings, use_sources, mention):
    """The core promise: sync rebuilds its own guesses, never the user's decisions."""
    from app.services.links import ATTACH, record_override

    use_sources(FakeSource([mention("pr", "r#1", title="A"), mention("todo", "t1", title="B")]))
    await sync_all(db, settings)

    task_a = (await db.execute(select(Task).where(Task.title == "A"))).scalars().one()
    await record_override(db, "todo:t1", task_a.id, ATTACH)
    await db.commit()

    await sync_all(db, settings)

    links = (await db.execute(select(TaskMention).where(TaskMention.task_id == task_a.id))).scalars().all()
    # "r#1" becomes "r~1": ids are made URL-safe at construction (see url_safe).
    assert {link.mention_id for link in links} == {"pr:r~1", "todo:t1"}


async def test_detach_is_not_undone_by_resync(db, settings, use_sources, mention):
    from app.services.links import DETACH, record_override

    use_sources(
        FakeSource(
            [
                mention("linear", "1", identity_keys={"PAY-88"}, title="Refund bug"),
                mention("slack", "C1:1", reference_keys={"PAY-88"}),
            ]
        )
    )
    await sync_all(db, settings)
    task = (await db.execute(select(Task))).scalars().one()

    await record_override(db, "slack:C1:1", task.id, DETACH)
    await db.commit()
    await sync_all(db, settings)

    await db.refresh(task)
    assert {m.id for m in task.mentions} == {"linear:1"}


async def test_sync_writes_one_log_row_per_run(db, settings, use_sources, mention):
    from app.models import SyncLog

    use_sources(FakeSource([mention("pr", "r#1")]))
    await sync_all(db, settings)

    logs = (await db.execute(select(SyncLog))).scalars().all()
    assert len(logs) == 1, "one row per run, not per source"
    assert logs[0].error is None
    assert logs[0].tasks_added == 1
    assert logs[0].sources == [{"source": "github", "mentions_fetched": 1, "configured": True, "error": None}]


async def test_sync_log_records_a_source_error_without_failing_the_run(db, settings, use_sources):
    from app.models import SyncLog

    use_sources(FakeSource([], fail=True))
    await sync_all(db, settings)

    log = (await db.execute(select(SyncLog))).scalars().one()
    assert "GitHub is down" in log.error
    assert log.sources[0]["error"] == "GitHub is down"


async def test_unknown_source_is_rejected(db, settings, use_sources, mention):
    use_sources(FakeSource([]))
    with pytest.raises(ValueError, match="Unknown source"):
        await sync_all(db, settings, only="nope")
