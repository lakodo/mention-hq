"""End-to-end sync: fetch, route through the engine, persist.

The promise under test is the one the user relies on: an engine may guess as often as it
likes, but a decision, once made, is never undone by a later sync.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.config import Settings
from app.models import CONFIRMED, PROPOSED, REJECTED, Bucket, Item, Link, SyncLog, Task
from app.services import sync as sync_module
from app.services.sync import sync_all
from app.sources.base import RawItem, Source


class FakeSource(Source):
    id = "github"
    name = "Fake GitHub"

    def __init__(self, items: list[RawItem], fail: bool = False) -> None:
        super().__init__({})
        self._items = items
        self._fail = fail

    def is_configured(self) -> bool:
        return True

    async def fetch(self) -> list[RawItem]:
        if self._fail:
            raise RuntimeError("GitHub is down")
        return self._items


@pytest.fixture
def settings() -> Settings:
    return Settings(db_path=":memory:")


@pytest.fixture
def use_sources(monkeypatch):
    def _install(*sources):
        async def fake_build(db, settings):
            return list(sources)

        monkeypatch.setattr(sync_module, "build_configured_sources", fake_build)

    return _install


async def _tasks(db) -> list[Task]:
    return list((await db.execute(select(Task))).scalars().all())


async def _links(db) -> list[Link]:
    return list((await db.execute(select(Link))).scalars().all())


async def test_an_item_with_no_home_creates_its_own_task(db, settings, use_sources, item):
    use_sources(FakeSource([item("pr", "r~1", title="Add webhook handler"), item("todo", "t1")]))

    result = await sync_all(db, settings)

    assert result.tasks_added == 2
    assert {t.title for t in await _tasks(db)} == {"Add webhook handler", "todo t1"}


async def test_the_item_that_creates_a_task_is_confirmed_on_it(db, settings, use_sources, item):
    """That attachment isn't a guess, so it isn't presented as one."""
    use_sources(FakeSource([item("pr", "r~1", title="Add webhook handler")]))
    await sync_all(db, settings)

    link = (await _links(db))[0]
    assert link.state == CONFIRMED
    assert link.engine is None


async def test_a_referencing_item_is_proposed_not_attached(db, settings, use_sources, item):
    use_sources(
        FakeSource(
            [
                item("linear", "1", identity_keys={"PAY-88"}, title="Refund bug"),
                item("slack", "C1:1", reference_keys={"PAY-88"}),
            ]
        )
    )

    await sync_all(db, settings)

    proposed = [link for link in await _links(db) if link.item_id == "slack:C1:1"]
    assert len(proposed) == 1
    assert proposed[0].state == PROPOSED
    assert proposed[0].engine == "keys"
    assert proposed[0].confidence == 0.9
    assert "PAY-88" in proposed[0].reason


async def test_a_proposal_does_not_spawn_a_competing_task(db, settings, use_sources, item):
    use_sources(
        FakeSource(
            [
                item("linear", "1", identity_keys={"PAY-88"}, title="Refund bug"),
                item("slack", "C1:1", reference_keys={"PAY-88"}),
            ]
        )
    )
    await sync_all(db, settings)

    assert len(await _tasks(db)) == 1


async def test_an_item_the_engine_has_no_opinion_on_gets_its_own_task(db, settings, use_sources, item):
    use_sources(
        FakeSource(
            [
                item("linear", "1", identity_keys={"PAY-88"}, title="Refund bug"),
                item("todo", "t1", label="Renew domain for personal site"),
            ]
        )
    )
    await sync_all(db, settings)

    assert len(await _tasks(db)) == 2


async def test_proposals_are_rebuilt_every_sync(db, settings, use_sources, item):
    """An engine may change its mind, so its guesses are not persisted state."""
    use_sources(
        FakeSource(
            [
                item("linear", "1", identity_keys={"PAY-88"}, title="Refund bug"),
                item("slack", "C1:1", reference_keys={"PAY-88"}),
            ]
        )
    )
    await sync_all(db, settings)
    await sync_all(db, settings)

    proposed = [link for link in await _links(db) if link.state == PROPOSED]
    assert len(proposed) == 1, "the same proposal must not accumulate"


async def test_a_confirmed_link_survives_resync(db, settings, use_sources, item):
    from app.services import catchup

    use_sources(FakeSource([item("pr", "r~1", title="A"), item("todo", "t1", label="Totally other")]))
    await sync_all(db, settings)

    task_a = (await db.execute(select(Task).where(Task.title == "A"))).scalars().one()
    await catchup.confirm(db, "todo:t1", [task_a.id])

    await sync_all(db, settings)

    link = await db.get(Link, {"task_id": task_a.id, "item_id": "todo:t1"})
    assert link is not None
    assert link.state == CONFIRMED


async def test_a_rejected_link_is_never_proposed_again(db, settings, use_sources, item):
    from app.services import catchup

    use_sources(
        FakeSource(
            [
                item("linear", "1", identity_keys={"PAY-88"}, title="Refund bug"),
                item("slack", "C1:1", reference_keys={"PAY-88"}),
            ]
        )
    )
    await sync_all(db, settings)
    task = (await db.execute(select(Task).where(Task.title == "Refund bug"))).scalars().one()

    await catchup.reject(db, "slack:C1:1", task.id)
    await sync_all(db, settings)

    link = await db.get(Link, {"task_id": task.id, "item_id": "slack:C1:1"})
    assert link.state == REJECTED, "a dismissed guess must not come back"


async def test_a_rejected_item_falls_back_to_its_own_task(db, settings, use_sources, item):
    """Rejecting a link means "not this task", not "not anywhere" — the item still exists."""
    from app.services import catchup

    use_sources(
        FakeSource(
            [
                item("linear", "1", identity_keys={"PAY-88"}, title="Refund bug"),
                item("slack", "C1:1", reference_keys={"PAY-88"}),
            ]
        )
    )
    await sync_all(db, settings)
    task = (await db.execute(select(Task).where(Task.title == "Refund bug"))).scalars().one()
    await catchup.reject(db, "slack:C1:1", task.id)

    await sync_all(db, settings)

    titles = {t.title for t in await _tasks(db)}
    assert len(titles) == 2, "the rejected item must not vanish from the board"
    assert "slack C1:1" in titles


async def test_new_tasks_start_unread(db, settings, use_sources, item):
    use_sources(FakeSource([item("pr", "r~1")]))
    await sync_all(db, settings)
    assert (await _tasks(db))[0].unread is True


async def test_resync_is_idempotent(db, settings, use_sources, item):
    use_sources(FakeSource([item("pr", "r~1", title="Add webhook handler")]))
    await sync_all(db, settings)
    second = await sync_all(db, settings)

    assert second.tasks_added == 0
    assert len(await _tasks(db)) == 1


async def test_manual_bucket_survives_resync(db, settings, use_sources, item):
    db.add(Bucket(name="Payments", keywords=["payments"], position=1))
    await db.flush()
    use_sources(FakeSource([item("pr", "r~1", title="Something unmatched")]))
    await sync_all(db, settings)

    task = (await _tasks(db))[0]
    task.bucket = "Payments"
    task.bucket_override = True
    await db.commit()

    await sync_all(db, settings)
    await db.refresh(task)
    assert task.bucket == "Payments"


async def test_keywords_assign_a_bucket(db, settings, use_sources, item):
    db.add(Bucket(name="Payments", keywords=["refund"], position=1))
    await db.flush()
    use_sources(FakeSource([item("pr", "r~1", title="Refund flow throws")]))

    await sync_all(db, settings)
    assert (await _tasks(db))[0].bucket == "Payments"


async def test_read_task_becomes_unread_when_an_item_moves(db, settings, use_sources, item, now):
    use_sources(FakeSource([item("pr", "r~1", occurred_at=now - timedelta(hours=2))]))
    await sync_all(db, settings)

    task = (await _tasks(db))[0]
    task.unread = False
    await db.commit()

    use_sources(FakeSource([item("pr", "r~1", occurred_at=now)]))
    await sync_all(db, settings)

    await db.refresh(task)
    assert task.unread is True, "new activity must resurface the task"


async def test_a_failing_source_does_not_erase_its_stored_items(db, settings, use_sources, item):
    """A GitHub 500 must not empty the board."""
    use_sources(FakeSource([item("pr", "r~1", title="Add webhook handler")]))
    await sync_all(db, settings)

    use_sources(FakeSource([], fail=True))
    result = await sync_all(db, settings)

    assert result.errors
    assert len(await _tasks(db)) == 1


async def test_vanished_item_drops_its_auto_task(db, settings, use_sources, item):
    use_sources(FakeSource([item("pr", "r~1")]))
    await sync_all(db, settings)

    use_sources(FakeSource([]))
    await sync_all(db, settings)

    assert await _tasks(db) == []
    assert (await db.execute(select(Item))).scalars().all() == []


async def test_manual_task_outlives_its_items(db, settings, use_sources, item):
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


async def test_task_takes_the_title_of_its_best_source(db, settings, use_sources, item):
    """A Linear issue names a subject; a Slack message does not."""
    use_sources(
        FakeSource(
            [
                item("slack", "C1:1", label="can someone look at this?", identity_keys={"PAY-88"}),
                item("linear", "1", identity_keys={"PAY-88"}, title="Refund flow throws"),
            ]
        )
    )
    await sync_all(db, settings)

    assert (await _tasks(db))[0].title == "Refund flow throws"


async def test_sync_writes_one_log_row_per_run(db, settings, use_sources, item):
    use_sources(FakeSource([item("pr", "r~1")]))
    await sync_all(db, settings)

    logs = (await db.execute(select(SyncLog))).scalars().all()
    assert len(logs) == 1, "one row per run, not per source"
    assert logs[0].error is None
    assert logs[0].tasks_added == 1
    assert logs[0].sources == [{"source": "github", "items_fetched": 1, "configured": True, "error": None}]


async def test_sync_log_records_a_source_error_without_failing_the_run(db, settings, use_sources):
    use_sources(FakeSource([], fail=True))
    await sync_all(db, settings)

    log = (await db.execute(select(SyncLog))).scalars().one()
    assert "GitHub is down" in log.error
    assert log.sources[0]["error"] == "GitHub is down"


async def test_unknown_source_is_rejected(db, settings, use_sources, item):
    use_sources(FakeSource([]))
    with pytest.raises(ValueError, match="Unknown source"):
        await sync_all(db, settings, only="nope")


async def test_a_weak_candidate_does_not_hide_the_item(db, settings, use_sources, item):
    """A title lookalike is a suggestion to review, not a home."""
    use_sources(
        FakeSource(
            [
                item("todo", "t1", label="Bump lodash in the api package"),
                item("pr", "r~1", title="Bump lodash in the web package"),
            ]
        )
    )
    await sync_all(db, settings)

    titles = {t.title for t in await _tasks(db)}
    assert titles == {"Bump lodash in the api package", "Bump lodash in the web package"}, (
        "each item keeps a task of its own"
    )

    proposed = [link for link in await _links(db) if link.state == PROPOSED]
    assert proposed, "and the lookalike still surfaces as a candidate to review"


async def test_a_ticket_reference_is_trusted_to_home_an_item(db, settings, use_sources, item):
    use_sources(
        FakeSource(
            [
                item("linear", "1", identity_keys={"ENG-42"}, title="Refund bug"),
                item("slack", "C1:1", reference_keys={"ENG-42"}),
            ]
        )
    )
    await sync_all(db, settings)

    assert len(await _tasks(db)) == 1, "an explicit reference is strong enough to attach to"
