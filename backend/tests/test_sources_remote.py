"""Adapters that parse someone else's API payloads.

These pin the mapping from a real response body to a RawItem, including the failure modes
each API has that a status code alone won't reveal.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest
import respx

from app.sources.github import GitHubSource
from app.sources.linear import LinearSource
from app.sources.notion import NotionSource
from app.sources.notion_mcp import NotionMcpSource, _items_from_search
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


def _github_search(pr_json: dict):
    """A respx side-effect for search/issues: the base PR query returns `pr_json`; the issue
    query returns nothing."""

    def handler(request):
        q = request.url.params.get("q", "")
        if q.startswith("is:pr"):
            return httpx.Response(200, json=pr_json)
        return httpx.Response(200, json={"items": []})

    return handler


def _github_graphql(nodes: list | None = None):
    """Mock the review-state GraphQL call. Empty by default (no review data)."""
    respx.post("https://api.github.com/graphql").mock(
        return_value=httpx.Response(200, json={"data": {"search": {"nodes": nodes or []}}})
    )


class TestGitHub:
    @respx.mock
    async def test_maps_a_pull_request(self, github):
        respx.get("https://api.github.com/search/issues").mock(side_effect=_github_search(PR_SEARCH))
        _github_graphql()

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
        respx.get("https://api.github.com/search/issues").mock(side_effect=_github_search(PR_SEARCH))
        _github_graphql()

        item = (await github.fetch())[0]

        assert item.identity_keys == {"gh:acme/widgets#1201"}
        assert "ENG-42" in item.reference_keys, "a ticket cited in the body links the two"
        assert item.identity_keys.isdisjoint(item.reference_keys)

    @respx.mock
    async def test_a_merged_pr_reports_merged(self, github):
        merged = {"items": [{**PR_SEARCH["items"][0], "pull_request": {"merged_at": "2026-07-16T11:00:00Z"}}]}
        respx.get("https://api.github.com/search/issues").mock(side_effect=_github_search(merged))
        _github_graphql()

        assert (await github.fetch())[0].status == "merged"

    @respx.mock
    async def test_a_draft_pr_is_open_not_in_progress(self, github):
        draft = {"items": [{**PR_SEARCH["items"][0], "draft": True}]}
        respx.get("https://api.github.com/search/issues").mock(side_effect=_github_search(draft))
        _github_graphql()

        assert (await github.fetch())[0].status == "open"

    @respx.mock
    async def test_a_pr_reports_changes_requested_and_a_pending_review(self, github):
        respx.get("https://api.github.com/search/issues").mock(side_effect=_github_search(PR_SEARCH))
        _github_graphql(
            [
                {
                    "number": 1201,
                    "repository": {"nameWithOwner": "acme/widgets"},
                    "reviewDecision": "CHANGES_REQUESTED",
                    "reviewRequests": {"totalCount": 1},
                }
            ]
        )

        item = (await github.fetch())[0]

        assert item.extra["pr_status"] == "changes_requested"
        assert item.extra["pr_review_requested"] is True

    @respx.mock
    async def test_a_pr_carries_its_author_assignees_and_reviewers(self, github):
        pr = {
            **PR_SEARCH["items"][0],
            "user": {"login": "someone"},
            "assignees": [{"login": "grace"}],
        }
        respx.get("https://api.github.com/search/issues").mock(side_effect=_github_search({"items": [pr]}))
        _github_graphql(
            [
                {
                    "number": 1201,
                    "repository": {"nameWithOwner": "acme/widgets"},
                    "reviewDecision": "CHANGES_REQUESTED",
                    "reviewRequests": {
                        "totalCount": 1,
                        "nodes": [{"requestedReviewer": {"login": "ada"}}],
                    },
                    "reviews": {"nodes": [{"author": {"login": "linus"}}]},
                }
            ]
        )

        people = (await github.fetch())[0].people
        by_login = {p["value"]: p["role"] for p in people}

        assert by_login["someone"] == "author"
        assert by_login["grace"] == "assignee"
        assert by_login["ada"] == "reviewer"
        assert by_login["linus"] == "reviewer"

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
    async def test_an_issue_carries_its_assignee_and_creator(self, linear):
        issue = {
            **LINEAR_ISSUES["data"]["issues"]["nodes"][0],
            "assignee": {"displayName": "Ada Lovelace", "email": "ada@acme.dev"},
            "creator": {"displayName": "Grace Hopper", "email": "grace@acme.dev"},
        }
        respx.post("https://api.linear.app/graphql").mock(
            return_value=httpx.Response(200, json={"data": {"issues": {"nodes": [issue]}}})
        )

        people = (await linear.fetch())[0].people
        by_name = {p["name"]: p["role"] for p in people}

        assert by_name["Ada Lovelace"] == "assignee"
        assert by_name["Grace Hopper"] == "creator"

    @respx.mock
    async def test_graphql_errors_arrive_with_status_200(self, linear):
        """raise_for_status alone would let this through."""
        respx.post("https://api.linear.app/graphql").mock(
            return_value=httpx.Response(200, json={"errors": [{"message": "Invalid API key"}]})
        )
        with pytest.raises(RuntimeError, match="Invalid API key"):
            await linear.fetch()

    @respx.mock
    async def test_backlog_issues_are_requested_and_mapped(self, linear):
        """Assigned issues sitting in the backlog must come through, not only active ones."""
        route = respx.post("https://api.linear.app/graphql").mock(
            return_value=httpx.Response(
                200,
                json={
                    "data": {
                        "issues": {
                            "nodes": [
                                {
                                    "id": "uuid-2",
                                    "identifier": "DOC-1996",
                                    "title": "link to message in message group",
                                    "description": "",
                                    "url": "https://linear.app/acme/issue/DOC-1996",
                                    "updatedAt": "2026-06-25T09:00:00Z",
                                    "branchName": "someone/doc-1996",
                                    "state": {"name": "Backlog", "type": "backlog"},
                                    "labels": {"nodes": []},
                                    "project": None,
                                }
                            ]
                        }
                    }
                },
            )
        )

        item = (await linear.fetch())[0]

        assert item.context == "DOC-1996"
        assert item.status == "open"
        # The query itself must ask Linear for backlog, or the server never returns these.
        assert "backlog" in route.calls[0].request.read().decode()

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
            "text": "Follow-up in Orion",
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
        assert items[0].label == "#mo - Follow-up in Orion"

    @respx.mock
    async def test_emoji_shortcodes_become_unicode(self, slack):
        match = {
            **SLACK_SEARCH["messages"]["matches"][0],
            "text": "Dataset annotation :arrow_heading_down: :party-parrot:",
        }
        respx.get("https://slack.com/api/search.messages").mock(
            return_value=httpx.Response(200, json={"ok": True, "messages": {"matches": [match]}})
        )

        label = (await slack.fetch())[0].label
        assert "⤵" in label, "a standard shortcode is rendered"
        assert ":party-parrot:" in label, "a custom workspace emoji has no Unicode, so it stays"

    @respx.mock
    async def test_configured_custom_emoji_carry_their_image_url(self):
        source = SlackSource(
            {
                "user_token": "xoxp-x",
                "user_id": "U1",
                "emoji_urls": "https://emoji.slack-edge.com/T04/party-parrot/abc123.gif",
            }
        )
        match = {**SLACK_SEARCH["messages"]["matches"][0], "text": "good :party-parrot: work"}
        respx.get("https://slack.com/api/search.messages").mock(
            return_value=httpx.Response(200, json={"ok": True, "messages": {"matches": [match]}})
        )

        item = (await source.fetch())[0]

        assert item.extra["emoji"] == {
            "party-parrot": "https://emoji.slack-edge.com/T04/party-parrot/abc123.gif"
        }

    @respx.mock
    async def test_markup_is_rendered_into_readable_text(self, slack):
        match = {
            **SLACK_SEARCH["messages"]["matches"][0],
            "text": (
                "hey <@U9|ada.lovelace> can you review "
                "<https://github.com/x/y/pull/1|PR #1>? cc <!here> &amp; thanks"
            ),
        }
        respx.get("https://slack.com/api/search.messages").mock(
            return_value=httpx.Response(200, json={"ok": True, "messages": {"matches": [match]}})
        )

        item = (await slack.fetch())[0]
        assert item.label.startswith("#eng - hey @ada.lovelace can you review PR #1?")

    @respx.mock
    async def test_a_shared_message_shows_the_quote_not_the_permalink(self, slack):
        match = {
            **SLACK_SEARCH["messages"]["matches"][0],
            "text": "<https://acme.slack.com/archives/C05/p1784100000000100>",
            "attachments": [
                {
                    "is_msg_unfurl": True,
                    "author_name": "Grace Hopper",
                    "channel_name": "mo",
                    "text": "follow-up investigation is done",
                    "from_url": "https://acme.slack.com/archives/C05/p1784100000000100",
                }
            ],
        }
        respx.get("https://slack.com/api/search.messages").mock(
            return_value=httpx.Response(200, json={"ok": True, "messages": {"matches": [match]}})
        )

        item = (await slack.fetch())[0]

        assert "slack.com/archives" not in item.label, "the raw permalink is gone"
        assert item.label.startswith("#eng - Grace Hopper in #mo: follow-up")

    @respx.mock
    async def test_a_usergroup_mention_uses_its_handle(self, slack):
        match = {**SLACK_SEARCH["messages"]["matches"][0], "text": "Cc <@S060JTNTFBP|mo-crew>"}
        respx.get("https://slack.com/api/search.messages").mock(
            return_value=httpx.Response(200, json={"ok": True, "messages": {"matches": [match]}})
        )

        label = (await slack.fetch())[0].label

        assert "@mo-crew" in label
        assert "S060JTNTFBP" not in label, "the raw id is gone"

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
                200, json={"ok": True, "user": {"id": "U9", "profile": {"display_name": "Ada"}}}
            )
        )

        item = (await slack.fetch())[0]
        assert item.label == "DM with @Ada - ping @Ada"

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
        slack.directory = _FakeDirectory({"U9": "Ada"})
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
        assert item.label == "DM with @Ada - ping @Ada"

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
                200, json={"ok": True, "user": {"id": "U9", "profile": {"display_name": "Ada"}}}
            )
        )

        item = (await slack.fetch())[0]
        assert item.label == "DM with @Ada - ping @Ada"
        assert directory.remembered == {"U9": "Ada"}

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


NOTION_SEARCH = {
    "results": [
        {
            "object": "page",
            "id": "page-1",
            "url": "https://notion.so/page-1",
            "last_edited_time": "2026-07-16T09:00:00.000Z",
            "created_by": {"object": "user", "id": "me", "name": "Ada Lovelace"},
            "last_edited_by": {"object": "user", "id": "grace", "name": "Grace Hopper"},
            "properties": {
                "title": {"type": "title", "title": [{"plain_text": "Roadmap "}, {"plain_text": "Q3"}]}
            },
        },
        {
            "object": "page",
            "id": "page-2",
            "url": "https://notion.so/page-2",
            "last_edited_time": "2026-07-15T09:00:00.000Z",
            "created_by": {"object": "user", "id": "grace", "name": "Grace Hopper"},
            "last_edited_by": {"object": "user", "id": "grace", "name": "Grace Hopper"},
            "properties": {"Name": {"type": "title", "title": [{"plain_text": "Design notes"}]}},
        },
        {
            "object": "page",
            "id": "page-3",
            "url": "https://notion.so/page-3",
            "last_edited_time": "2026-07-14T09:00:00.000Z",
            "created_by": {"object": "user", "id": "grace", "name": "Grace Hopper"},
            "last_edited_by": {"object": "user", "id": "grace", "name": "Grace Hopper"},
            "properties": {"title": {"type": "title", "title": [{"plain_text": "Someone else's page"}]}},
        },
    ]
}

NOTION_COMMENTS = {
    "page-2": {
        "results": [
            {
                "created_by": {"object": "user", "id": "grace", "name": "Grace Hopper"},
                "rich_text": [
                    {"type": "text", "plain_text": "cc "},
                    {
                        "type": "mention",
                        "mention": {"type": "user", "user": {"id": "me", "name": "Ada Lovelace"}},
                        "plain_text": "@Ada",
                    },
                ],
            }
        ]
    }
}


def _notion_comments(request):
    block = request.url.params.get("block_id", "")
    return httpx.Response(200, json=NOTION_COMMENTS.get(block, {"results": []}))


@pytest.fixture
def notion() -> NotionSource:
    return NotionSource({"token": "ntn_x", "user_id": "me"})


class TestNotion:
    @respx.mock
    async def test_surfaces_pages_you_created_own_or_are_mentioned_in(self, notion):
        respx.post("https://api.notion.com/v1/search").mock(
            return_value=httpx.Response(200, json=NOTION_SEARCH)
        )
        respx.get("https://api.notion.com/v1/comments").mock(side_effect=_notion_comments)

        items = await notion.fetch()

        # page-1 (you created it) and page-2 (a comment mentions you); page-3 is someone
        # else's with no involvement, so it never lands in your board.
        assert {item.external_id for item in items} == {"page-1", "page-2"}
        page1 = next(i for i in items if i.external_id == "page-1")
        assert page1.source == "notion"
        assert page1.id == "notion:page-1"
        assert page1.label == "Roadmap Q3"
        assert page1.url == "https://notion.so/page-1"

    @respx.mock
    async def test_a_created_page_names_its_creator_and_owner(self, notion):
        respx.post("https://api.notion.com/v1/search").mock(
            return_value=httpx.Response(200, json=NOTION_SEARCH)
        )
        respx.get("https://api.notion.com/v1/comments").mock(side_effect=_notion_comments)

        page1 = next(i for i in await notion.fetch() if i.external_id == "page-1")
        by_name = {p["name"]: p["role"] for p in page1.people}

        assert by_name["Ada Lovelace"] == "creator"
        assert by_name["Grace Hopper"] == "owner"

    @respx.mock
    async def test_a_comment_mention_carries_the_mentioned_person(self, notion):
        respx.post("https://api.notion.com/v1/search").mock(
            return_value=httpx.Response(200, json=NOTION_SEARCH)
        )
        respx.get("https://api.notion.com/v1/comments").mock(side_effect=_notion_comments)

        page2 = next(i for i in await notion.fetch() if i.external_id == "page-2")
        roles = {p["value"]: p["role"] for p in page2.people}

        assert roles["me"] == "mentioned"
        assert roles["grace"] == "creator"

    @respx.mock
    async def test_missing_comment_access_does_not_sink_the_sync(self, notion):
        respx.post("https://api.notion.com/v1/search").mock(
            return_value=httpx.Response(200, json=NOTION_SEARCH)
        )
        respx.get("https://api.notion.com/v1/comments").mock(
            return_value=httpx.Response(403, json={"message": "no comment capability"})
        )

        # Comments are a separate integration capability; without it, creator/owner pages
        # still come through — you just lose the mention signal.
        items = await notion.fetch()

        assert {item.external_id for item in items} == {"page-1"}

    @respx.mock
    async def test_resolves_you_from_the_token_when_user_id_is_blank(self):
        source = NotionSource({"token": "ntn_x"})
        respx.get("https://api.notion.com/v1/users/me").mock(
            return_value=httpx.Response(200, json={"bot": {"owner": {"type": "user", "user": {"id": "me"}}}})
        )
        respx.post("https://api.notion.com/v1/search").mock(
            return_value=httpx.Response(200, json=NOTION_SEARCH)
        )
        respx.get("https://api.notion.com/v1/comments").mock(side_effect=_notion_comments)

        items = await source.fetch()

        assert {item.external_id for item in items} == {"page-1", "page-2"}

    async def test_unconfigured_notion_fetches_nothing(self):
        assert await NotionSource({}).fetch() == []

    @respx.mock
    async def test_exchange_code_returns_the_token_and_its_owner(self):
        source = NotionSource({"client_id": "cid", "client_secret": "csec"})
        respx.post("https://api.notion.com/v1/oauth/token").mock(
            return_value=httpx.Response(
                200,
                json={
                    "access_token": "ntn_new",
                    "refresh_token": "refresh_1",
                    "expires_in": 3600,
                    "owner": {"type": "user", "user": {"id": "me"}},
                },
            )
        )

        updates = await source.exchange_code("code123", "http://jojohq/api/admin/oauth/notion/callback")

        assert updates["token"] == "ntn_new"
        assert updates["refresh_token"] == "refresh_1"
        assert updates["user_id"] == "me"
        assert "token_expiry" in updates

    @respx.mock
    async def test_prepare_refreshes_a_token_that_is_about_to_lapse(self):
        past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        source = NotionSource(
            {
                "client_id": "cid",
                "client_secret": "csec",
                "refresh_token": "r1",
                "token": "old",
                "token_expiry": past,
            }
        )
        route = respx.post("https://api.notion.com/v1/oauth/token").mock(
            return_value=httpx.Response(
                200, json={"access_token": "ntn_fresh", "refresh_token": "r2", "expires_in": 3600}
            )
        )

        updates = await source.prepare()

        assert route.called
        assert updates["token"] == "ntn_fresh"
        assert updates["refresh_token"] == "r2"

    async def test_prepare_is_a_noop_without_a_refresh_token(self):
        assert await NotionSource({"token": "ntn_x"}).prepare() is None

    async def test_prepare_is_a_noop_while_the_token_is_still_valid(self):
        future = (datetime.now(UTC) + timedelta(hours=1)).isoformat()
        source = NotionSource(
            {"client_id": "c", "client_secret": "s", "refresh_token": "r1", "token_expiry": future}
        )
        assert await source.prepare() is None


def _mcp_search_result(entry: dict) -> dict:
    # notion-search returns its results as a JSON string inside a text content block.
    payload = json.dumps({"results": [entry], "type": "workspace_search"})
    return {"jsonrpc": "2.0", "id": 2, "result": {"content": [{"type": "text", "text": payload}]}}


def _mcp_handler(search_response: httpx.Response):
    """Dispatch the three MCP posts by JSON-RPC method: handshake, ack, then the search."""

    def handler(request):
        method = json.loads(request.content).get("method")
        if method == "initialize":
            return httpx.Response(
                200,
                headers={"mcp-session-id": "sess-1"},
                json={"jsonrpc": "2.0", "id": 1, "result": {"protocolVersion": "2025-06-18"}},
            )
        if method == "notifications/initialized":
            return httpx.Response(202)
        return search_response

    return handler


@pytest.fixture
def notion_mcp() -> NotionMcpSource:
    return NotionMcpSource({"token": "mcp-token", "query": "project"})


class TestNotionMcp:
    @respx.mock
    async def test_fetch_searches_over_mcp_and_maps_the_results(self, notion_mcp):
        entry = {
            "id": "page-1",
            "title": "Roadmap",
            "url": "https://notion.so/page-1",
            "type": "page",
            "highlight": "the Q3 roadmap",
            "timestamp": "2026-07-16T09:00:00.000Z",
        }
        respx.post("https://mcp.notion.com/mcp").mock(
            side_effect=_mcp_handler(httpx.Response(200, json=_mcp_search_result(entry)))
        )

        items = await notion_mcp.fetch()

        assert len(items) == 1
        assert items[0].source == "notion_mcp"
        assert items[0].id == "notion_mcp:page-1"
        assert items[0].label == "Roadmap"
        assert items[0].context == "the Q3 roadmap"
        assert items[0].occurred_at.year == 2026
        assert items[0].url == "https://notion.so/page-1"

    @respx.mock
    async def test_fetch_parses_an_sse_encoded_response(self, notion_mcp):
        data = json.dumps(_mcp_search_result({"id": "p9", "title": "X", "url": "u"}))
        sse = httpx.Response(
            200, headers={"content-type": "text/event-stream"}, text=f"event: message\ndata: {data}\n\n"
        )
        respx.post("https://mcp.notion.com/mcp").mock(side_effect=_mcp_handler(sse))

        items = await notion_mcp.fetch()

        assert [i.external_id for i in items] == ["p9"]

    @respx.mock
    async def test_register_client_returns_a_public_client_id(self, notion_mcp):
        route = respx.post("https://mcp.notion.com/register").mock(
            return_value=httpx.Response(200, json={"client_id": "cid-1"})
        )

        client_id = await notion_mcp.register_client("http://jojohq/api/admin/oauth/notion-mcp/callback")

        assert client_id == "cid-1"
        # No secret is requested — it registers as a public client that uses PKCE.
        assert json.loads(route.calls[0].request.content)["token_endpoint_auth_method"] == "none"

    @respx.mock
    async def test_exchange_code_returns_tokens_and_client(self, notion_mcp):
        respx.post("https://mcp.notion.com/token").mock(
            return_value=httpx.Response(
                200, json={"access_token": "tok", "refresh_token": "ref", "expires_in": 3600}
            )
        )

        updates = await notion_mcp.exchange_code("code", "http://jojohq/cb", "verifier", "cid-1")

        assert updates["token"] == "tok"
        assert updates["refresh_token"] == "ref"
        assert updates["client_id"] == "cid-1"

    @respx.mock
    async def test_prepare_refreshes_an_expired_token(self):
        past = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
        source = NotionMcpSource(
            {"token": "old", "refresh_token": "r", "client_id": "cid", "token_expiry": past}
        )
        route = respx.post("https://mcp.notion.com/token").mock(
            return_value=httpx.Response(200, json={"access_token": "fresh", "expires_in": 3600})
        )

        updates = await source.prepare()

        assert route.called
        assert updates["token"] == "fresh"

    async def test_prepare_is_a_noop_without_a_refresh_token(self):
        assert await NotionMcpSource({"token": "x"}).prepare() is None

    def test_items_from_search_reads_a_json_text_block(self):
        result = {
            "content": [{"type": "text", "text": json.dumps({"results": [{"id": "p2", "title": "Notes"}]})}]
        }

        items = _items_from_search(result)

        assert [i.external_id for i in items] == ["p2"]
        assert items[0].label == "Notes"

    async def test_unconfigured_mcp_fetches_nothing(self):
        assert await NotionMcpSource({}).fetch() == []

    async def test_no_search_terms_means_no_fetch(self):
        # notion-search rejects an empty query, so a connected source with no terms fetches
        # nothing rather than erroring — no MCP call is made at all (no respx mock needed).
        assert await NotionMcpSource({"token": "mcp-token"}).fetch() == []
