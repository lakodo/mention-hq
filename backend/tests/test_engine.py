"""Engines propose; they never decide.

The bar for a proposal is that a person would agree with the reason attached to it, so
these tests are as much about what must *not* be proposed as what must.
"""

from __future__ import annotations

import pytest

from app.engine import KeyEngine, NullEngine, TaskView, TitleSimilarityEngine, engines_for, propose
from app.engine.base import Proposal
from app.engine.similarity import normalise


def make_task(task_id: str, title: str, identity=(), reference=()) -> TaskView:
    return TaskView(
        id=task_id,
        title=title,
        identity_keys=frozenset(identity),
        reference_keys=frozenset(reference),
    )


def test_proposal_rejects_impossible_confidence():
    with pytest.raises(ValueError, match="confidence"):
        Proposal(task_id="t", confidence=1.5, reason="nope")


def test_null_engine_proposes_nothing(item):
    task = make_task("t1", "Refund bug")
    assert NullEngine().propose(item("todo", "1"), [task]) == []


def test_unknown_source_falls_back_to_proposing_nothing(item):
    assert [type(e) for e in engines_for("something-new")] == [NullEngine]
    assert propose(item("something-new", "1"), [make_task("t1", "Refund bug")]) == []


class TestKeyEngine:
    def test_identity_match_is_certain(self, item):
        task = make_task("t1", "Refund bug", identity=["ENG-42"])
        incoming = item("branch", "repo:owner~eng-42", identity_keys={"ENG-42"})

        proposals = KeyEngine().propose(incoming, [task])
        assert len(proposals) == 1
        assert proposals[0].confidence == 1.0
        assert "ENG-42" in proposals[0].reason

    def test_reference_match_is_strong_but_not_certain(self, item):
        task = make_task("t1", "Refund bug", identity=["ENG-42"])
        incoming = item("slack", "C1:1", reference_keys={"ENG-42"})

        proposals = KeyEngine().propose(incoming, [task])
        assert proposals[0].confidence == 0.9

    def test_no_keys_means_no_opinion(self, item):
        task = make_task("t1", "Refund bug", identity=["ENG-42"])
        assert KeyEngine().propose(item("todo", "1"), [task]) == []

    def test_different_keys_do_not_match(self, item):
        task = make_task("t1", "Refund bug", identity=["ENG-42"])
        incoming = item("branch", "b", identity_keys={"AUTH-2"})
        assert KeyEngine().propose(incoming, [task]) == []


class TestTitleSimilarityEngine:
    def test_matches_across_wording_and_order(self, item):
        task = make_task("t1", "Stripe webhook handling for invoice payments")
        incoming = item("pr", "r~1", title="feat(payments): add Stripe webhook handler")

        proposals = TitleSimilarityEngine().propose(incoming, [task])
        assert proposals, "reordered wording with a commit prefix should still match"
        assert proposals[0].confidence <= 0.8, "a title lookalike is never a certainty"
        assert "similar" in proposals[0].reason

    def test_unrelated_titles_do_not_match(self, item):
        task = make_task("t1", "Terraform apply hangs on RDS module")
        incoming = item("pr", "r~2", title="feat(auth): rotate refresh tokens on scope change")
        assert TitleSimilarityEngine().propose(incoming, [task]) == []

    def test_one_word_titles_are_not_enough_to_argue_from(self, item):
        task = make_task("t1", "Refund")
        assert TitleSimilarityEngine().propose(item("todo", "1", label="Refund"), [task]) == []

    def test_conventional_commit_prefixes_do_not_create_matches(self, item):
        """Two unrelated PRs both starting "feat(x):" must not look alike."""
        task = make_task("t1", "feat(billing): generate monthly invoices")
        incoming = item("pr", "r~3", title="feat(billing): delete stale audit logs")
        assert TitleSimilarityEngine().propose(incoming, [task]) == []

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            # The commit type goes, the scope stays — it names the subject.
            ("feat(payments): add Stripe webhook handler", "payments stripe webhook handler"),
            ("fix: rotate refresh tokens", "rotate refresh tokens"),
            ("joris/pay-88-refunds", "pay 88 refunds"),
            ("[alan-apps] main", "alan apps main"),
        ],
    )
    def test_normalise(self, raw, expected):
        assert normalise(raw) == expected


class TestRegistry:
    def test_slack_never_fuzzy_matches(self, item):
        """Slack text is chatty; matching it on titles produces confident nonsense."""
        assert [type(e) for e in engines_for("slack")] == [KeyEngine]

    def test_strongest_claim_wins_when_engines_agree(self, item):
        task = make_task("t1", "Stripe webhook handling", identity=["ENG-42"])
        incoming = item(
            "pr",
            "r~1",
            title="Stripe webhook handling",
            identity_keys={"ENG-42"},
        )

        proposals = propose(incoming, [task])
        assert len(proposals) == 1, "one proposal per task, not one per engine"
        proposal, source_engine = proposals[0]
        assert proposal.confidence == 1.0
        assert source_engine.id == "keys"

    def test_proposals_are_ordered_by_confidence(self, item):
        strong = make_task("t1", "Refund bug", identity=["ENG-42"])
        weak = make_task("t2", "Refund bug elsewhere")
        incoming = item("pr", "r~1", title="Refund bug", reference_keys={"ENG-42"})

        proposals = propose(incoming, [strong, weak])
        confidences = [p.confidence for p, _ in proposals]
        assert confidences == sorted(confidences, reverse=True)
