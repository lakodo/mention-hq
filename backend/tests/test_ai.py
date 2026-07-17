"""Bucket suggestions.

The Claude call itself is mocked — what matters here is that credentials resolve in the
right order, that a missing one degrades to an actionable message rather than a stack
trace, and that a suggestion is only ever a suggestion.
"""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.models import Bucket, Item, Task
from app.services import ai
from app.services.ai import BucketSuggestion


@pytest.fixture(autouse=True)
def _no_local_claude(monkeypatch):
    # The test host may have the real `claude` CLI on PATH; pin it off so credential
    # resolution is deterministic. A test that wants it re-patches this.
    monkeypatch.setattr(ai, "_claude_cli", lambda: None)


@pytest.fixture
def task(db) -> Task:
    return Task(
        id="task:1",
        title="Search endpoint times out",
        bucket="Uncategorized",
        status="open",
        tags=["bug"],
        unread=True,
        origin="auto",
        updated_at=datetime.now(UTC),
    )


def _fake_client(suggestion: BucketSuggestion):
    async def parse(**_kwargs):
        return SimpleNamespace(parsed_output=suggestion)

    return SimpleNamespace(messages=SimpleNamespace(parse=parse))


class TestStatus:
    def test_no_credentials_is_actionable(self, isolated_secrets):
        current = ai.status()

        assert current.available is False
        assert current.source == "none"
        assert "API key" in current.detail, "the message must say what to do next"

    def test_a_local_claude_cli_is_a_usable_brain(self, isolated_secrets, monkeypatch):
        monkeypatch.setattr(ai, "_claude_cli", lambda: "/usr/local/bin/claude")

        current = ai.status()

        assert current.available is True
        assert current.source == "claude-cli"

    def test_a_stored_key_is_reported_as_keychain(self, isolated_secrets):
        isolated_secrets.set("anthropic", "api_key", "sk-ant-xxx")
        assert ai.status().source == "keychain"

    def test_an_environment_key_is_found(self, isolated_secrets, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env")
        assert ai.status().source == "environment"

    def test_a_stored_key_wins_over_the_environment(self, isolated_secrets, monkeypatch):
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-env")
        isolated_secrets.set("anthropic", "api_key", "sk-ant-stored")
        assert ai.status().source == "keychain"

    def test_a_local_cli_login_is_enough(self, isolated_secrets, monkeypatch, tmp_path):
        (tmp_path / "credentials").mkdir()
        (tmp_path / "credentials" / "default.json").write_text("{}")
        monkeypatch.setenv("ANTHROPIC_CONFIG_DIR", str(tmp_path))

        current = ai.status()
        assert current.available is True
        assert current.source == "cli-login"


class TestSuggest:
    async def test_without_credentials_it_refuses_rather_than_failing(self, db, task):
        with pytest.raises(RuntimeError, match="API key"):
            await ai.suggest_bucket(db, task)

    async def test_a_suggestion_is_returned_verbatim(self, db, task, isolated_secrets, monkeypatch):
        isolated_secrets.set("anthropic", "api_key", "sk-ant-xxx")
        expected = BucketSuggestion(
            bucket="Platform", is_new=True, keywords=["search", "latency"], confidence=0.8, reasoning="…"
        )
        monkeypatch.setattr(ai, "_client", lambda: _fake_client(expected))

        result = await ai.suggest_bucket(db, task)

        assert result.bucket == "Platform"
        assert result.is_new is True
        assert result.keywords == ["search", "latency"]

    async def test_a_bucket_that_already_exists_is_not_reported_as_new(
        self, db, task, isolated_secrets, monkeypatch
    ):
        """The model can propose a name that exists, differing only in case."""
        db.add(Bucket(name="Platform", keywords=[], position=1))
        await db.flush()
        isolated_secrets.set("anthropic", "api_key", "sk-ant-xxx")
        monkeypatch.setattr(
            ai,
            "_client",
            lambda: _fake_client(
                BucketSuggestion(bucket="platform", is_new=True, keywords=[], confidence=0.9, reasoning="…")
            ),
        )

        result = await ai.suggest_bucket(db, task)

        assert result.bucket == "Platform", "it must match the existing bucket's casing"
        assert result.is_new is False

    async def test_uncategorized_is_never_a_new_bucket(self, db, task, isolated_secrets, monkeypatch):
        isolated_secrets.set("anthropic", "api_key", "sk-ant-xxx")
        monkeypatch.setattr(
            ai,
            "_client",
            lambda: _fake_client(
                BucketSuggestion(
                    bucket="uncategorized", is_new=True, keywords=[], confidence=0.2, reasoning="unsure"
                )
            ),
        )

        result = await ai.suggest_bucket(db, task)

        assert result.bucket == "Uncategorized"
        assert result.is_new is False

    async def test_confidence_must_be_a_probability(self):
        with pytest.raises(ValueError):
            BucketSuggestion(bucket="X", is_new=False, keywords=[], confidence=1.4, reasoning="…")


class TestEndpoint:
    async def test_suggest_reports_503_when_there_are_no_credentials(self, client, db, task):
        db.add(task)
        await db.commit()

        response = await client.post("/api/buckets/suggest/task:1")

        assert response.status_code == 503
        assert "API key" in response.json()["detail"]

    async def test_suggest_404s_for_an_unknown_task(self, client):
        assert (await client.post("/api/buckets/suggest/nope")).status_code == 404

    async def test_suggest_tasks_keeps_only_confident_real_matches(self, client, db, monkeypatch):
        for tid, title in [("task:a", "Refund bug"), ("task:b", "CI flake")]:
            db.add(
                Task(
                    id=tid,
                    title=title,
                    bucket="Uncategorized",
                    status="open",
                    tags=[],
                    unread=False,
                    origin="manual",
                    updated_at=datetime.now(UTC),
                )
            )
        db.add(
            Item(
                id="pr:x~1",
                source="pr",
                label="fix refunds",
                url=None,
                context=None,
                occurred_at=datetime.now(UTC),
                extra={},
            )
        )
        await db.commit()

        async def fake_structured(system, prompt, model_cls):
            return model_cls(
                matches=[
                    {"task_id": "task:a", "confidence": 0.9, "reason": "same refund work"},
                    {"task_id": "task:b", "confidence": 0.2, "reason": "too vague"},
                    {"task_id": "task:ghost", "confidence": 0.99, "reason": "invented"},
                ]
            )

        monkeypatch.setattr(ai, "_claude_cli", lambda: "/usr/bin/claude")
        monkeypatch.setattr(ai, "_structured", fake_structured)

        body = (await client.post("/api/catchup/pr:x~1/suggest-tasks")).json()

        # Weak (task:b) and invented (task:ghost) are dropped; only the confident real one stays.
        assert [m["task"]["id"] for m in body] == ["task:a"]
        assert body[0]["reason"] == "same refund work"

    async def test_suggest_tasks_resolves_a_match_that_dropped_the_task_prefix(self, client, db, monkeypatch):
        db.add(
            Task(
                id="task:dcd73249fe21",
                title="SFA",
                bucket="Uncategorized",
                status="open",
                tags=[],
                unread=False,
                origin="manual",
                updated_at=datetime.now(UTC),
            )
        )
        db.add(
            Item(
                id="slack:x~1",
                source="slack",
                label="#org_alaner-sfa hiring",
                url=None,
                context=None,
                occurred_at=datetime.now(UTC),
                extra={},
            )
        )
        await db.commit()

        async def fake_structured(system, prompt, model_cls):
            # The brain returns the id without the "task:" prefix, as it often does.
            return model_cls(matches=[{"task_id": "dcd73249fe21", "confidence": 0.9, "reason": "SFA"}])

        monkeypatch.setattr(ai, "_claude_cli", lambda: "/usr/bin/claude")
        monkeypatch.setattr(ai, "_structured", fake_structured)

        body = (await client.post("/api/catchup/slack:x~1/suggest-tasks")).json()

        assert [m["task"]["id"] for m in body] == ["task:dcd73249fe21"]

    async def test_admin_reports_ai_status(self, client, isolated_secrets):
        body = (await client.get("/api/admin/ai")).json()

        assert body["available"] is False
        assert body["model"] == "claude-opus-4-8"

    async def test_setting_and_clearing_the_key(self, client, isolated_secrets):
        set_response = await client.put("/api/admin/ai/key", json={"api_key": "sk-ant-xxx"})
        assert set_response.json()["source"] == "keychain"

        cleared = await client.put("/api/admin/ai/key", json={"api_key": ""})
        assert cleared.json()["available"] is False

    async def test_the_key_is_never_echoed_back(self, client, isolated_secrets):
        response = await client.put("/api/admin/ai/key", json={"api_key": "sk-ant-supersecret"})
        assert "supersecret" not in response.text
