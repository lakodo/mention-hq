"""Grouping is the heart of the app — if it over-merges, unrelated work collapses into
one task; if it under-merges, the board is just a flat feed. These pin both directions.
"""

from __future__ import annotations

from datetime import timedelta

from app.services.grouping import group_mentions


def test_unrelated_mentions_stay_separate(mention):
    groups = group_mentions([mention("todo", "a"), mention("todo", "b")])
    assert len(groups) == 2


def test_shared_identity_key_merges(mention):
    linear = mention("linear", "1", identity_keys={"PAY-88"})
    branch = mention("branch", "repo:joris/pay-88", identity_keys={"PAY-88"})
    groups = group_mentions([linear, branch])

    assert len(groups) == 1
    assert {m.source for m in groups[0].mentions} == {"linear", "branch"}


def test_reference_merges_into_identity(mention):
    linear = mention("linear", "1", identity_keys={"PAY-88"}, title="Refund flow throws")
    slack = mention("slack", "C1:1", reference_keys={"PAY-88"})
    groups = group_mentions([linear, slack])

    assert len(groups) == 1
    assert groups[0].title == "Refund flow throws"


def test_merging_is_transitive(mention):
    """PR -> issue and issue -> slack must land all three on one task."""
    pr = mention("pr", "r#1", identity_keys={"gh:r#1"}, reference_keys={"PAY-88"})
    linear = mention("linear", "1", identity_keys={"PAY-88"}, reference_keys={"AUTH-2"})
    other = mention("linear", "2", identity_keys={"AUTH-2"})

    groups = group_mentions([pr, linear, other])
    assert len(groups) == 1
    assert len(groups[0].mentions) == 3


def test_reference_to_nothing_does_not_merge(mention):
    """A Slack message citing a ticket we never fetched must not glom onto a random task."""
    slack = mention("slack", "C1:1", reference_keys={"PAY-88"})
    unrelated = mention("todo", "x")

    groups = group_mentions([slack, unrelated])
    assert len(groups) == 2


def test_title_comes_from_highest_priority_source(mention):
    slack = mention("slack", "C1:1", identity_keys={"K"}, label="can someone look at this?")
    linear = mention("linear", "1", identity_keys={"K"}, title="Refund flow throws")

    groups = group_mentions([slack, linear])
    assert groups[0].title == "Refund flow throws"


def test_slack_never_wins_the_title(mention):
    """Slack labels are message text, which makes a terrible task title."""
    slack = mention("slack", "C1:1", identity_keys={"K"}, label="lol what")
    todo = mention("todo", "1", identity_keys={"K"}, label="Write retry tests")

    groups = group_mentions([slack, todo])
    assert groups[0].title == "Write retry tests"


def test_in_progress_beats_open(mention):
    a = mention("linear", "1", identity_keys={"K"}, status="open")
    b = mention("pr", "r#1", identity_keys={"K"}, status="in_progress")

    assert group_mentions([a, b])[0].status == "in_progress"


def test_status_defaults_to_open_when_no_mention_has_one(mention):
    assert group_mentions([mention("slack", "C1:1")])[0].status == "open"


def test_tags_union_across_mentions(mention):
    a = mention("linear", "1", identity_keys={"K"}, tags=["bug"])
    b = mention("pr", "r#1", identity_keys={"K"}, tags=["security", "bug"])

    assert group_mentions([a, b])[0].tags == ["bug", "security"]


def test_updated_at_is_the_most_recent_mention(mention, now):
    old = mention("todo", "1", identity_keys={"K"}, occurred_at=now - timedelta(days=3))
    fresh = mention("pr", "r#1", identity_keys={"K"}, occurred_at=now)

    assert group_mentions([old, fresh])[0].updated_at == now


def test_empty_input():
    assert group_mentions([]) == []
