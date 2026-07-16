"""Adapters that parse someone else's API payloads.

These pin the mapping from a real response body to a RawItem, including the failure modes
each API has that a status code alone won't reveal.
"""

from __future__ import annotations

import httpx
import pytest
import respx

from app.sources.github import GitHubSource
from app.sources.linear import LinearSource
from app.sources.slack import SlackSource

PR_SEARCH = {
    "items": [
        {
            "number": 1201,
            "title": "feat(api): add pagination to the search endpoint",
            "html_url": "https://github.com/acme/widgets/pull/1201",
            "repository_url": "https://api.github.com/repos/acme/widgets",
            "updated_at": "2026-07-16T10:00:00Z",
            "state": "open",
            "draft": False,
            "labels": [{"name": "backend"}],
            "body": "Closes ENG-42",
            "pull_request": {},
        }
    ]
}


@pytest.fixture
def github() -> GitHubSource:
    return GitHubSource({"token": "ghp_x", "username": "someone", "org": "acme"})


class TestGitHub:
    @respx.mock
    async def test_maps_a_pull_request(self, github):
        respx.get("https://api.github.com/search/issues").mock(
            side_effect=[httpx.Response(200, json=PR_SEARCH), httpx.Response(200, json={"items": []})]
        )

        items = await github.fetch()

        assert len(items) == 1
        item = items[0]
        assert item.source == "pr"
        assert item.id == "pr:acme~widgets~1201"
        assert item.title == "feat(api): add pagination to the search endpoint"
        assert item.url == "https://github.com/acme/widgets/pull/1201"
        assert item.context == "#1201"
        assert item.tags == ["backend"]
        assert item.extra["repo"] == "acme/widgets"

    @respx.mock
    async def test_identity_is_its_own_ref_and_the_cited_ticket_is_a_reference(self, github):
        respx.get("https://api.github.com/search/issues").mock(
            side_effect=[httpx.Response(200, json=PR_SEARCH), httpx.Response(200, json={"items": []})]
        )

        item = (await github.fetch())[0]

        assert item.identity_keys == {"gh:acme/widgets#1201"}
        assert "ENG-42" in item.reference_keys, "a ticket cited in the body links the two"
        assert item.identity_keys.isdisjoint(item.reference_keys)

    @respx.mock
    async def test_a_merged_pr_reports_merged(self, github):
        merged = {"items": [{**PR_SEARCH["items"][0], "pull_request": {"merged_at": "2026-07-16T11:00:00Z"}}]}
        respx.get("https://api.github.com/search/issues").mock(
            side_effect=[httpx.Response(200, json=merged), httpx.Response(200, json={"items": []})]
        )

        assert (await github.fetch())[0].status == "merged"

    @respx.mock
    async def test_a_draft_pr_is_open_not_in_progress(self, github):
        draft = {"items": [{**PR_SEARCH["items"][0], "draft": True}]}
        respx.get("https://api.github.com/search/issues").mock(
            side_effect=[httpx.Response(200, json=draft), httpx.Response(200, json={"items": []})]
        )

        assert (await github.fetch())[0].status == "open"

    async def test_unconfigured_fetches_nothing_rather_than_failing(self):
        assert await GitHubSource({}).fetch() == []

    @respx.mock
    async def test_check_surfaces_a_bad_token(self, github):
        respx.get("https://api.github.com/user").mock(return_value=httpx.Response(401))
        with pytest.raises(httpx.HTTPStatusError):
            await github.check()


LINEAR_ISSUES = {
    "data": {
        "issues": {
            "nodes": [
                {
                    "id": "uuid-1",
                    "identifier": "ENG-42",
                    "title": "Search endpoint times out on large pages",
                    "description": "See acme/widgets#1201",
                    "url": "https://linear.app/acme/issue/ENG-42",
                    "updatedAt": "2026-07-16T09:00:00Z",
                    "branchName": "someone/eng-42-search-timeout",
                    "state": {"name": "In Progress", "type": "started"},
                    "labels": {"nodes": [{"name": "bug"}]},
                    "project": {"name": "Platform"},
                }
            ]
        }
    }
}


@pytest.fixture
def linear() -> LinearSource:
    return LinearSource({"api_key": "lin_api_x", "user_id": "me"})


class TestLinear:
    @respx.mock
    async def test_maps_an_issue(self, linear):
        respx.post("https://api.linear.app/graphql").mock(
            return_value=httpx.Response(200, json=LINEAR_ISSUES)
        )

        item = (await linear.fetch())[0]

        assert item.source == "linear"
        assert item.id == "linear:uuid-1"
        assert item.context == "ENG-42"
        assert item.status == "in_progress"
        assert item.tags == ["bug"]
        assert item.extra["project_name"] == "Platform"

    @respx.mock
    async def test_identity_covers_the_issue_key_and_its_branch_name(self, linear):
        respx.post("https://api.linear.app/graphql").mock(
            return_value=httpx.Response(200, json=LINEAR_ISSUES)
        )

        item = (await linear.fetch())[0]

        assert "ENG-42" in item.identity_keys
        assert "SOMEONE/ENG-42-SEARCH-TIMEOUT" in item.identity_keys, (
            "the branch name is how a local branch finds its issue"
        )

    @respx.mock
    async def test_graphql_errors_arrive_with_status_200(self, linear):
        """raise_for_status alone would let this through."""
        respx.post("https://api.linear.app/graphql").mock(
            return_value=httpx.Response(200, json={"errors": [{"message": "Invalid API key"}]})
        )
        with pytest.raises(RuntimeError, match="Invalid API key"):
            await linear.fetch()

    @respx.mock
    async def test_user_id_is_looked_up_when_not_configured(self):
        route = respx.post("https://api.linear.app/graphql").mock(
            side_effect=[
                httpx.Response(200, json={"data": {"viewer": {"id": "resolved-me"}}}),
                httpx.Response(200, json=LINEAR_ISSUES),
            ]
        )

        await LinearSource({"api_key": "lin_api_x"}).fetch()

        assert route.call_count == 2
        assert route.calls[1].request.read().decode().find("resolved-me") != -1


SLACK_SEARCH = {
    "ok": True,
    "messages": {
        "matches": [
            {
                "ts": "1752660000.000100",
                "thread_ts": "1752660000.000100",
                "text": "anyone seen the search endpoint time out? ENG-42",
                "permalink": "https://acme.slack.com/archives/C01/p1752660000000100",
                "channel": {"id": "C01", "name": "eng"},
            }
        ]
    },
}


@pytest.fixture
def slack() -> SlackSource:
    return SlackSource({"user_token": "xoxp-x", "user_id": "U1"})


class TestSlack:
    @respx.mock
    async def test_maps_a_message(self, slack):
        respx.get("https://slack.com/api/search.messages").mock(
            return_value=httpx.Response(200, json=SLACK_SEARCH)
        )

        items = await slack.fetch()

        assert len(items) == 1, "the same thread matching both queries must collapse to one item"
        item = items[0]
        assert item.source == "slack"
        assert item.id == "slack:C01:1752660000.000100"
        assert item.context == "#eng"
        assert item.url == SLACK_SEARCH["messages"]["matches"][0]["permalink"]

    @respx.mock
    async def test_a_message_points_at_a_subject_but_never_names_one(self, slack):
        respx.get("https://slack.com/api/search.messages").mock(
            return_value=httpx.Response(200, json=SLACK_SEARCH)
        )

        item = (await slack.fetch())[0]

        assert item.reference_keys == {"ENG-42"}
        assert item.identity_keys == set()
        assert item.status is None

    @respx.mock
    async def test_slack_reports_failure_with_status_200(self, slack):
        respx.get("https://slack.com/api/search.messages").mock(
            return_value=httpx.Response(200, json={"ok": False, "error": "missing_scope"})
        )
        with pytest.raises(RuntimeError, match="missing_scope"):
            await slack.fetch()

    @respx.mock
    async def test_user_id_is_detected_when_not_configured(self):
        respx.get("https://slack.com/api/auth.test").mock(
            return_value=httpx.Response(200, json={"ok": True, "user_id": "U9"})
        )
        route = respx.get("https://slack.com/api/search.messages").mock(
            return_value=httpx.Response(200, json=SLACK_SEARCH)
        )

        await SlackSource({"user_token": "xoxp-x"}).fetch()

        assert "U9" in str(route.calls[0].request.url)

    @respx.mock
    async def test_long_text_is_truncated_for_the_label(self, slack):
        long_text = {
            "ok": True,
            "messages": {
                "matches": [
                    {**SLACK_SEARCH["messages"]["matches"][0], "text": "x" * 300},
                ]
            },
        }
        respx.get("https://slack.com/api/search.messages").mock(
            return_value=httpx.Response(200, json=long_text)
        )

        assert (await slack.fetch())[0].label.endswith("…")


class TestSlackSessionToken:
    def test_an_app_token_needs_no_cookie(self):
        assert SlackSource({"user_token": "xoxp-abc"}).is_configured() is True

    def test_a_session_token_without_a_cookie_is_not_configured(self):
        source = SlackSource({"user_token": "xoxc-abc"})
        assert source.is_configured() is False, "the xoxc token is useless without the d cookie"

    def test_a_session_token_with_its_cookie_is_configured(self):
        assert SlackSource({"user_token": "xoxc-abc", "cookie": "xoxd-xyz"}).is_configured() is True

    def test_the_cookie_is_sent_verbatim_not_re_encoded(self):
        """The value copied from the browser is already the correct cookie value."""
        source = SlackSource({"user_token": "xoxc-abc", "cookie": "xoxd-8%2FxABC%3D"})
        assert source._headers()["Cookie"] == "d=xoxd-8%2FxABC%3D"

    def test_a_pasted_d_prefix_is_stripped(self):
        source = SlackSource({"user_token": "xoxc-abc", "cookie": "d=xoxd-xyz"})
        assert source._headers()["Cookie"] == "d=xoxd-xyz"

    def test_an_app_token_sends_no_cookie(self):
        assert "Cookie" not in SlackSource({"user_token": "xoxp-abc"})._headers()

    @respx.mock
    async def test_a_session_token_actually_searches(self):
        source = SlackSource({"user_token": "xoxc-abc", "cookie": "xoxd-xyz", "user_id": "U1"})
        route = respx.get("https://slack.com/api/search.messages").mock(
            return_value=httpx.Response(200, json=SLACK_SEARCH)
        )

        items = await source.fetch()

        assert len(items) == 1
        assert route.calls[0].request.headers["Cookie"] == "d=xoxd-xyz"
