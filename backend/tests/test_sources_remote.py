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


class _FakeDirectory:
    def __init__(self, known: dict[str, str] | None = None) -> None:
        self._known = known or {}
        self.remembered: dict[str, str] = {}

    async def known(self, kind: str, values: set[str]) -> dict[str, str]:
        return {v: self._known[v] for v in values if v in self._known}

    async def remember(self, kind: str, names: dict[str, str]) -> None:
        self.remembered.update(names)


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
        # The channel leads the label, so there is no separate context line to repeat it.
        assert item.label == "#eng - anyone seen the search endpoint time out? ENG-42"
        assert item.context is None
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

    @respx.mock
    async def test_a_thread_collapses_to_one_item_even_via_the_permalink(self, slack):
        root = {
            "ts": "1752660000.000100",
            "text": "Follow-up in Vera",
            "permalink": "https://acme.slack.com/archives/C05/p1752660000000100",
            "channel": {"id": "C05", "name": "mo"},
        }
        # A reply's search result drops thread_ts, but its permalink still carries it.
        reply = {
            "ts": "1752660500.000200",
            "text": "and destiny already selected you",
            "permalink": "https://acme.slack.com/archives/C05/p1752660500000200?thread_ts=1752660000.000100",
            "channel": {"id": "C05", "name": "mo"},
        }
        respx.get("https://slack.com/api/search.messages").mock(
            return_value=httpx.Response(200, json={"ok": True, "messages": {"matches": [reply, root]}})
        )

        items = await slack.fetch()
        assert len(items) == 1, "root and reply belong to one thread, so one item"
        # And it is titled by the thread's root, not whichever reply happened to match.
        assert items[0].label == "#mo - Follow-up in Vera"

    @respx.mock
    async def test_emoji_shortcodes_become_unicode(self, slack):
        match = {
            **SLACK_SEARCH["messages"]["matches"][0],
            "text": "Dataset annotation :arrow_heading_down: :marmot-wave:",
        }
        respx.get("https://slack.com/api/search.messages").mock(
            return_value=httpx.Response(200, json={"ok": True, "messages": {"matches": [match]}})
        )

        label = (await slack.fetch())[0].label
        assert "⤵" in label, "a standard shortcode is rendered"
        assert ":marmot-wave:" in label, "a custom workspace emoji has no Unicode, so it stays"

    @respx.mock
    async def test_markup_is_rendered_into_readable_text(self, slack):
        match = {
            **SLACK_SEARCH["messages"]["matches"][0],
            "text": (
                "hey <@U9|bruno.vegreville> can you review "
                "<https://github.com/x/y/pull/1|PR #1>? cc <!here> &amp; thanks"
            ),
        }
        respx.get("https://slack.com/api/search.messages").mock(
            return_value=httpx.Response(200, json={"ok": True, "messages": {"matches": [match]}})
        )

        item = (await slack.fetch())[0]
        assert item.label.startswith("#eng - hey @bruno.vegreville can you review PR #1?")

    @respx.mock
    async def test_a_bare_mention_and_dm_channel_resolve_to_names(self, slack):
        match = {
            "ts": "1752660000.000100",
            "thread_ts": "1752660000.000100",
            "text": "ping <@U9>",
            "permalink": "https://acme.slack.com/archives/D01/p1",
            "channel": {"id": "D01", "name": "U9", "is_im": True, "user": "U9"},
        }
        respx.get("https://slack.com/api/search.messages").mock(
            return_value=httpx.Response(200, json={"ok": True, "messages": {"matches": [match]}})
        )
        respx.get("https://slack.com/api/users.info").mock(
            return_value=httpx.Response(
                200, json={"ok": True, "user": {"id": "U9", "profile": {"display_name": "Bruno"}}}
            )
        )

        item = (await slack.fetch())[0]
        assert item.label == "DM with @Bruno - ping @Bruno"

    @respx.mock
    async def test_a_missing_users_read_scope_leaves_a_dm_readable(self, slack):
        match = {
            "ts": "1752660000.000100",
            "thread_ts": "1752660000.000100",
            "text": "ping <@U9>",
            "permalink": "https://acme.slack.com/archives/D01/p1",
            "channel": {"id": "D01", "name": "U9", "is_im": True, "user": "U9"},
        }
        respx.get("https://slack.com/api/search.messages").mock(
            return_value=httpx.Response(200, json={"ok": True, "messages": {"matches": [match]}})
        )
        respx.get("https://slack.com/api/users.info").mock(
            return_value=httpx.Response(200, json={"ok": False, "error": "missing_scope"})
        )

        item = (await slack.fetch())[0]
        assert item.label == "direct message - ping @someone"

    @respx.mock
    async def test_a_known_id_is_not_looked_up_again(self, slack):
        slack.directory = _FakeDirectory({"U9": "Bruno"})
        match = {
            "ts": "1752660000.000100",
            "thread_ts": "1752660000.000100",
            "text": "ping <@U9>",
            "permalink": "https://acme.slack.com/archives/D01/p1",
            "channel": {"id": "D01", "name": "U9", "is_im": True, "user": "U9"},
        }
        respx.get("https://slack.com/api/search.messages").mock(
            return_value=httpx.Response(200, json={"ok": True, "messages": {"matches": [match]}})
        )
        # No users.info mock: if the source asked Slack for a name the directory already had,
        # respx would raise on the unmocked call.
        item = (await slack.fetch())[0]
        assert item.label == "DM with @Bruno - ping @Bruno"

    @respx.mock
    async def test_a_discovered_name_is_handed_to_the_directory(self, slack):
        directory = _FakeDirectory()
        slack.directory = directory
        match = {
            "ts": "1752660000.000100",
            "thread_ts": "1752660000.000100",
            "text": "ping <@U9>",
            "permalink": "https://acme.slack.com/archives/D01/p1",
            "channel": {"id": "D01", "name": "U9", "is_im": True, "user": "U9"},
        }
        respx.get("https://slack.com/api/search.messages").mock(
            return_value=httpx.Response(200, json={"ok": True, "messages": {"matches": [match]}})
        )
        respx.get("https://slack.com/api/users.info").mock(
            return_value=httpx.Response(
                200, json={"ok": True, "user": {"id": "U9", "profile": {"display_name": "Bruno"}}}
            )
        )

        item = (await slack.fetch())[0]
        assert item.label == "DM with @Bruno - ping @Bruno"
        assert directory.remembered == {"U9": "Bruno"}

    @respx.mock
    async def test_an_app_message_reads_its_block_kit_content(self, slack):
        # A GitHub app posts a PR notice with no top-level text — it lives in a section block.
        match = {
            "ts": "1752660000.000100",
            "thread_ts": "1752660000.000100",
            "text": "",
            "permalink": "https://acme.slack.com/archives/C01/p1",
            "channel": {"id": "C01", "name": "mo"},
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "New PR <https://github.com/x/y/pull/1|docs: add guideline> | +6 -0",
                    },
                }
            ],
        }
        respx.get("https://slack.com/api/search.messages").mock(
            return_value=httpx.Response(200, json={"ok": True, "messages": {"matches": [match]}})
        )

        assert (await slack.fetch())[0].label == "#mo - New PR docs: add guideline | +6 -0"

    @respx.mock
    async def test_a_rich_text_block_message_is_read(self, slack):
        match = {
            "ts": "1752660000.000100",
            "thread_ts": "1752660000.000100",
            "text": "",
            "permalink": "https://acme.slack.com/archives/C01/p1",
            "channel": {"id": "C01", "name": "mo"},
            "blocks": [
                {
                    "type": "rich_text",
                    "elements": [
                        {
                            "type": "rich_text_section",
                            "elements": [
                                {"type": "text", "text": "the perfect example of a "},
                                {"type": "text", "text": "CEO fraud scam"},
                            ],
                        }
                    ],
                }
            ],
        }
        respx.get("https://slack.com/api/search.messages").mock(
            return_value=httpx.Response(200, json={"ok": True, "messages": {"matches": [match]}})
        )

        assert (await slack.fetch())[0].label == "#mo - the perfect example of a CEO fraud scam"

    @respx.mock
    async def test_a_message_with_no_text_is_named_by_its_file(self, slack):
        match = {
            "ts": "1752660000.000100",
            "thread_ts": "1752660000.000100",
            "text": "",
            "permalink": "https://acme.slack.com/archives/C01/p1",
            "channel": {"id": "C01", "name": "eng"},
            "files": [{"title": "design-v2.fig"}],
        }
        respx.get("https://slack.com/api/search.messages").mock(
            return_value=httpx.Response(200, json={"ok": True, "messages": {"matches": [match]}})
        )

        assert (await slack.fetch())[0].label == "#eng - shared a file: design-v2.fig"
