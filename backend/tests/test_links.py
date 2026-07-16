"""A mention can belong to several tasks, and sync must never destroy a human's decision.
These are the tests for that promise.
"""

from __future__ import annotations

from app.services.links import ATTACH, DETACH, apply_overrides


def test_auto_links_pass_through():
    assert apply_overrides({"t1": {"m1", "m2"}}, {}, {}) == {"t1": {"m1", "m2"}}


def test_attach_adds_a_link_grouping_never_inferred():
    resolved = apply_overrides({"t1": {"m1"}}, {"t1": {"m2"}}, {})
    assert resolved["t1"] == {"m1", "m2"}


def test_detach_removes_an_inferred_link():
    resolved = apply_overrides({"t1": {"m1", "m2"}}, {}, {"t1": {"m2"}})
    assert resolved["t1"] == {"m1"}


def test_one_mention_can_belong_to_several_tasks():
    """The whole point: a thread about two subjects is about both."""
    resolved = apply_overrides({"t1": {"m1"}}, {"t2": {"m1"}, "t3": {"m1"}}, {})
    assert resolved["t1"] == {"m1"}
    assert resolved["t2"] == {"m1"}
    assert resolved["t3"] == {"m1"}


def test_detaching_every_mention_drops_the_task():
    assert apply_overrides({"t1": {"m1"}}, {}, {"t1": {"m1"}}) == {}


def test_detach_on_one_task_does_not_touch_another():
    resolved = apply_overrides({"t1": {"m1"}, "t2": {"m1"}}, {}, {"t1": {"m1"}})
    assert "t1" not in resolved
    assert resolved["t2"] == {"m1"}


def test_attach_survives_grouping_finding_nothing():
    """The regression that matters: a manual attach must not vanish on the next sync."""
    assert apply_overrides({}, {"t1": {"m9"}}, {}) == {"t1": {"m9"}}


async def test_record_override_flips_instead_of_duplicating(db):
    from sqlalchemy import select

    from app.models import LinkOverride
    from app.services.links import record_override

    await record_override(db, "m1", "t1", DETACH)
    await db.flush()
    await record_override(db, "m1", "t1", ATTACH)
    await db.flush()

    rows = (await db.execute(select(LinkOverride))).scalars().all()
    assert len(rows) == 1
    assert rows[0].action == ATTACH
