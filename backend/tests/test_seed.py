"""The demo seed — the data behind `task back:seed`, which fills a throwaway DB for
development, screenshots and docs so the real one is never touched."""

from __future__ import annotations

from sqlalchemy import select

from app.models import CONFIRMED, Bucket, Item, Link, Person, Task
from app.seed import seed

EVERY_SOURCE = {
    "pr",
    "issue",
    "linear",
    "slack",
    "branch",
    "todo",
    "markdown",
    "dust",
    "notion",
    "notion_mcp",
    "note",
}


async def test_populates_every_source(db):
    await seed(db)

    sources = {i.source for i in (await db.execute(select(Item))).scalars()}
    assert sources >= EVERY_SOURCE, f"missing: {EVERY_SOURCE - sources}"


async def test_builds_a_board_of_tasks_in_buckets(db):
    await seed(db)

    tasks = (await db.execute(select(Task))).scalars().all()
    buckets = {b.name for b in (await db.execute(select(Bucket))).scalars()}
    assert len(tasks) >= 10
    # Most tasks land in a real bucket, not just Uncategorized.
    assert {t.bucket for t in tasks} & buckets


async def test_has_a_git_spice_stack_and_catch_up_inbox(db):
    await seed(db)

    items = (await db.execute(select(Item))).scalars().all()
    stacked = [i for i in items if i.source == "branch" and len(i.stack) >= 2]
    assert stacked, "a git-spice stack should exist to show the Code lane"

    untriaged = [i for i in items if not i.triaged]
    assert untriaged, "some items wait untriaged in catch-up"


async def test_people_are_referenced_by_filed_items(db):
    await seed(db)

    people = (await db.execute(select(Person))).scalars().all()
    assert people, "a people directory is seeded"
    confirmed = [
        link.item for link in (await db.execute(select(Link).where(Link.state == CONFIRMED))).scalars()
    ]
    assert any(item.people for item in confirmed), "filed items carry the people they concern"
