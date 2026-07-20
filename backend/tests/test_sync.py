"""Sync: fetch, upsert items, propose against existing tasks.

The model this pins: an item is not a task. A sync brings items in and, at most, proposes
attaching them to tasks that already exist. It never creates a task. Tasks are the user's —
made by hand or by promoting an item in catch-up — and a sync never invents one.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.config import Settings
from app.models import CONFIRMED, PROPOSED, REJECTED, Item, Link, SourceInstance, SyncLog, Task
from app.services import sync as sync_module
from app.services.sources_factory import Connected
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
    def _install(*sources, name: str = "GitHub"):
        connected = [
            Connected(
                instance=SourceInstance(
                    id=f"github-{index}", kind="github", name=f"{name} {index}", position=index
                ),
                source=source,
            )
            for index, source in enumerate(sources)
        ]

        async def fake_build(db):
            return connected

        monkeypatch.setattr(sync_module, "build_connected", fake_build)

    return _install


async def _tasks(db) -> list[Task]:
    return list((await db.execute(select(Task))).scalars().all())


async def _items(db) -> list[Item]:
    return list((await db.execute(select(Item))).scalars().all())


async def _links(db) -> list[Link]:
    return list((await db.execute(select(Link))).scalars().all())


async def seed_task(db, task_id: str, title: str) -> Task:
    """A task the user made by hand."""
    task = Task(
        id=task_id,
        title=title,
        bucket="Uncategorized",
        status="open",
        tags=[],
        unread=False,
        origin="manual",
        title_override=True,
        updated_at=datetime.now(UTC),
    )
    db.add(task)
    await db.flush()
    return task


async def attach(db, task_id: str, item_id: str, source: str, *, identity=(), reference=()) -> Item:
    """Put an item on a task with a confirmed link, so the task carries its keys."""
    item = Item(
        id=item_id,
        source=source,
        label=item_id,
        url=None,
        context=None,
        occurred_at=datetime.now(UTC),
        extra={"identity_keys": list(identity), "reference_keys": list(reference)},
    )
    db.add(item)
    db.add(Link(task_id=task_id, item_id=item_id, state=CONFIRMED))
    await db.flush()
    return item


# --- an item is not a task -------------------------------------------------------------


async def test_a_sync_brings_items_not_tasks(db, settings, use_sources, item):
    use_sources(FakeSource([item("pr", "acme~api~1", title="Add webhook handler"), item("todo", "t1")]))

    result = await sync_all(db, settings)

    assert result.items_added == 2
    assert len(await _items(db)) == 2
    assert await _tasks(db) == [], "a fresh import creates no tasks"


async def test_a_homeless_item_waits_in_catch_up(db, settings, use_sources, item):
    use_sources(FakeSource([item("pr", "acme~api~1", title="Nothing matches this")]))

    await sync_all(db, settings)

    only = (await _items(db))[0]
    assert only.triaged is False, "it sits untriaged until you deal with it"
    assert await _links(db) == [], "and belongs to no task"


async def test_a_legacy_auto_task_is_purged(db, settings, use_sources, item):
    """Earlier syncs made a task per item; those are cleared, and the item returns."""
    db.add(
        Task(
            id="pr:acme~api~1",
            title="Add webhook handler",
            bucket="Uncategorized",
            status="open",
            tags=[],
            unread=True,
            origin="auto",
            updated_at=datetime.now(UTC),
        )
    )
    await db.flush()
    use_sources(FakeSource([item("pr", "acme~api~1", title="Add webhook handler")]))

    await sync_all(db, settings)

    assert await _tasks(db) == []
    assert len(await _items(db)) == 1


async def test_a_sync_keeps_an_item_attached_to_a_task_the_source_dropped(db, settings, use_sources, item):
    """A merged PR falls out of the source's is:open search, but it's filed on a task — keep it."""
    await seed_task(db, "task:webhooks", "Webhook work")
    await attach(db, "task:webhooks", "pr:acme~api~1", "pr")
    use_sources(FakeSource([item("pr", "acme~api~2", title="Something else")]))

    await sync_all(db, settings)

    ids = {i.id for i in await _items(db)}
    assert "pr:acme~api~1" in ids, "an attached item survives the source no longer returning it"
    assert any(link.item_id == "pr:acme~api~1" for link in await _links(db)), "its attachment stays"


async def test_a_sync_clears_an_unattached_item_the_source_dropped(db, settings, use_sources, item):
    """The counterpart: an item nobody filed is cleared when the source stops returning it."""
    use_sources(FakeSource([item("pr", "acme~api~1", title="Ephemeral")]))
    await sync_all(db, settings)
    assert "pr:acme~api~1" in {i.id for i in await _items(db)}

    use_sources(FakeSource([item("pr", "acme~api~2", title="Replacement")]))
    await sync_all(db, settings)

    assert "pr:acme~api~1" not in {i.id for i in await _items(db)}


async def test_a_sync_does_not_create_a_new_refresh_only_item(db, settings, use_sources, item):
    """A merged PR you never filed shouldn't flood catch-up — refresh-only is update-or-skip."""
    use_sources(FakeSource([item("pr", "acme~api~9", title="Merged, never seen", refresh_only=True)]))

    await sync_all(db, settings)

    assert await _items(db) == []


async def test_a_sync_refreshes_an_attached_item_from_a_refresh_only_fetch(db, settings, use_sources, item):
    """An attached PR that merges is refreshed (kept, restated), never deleted."""
    await seed_task(db, "task:webhooks", "Webhook work")
    await attach(db, "task:webhooks", "pr:acme~api~1", "pr")
    use_sources(
        FakeSource([item("pr", "acme~api~1", label="Now merged", status="merged", refresh_only=True)])
    )

    await sync_all(db, settings)

    items = await _items(db)
    assert {i.id for i in items} == {"pr:acme~api~1"}, "the attached item stays"
    assert items[0].label == "Now merged", "and is refreshed from the merged fetch"
    assert items[0].extra["status"] == "merged"


# --- proposing against existing tasks --------------------------------------------------


async def test_an_item_is_proposed_against_a_task_that_shares_its_key(db, settings, use_sources, item):
    await seed_task(db, "task:refunds", "Refund bug")
    await attach(db, "task:refunds", "linear:1", "linear", identity=["ENG-42"])
    await db.commit()

    use_sources(FakeSource([item("slack", "C1:1", reference_keys={"ENG-42"})]))
    await sync_all(db, settings)

    proposed = [link for link in await _links(db) if link.state == PROPOSED]
    assert len(proposed) == 1
    assert proposed[0].task_id == "task:refunds"
    assert proposed[0].engine == "keys"
    assert "ENG-42" in proposed[0].reason


async def test_an_item_is_proposed_against_a_task_with_a_similar_title(db, settings, use_sources, item):
    await seed_task(db, "task:ci", "Migrate CI to the new runner pool")
    await db.commit()

    use_sources(FakeSource([item("branch", "repo:owner~ci-runner-pool", title="Migrate CI runner pool")]))
    await sync_all(db, settings)

    proposed = [link for link in await _links(db) if link.state == PROPOSED]
    assert len(proposed) == 1
    assert proposed[0].engine == "title-similarity"


async def test_with_no_tasks_yet_nothing_is_proposed(db, settings, use_sources, item):
    use_sources(FakeSource([item("pr", "acme~api~1", title="Add webhook handler")]))
    await sync_all(db, settings)

    assert await _links(db) == []


async def test_proposals_are_rebuilt_every_sync(db, settings, use_sources, item):
    await seed_task(db, "task:refunds", "Refund bug")
    await attach(db, "task:refunds", "linear:1", "linear", identity=["ENG-42"])
    await db.commit()
    use_sources(FakeSource([item("slack", "C1:1", reference_keys={"ENG-42"})]))

    await sync_all(db, settings)
    await sync_all(db, settings)

    proposed = [link for link in await _links(db) if link.state == PROPOSED]
    assert len(proposed) == 1, "the same proposal must not accumulate"


# --- decisions are untouchable ---------------------------------------------------------


async def test_a_confirmed_link_survives_resync(db, settings, use_sources, item):
    from app.services import catchup

    await seed_task(db, "task:mine", "Something I track")
    await db.commit()
    use_sources(FakeSource([item("pr", "acme~api~1", title="A PR")]))
    await sync_all(db, settings)

    await catchup.confirm(db, "pr:acme~api~1", ["task:mine"])
    await sync_all(db, settings)

    link = await db.get(Link, {"task_id": "task:mine", "item_id": "pr:acme~api~1"})
    assert link is not None
    assert link.state == CONFIRMED


async def test_a_rejected_link_is_never_proposed_again(db, settings, use_sources, item):
    from app.services import catchup

    await seed_task(db, "task:refunds", "Refund bug")
    await attach(db, "task:refunds", "linear:1", "linear", identity=["ENG-42"])
    await db.commit()
    use_sources(FakeSource([item("slack", "C1:1", reference_keys={"ENG-42"})]))
    await sync_all(db, settings)

    await catchup.reject(db, "slack:C1:1", "task:refunds")
    await sync_all(db, settings)

    link = await db.get(Link, {"task_id": "task:refunds", "item_id": "slack:C1:1"})
    assert link.state == REJECTED


async def test_a_manual_task_is_never_purged(db, settings, use_sources, item):
    await seed_task(db, "task:mine", "Mine to keep")
    await db.commit()
    use_sources(FakeSource([]))

    await sync_all(db, settings)

    assert await db.get(Task, "task:mine") is not None


# --- refreshing a task from its items --------------------------------------------------


async def test_a_task_status_follows_the_items_on_it(db, settings, use_sources, item):
    await seed_task(db, "task:pr", "Tracking a PR")
    await attach(db, "task:pr", "pr:acme~api~1", "pr")
    await db.commit()

    use_sources(FakeSource([item("pr", "acme~api~1", title="A PR", status="merged")]))
    await sync_all(db, settings)

    refreshed = await db.get(Task, "task:pr")
    await db.refresh(refreshed)
    assert refreshed.status == "merged"


# --- items -----------------------------------------------------------------------------


async def test_a_vanished_item_is_removed(db, settings, use_sources, item):
    use_sources(FakeSource([item("pr", "acme~api~1")]))
    await sync_all(db, settings)

    use_sources(FakeSource([]))
    await sync_all(db, settings)

    assert await _items(db) == []


async def test_a_new_item_un_triages_when_it_moves(db, settings, use_sources, item, now):
    use_sources(FakeSource([item("pr", "acme~api~1", occurred_at=now - timedelta(hours=2))]))
    await sync_all(db, settings)

    stored = (await _items(db))[0]
    stored.triaged = True
    await db.commit()

    use_sources(FakeSource([item("pr", "acme~api~1", occurred_at=now)]))
    await sync_all(db, settings)

    assert (await _items(db))[0].triaged is False


async def test_new_activity_does_not_un_triage_an_item_you_have_attached(
    db, settings, use_sources, item, now
):
    """A branch you filed keeps gathering commits; that must not drag it back to catch-up."""
    await seed_task(db, "task:vera", "Vera")
    await attach(db, "task:vera", "branch:apps~vera", "branch")
    stored = (await _items(db))[0]
    stored.triaged = True
    stored.occurred_at = now - timedelta(hours=2)
    await db.commit()

    use_sources(FakeSource([item("branch", "apps~vera", occurred_at=now)]))
    await sync_all(db, settings)

    refreshed = (await _items(db))[0]
    assert refreshed.triaged is True, (
        "an attached item that moves stays filed — it doesn't re-enter the inbox"
    )
    assert any(link.item_id == "branch:apps~vera" for link in await _links(db)), "and it stays attached"


# --- several accounts of one kind ------------------------------------------------------


async def test_two_accounts_both_bring_their_items(db, settings, use_sources, item):
    use_sources(
        FakeSource([item("pr", "acme~api~1", title="Work PR")]),
        FakeSource([item("pr", "me~blog~2", title="Weekend PR")]),
    )
    await sync_all(db, settings)

    assert {i.id for i in await _items(db)} == {"pr:acme~api~1", "pr:me~blog~2"}


async def test_each_item_records_which_account_fetched_it(db, settings, use_sources, item):
    use_sources(
        FakeSource([item("pr", "acme~api~1")]),
        FakeSource([item("pr", "me~blog~2")]),
    )
    await sync_all(db, settings)

    owners = {i.id: i.instance_id for i in await _items(db)}
    assert owners == {"pr:acme~api~1": "github-0", "pr:me~blog~2": "github-1"}


async def test_one_account_failing_keeps_the_others_items(db, settings, use_sources, item):
    work = FakeSource([item("pr", "acme~api~1")])
    personal = FakeSource([item("pr", "me~blog~2")])
    use_sources(work, personal)
    await sync_all(db, settings)

    use_sources(FakeSource([], fail=True), personal)
    result = await sync_all(db, settings)

    assert result.errors
    assert {i.id for i in await _items(db)} == {"pr:acme~api~1", "pr:me~blog~2"}


async def test_a_failing_source_keeps_its_stored_items(db, settings, use_sources, item):
    use_sources(FakeSource([item("pr", "acme~api~1")]))
    await sync_all(db, settings)

    use_sources(FakeSource([], fail=True))
    await sync_all(db, settings)

    assert len(await _items(db)) == 1


# --- reporting -------------------------------------------------------------------------


async def test_the_result_counts_items_and_proposals(db, settings, use_sources, item):
    await seed_task(db, "task:refunds", "Refund bug")
    await attach(db, "task:refunds", "linear:1", "linear", identity=["ENG-42"])
    await db.commit()
    use_sources(
        FakeSource([item("slack", "C1:1", reference_keys={"ENG-42"}), item("todo", "t1", label="loose end")])
    )

    result = await sync_all(db, settings)

    assert result.items_added == 2
    assert result.proposals == 1


async def test_sync_writes_one_log_row_per_run(db, settings, use_sources, item):
    use_sources(FakeSource([item("pr", "acme~api~1")]))
    await sync_all(db, settings)

    logs = (await db.execute(select(SyncLog))).scalars().all()
    assert len(logs) == 1
    assert logs[0].error is None
    assert logs[0].items_added == 1
    assert logs[0].sources == [
        {"source": "GitHub 0", "kind": "github", "items_fetched": 1, "configured": True, "error": None}
    ]


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


class TestDrainMatching:
    """The drain loop that "Match all" runs, exercised without the brain or a database.

    _match_candidates, _match_one and _count_unmatched are stubbed so the test is about the
    orchestration: does a drain work the whole inbox in batches, report progress, and stop?
    """

    @pytest.fixture(autouse=True)
    def _reset(self):
        sync_module._progress = sync_module.MatchProgress()
        sync_module._cancel.clear()

    def _stub_inbox(self, monkeypatch, count: int) -> list[str]:
        remaining = [str(i) for i in range(count)]
        processed: list[str] = []

        async def candidates():
            return [(item_id, False) for item_id in remaining[: sync_module._AUTO_MATCH_BATCH]]

        async def match_one(item_id, already_proposed):
            processed.append(item_id)
            remaining.remove(item_id)

        async def count():
            return len(remaining)

        monkeypatch.setattr(sync_module, "_match_candidates", candidates)
        monkeypatch.setattr(sync_module, "_match_one", match_one)
        monkeypatch.setattr(sync_module, "_count_unmatched", count)
        return processed

    async def test_a_drain_works_the_whole_inbox_not_one_batch(self, monkeypatch):
        processed = self._stub_inbox(monkeypatch, 25)

        await sync_module._auto_match_pass(drain=True)

        assert len(processed) == 25, "all three batches ran, not just the first ten"
        assert sync_module.match_status().done == 25
        assert sync_module.match_status().running is False

    async def test_a_background_pass_does_a_single_batch(self, monkeypatch):
        processed = self._stub_inbox(monkeypatch, 25)

        await sync_module._auto_match_pass(drain=False)

        assert len(processed) == sync_module._AUTO_MATCH_BATCH
        # A background pass leaves the visible progress alone; only a drain reports it.
        assert sync_module.match_status().running is False
        assert sync_module.match_status().done == 0

    async def test_stop_halts_a_drain_after_the_current_item(self, monkeypatch):
        remaining = [str(i) for i in range(25)]
        processed: list[str] = []

        async def candidates():
            return [(item_id, False) for item_id in remaining[:10]]

        async def match_one(item_id, already_proposed):
            processed.append(item_id)
            remaining.remove(item_id)
            if len(processed) == 5:
                sync_module.stop_matching()

        async def count():
            return len(remaining)

        monkeypatch.setattr(sync_module, "_match_candidates", candidates)
        monkeypatch.setattr(sync_module, "_match_one", match_one)
        monkeypatch.setattr(sync_module, "_count_unmatched", count)

        await sync_module._auto_match_pass(drain=True)

        assert len(processed) == 5
        assert sync_module.match_status().done == 5
        assert sync_module.match_status().running is False
