"""Reading a source's settings out of a CLI the user already logged into."""

from __future__ import annotations

import pytest

from app.sources import github
from app.sources.base import Source
from app.sources.github import GitHubSource


@pytest.fixture
def fake_gh(monkeypatch):
    def _install(responses: dict[str, str]):
        async def fake_run(command: str, *args: str) -> str:
            return responses.get(" ".join((command, *args)), "")

        monkeypatch.setattr(github, "run_tool", fake_run)

    return _install


LOGGED_IN = {
    "gh auth token": "gho_realtoken1234",
    "gh api user --jq .login": "someone",
    'gh api user/orgs --jq [.[].login] | join("\\n")': "acme\nwidgets",
}


class TestGitHubDetection:
    async def test_reads_the_token_and_username(self, fake_gh):
        fake_gh(LOGGED_IN)

        found = await GitHubSource.detect()

        assert found.available is True
        assert found.values["token"] == "gho_realtoken1234"
        assert found.values["username"] == "someone"
        assert "@someone" in found.detail

    async def test_offers_the_orgs_it_cannot_choose_between(self, fake_gh):
        fake_gh(LOGGED_IN)
        assert (await GitHubSource.detect()).choices == {"org": ["acme", "widgets"]}

    async def test_no_cli_is_reported_with_what_to_do(self, fake_gh):
        fake_gh({})

        found = await GitHubSource.detect()

        assert found.available is False
        assert "gh auth login" in found.detail, "the message must say how to fix it"

    async def test_a_source_without_a_cli_detects_nothing(self):
        from app.sources.todos import TodoSource

        assert (await TodoSource.detect()).available is False


class TestDetectEndpoint:
    async def test_a_detected_secret_is_saved_and_never_returned(
        self, client, connect, fake_gh, isolated_secrets
    ):
        fake_gh(LOGGED_IN)
        source_id = await connect("github", "Work")

        response = await client.post(f"/admin/sources/{source_id}/detect")

        assert response.status_code == 200
        assert "gho_realtoken1234" not in response.text, "the browser must never see the token"
        assert response.json()["applied"]["token"] == "saved"
        assert isolated_secrets.get(source_id, "token") == "gho_realtoken1234"

    async def test_non_secret_values_are_written_and_shown(self, client, connect, fake_gh, isolated_secrets):
        fake_gh(LOGGED_IN)
        source_id = await connect("github", "Work")

        body = (await client.post(f"/admin/sources/{source_id}/detect")).json()

        assert body["applied"]["username"] == "someone"
        assert body["choices"]["org"] == ["acme", "widgets"]
        assert body["source"]["fields"][0]["value"].endswith("1234")

    async def test_detection_leaves_a_source_reporting_what_is_still_missing(
        self, client, connect, fake_gh, isolated_secrets
    ):
        """gh knows the token, not which org you want."""
        fake_gh(LOGGED_IN)
        source_id = await connect("github", "Work")

        body = (await client.post(f"/admin/sources/{source_id}/detect")).json()

        assert body["source"]["status"] == "unconfigured"

    async def test_no_cli_changes_nothing(self, client, connect, fake_gh, isolated_secrets):
        fake_gh({})
        source_id = await connect("github", "Work")

        body = (await client.post(f"/admin/sources/{source_id}/detect")).json()

        assert body["available"] is False
        assert body["applied"] == {}
        assert isolated_secrets.get(source_id, "token") is None

    async def test_unknown_source_404s(self, client):
        assert (await client.post("/admin/sources/nope/detect")).status_code == 404

    async def test_the_picker_says_which_kinds_can_detect(self, client):
        kinds = {k["kind"]: k for k in (await client.get("/admin/source-kinds")).json()}

        assert kinds["github"]["detectable"] is True
        assert kinds["todo"]["detectable"] is False

    async def test_the_picker_carries_setup_prose_and_a_link(self, client):
        kinds = {k["kind"]: k for k in (await client.get("/admin/source-kinds")).json()}

        assert kinds["slack"]["setup"], "the fiddly ones need instructions"
        assert kinds["slack"]["setup_url"].startswith("https://")
        assert kinds["git"]["setup"], "and the easy ones should say there is nothing to do"
        assert kinds["git"]["needs_credentials"] is False
        assert kinds["github"]["needs_credentials"] is True


async def test_run_tool_survives_a_missing_binary():
    from app.sources.tools import run_tool

    assert await run_tool("definitely-not-a-real-binary-xyz", "--version") == ""


def test_a_source_that_overrides_detect_is_distinguishable_from_one_that_does_not():
    """A classmethod builds a new bound method on every access, so compare the functions."""
    from app.sources.todos import TodoSource

    assert GitHubSource.detect.__func__ is not Source.detect.__func__
    assert TodoSource.detect.__func__ is Source.detect.__func__
