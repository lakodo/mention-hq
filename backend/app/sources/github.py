"""GitHub PRs and issues, via the REST search API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import ClassVar

import httpx

from app.sources.base import ConfigField, Detection, RawItem, Source
from app.sources.keys import all_reference_keys, github_key
from app.sources.tools import run_tool

API_ROOT = "https://api.github.com"
# How far back to keep showing a merged PR. Recently-merged ones stay visible (as "merged")
# rather than vanishing the moment they leave the is:open search; older ones age out — unless
# you've filed one onto a task, which sync keeps regardless.
MERGED_WINDOW_DAYS = 14


class GitHubSource(Source):
    id = "github"
    name = "GitHub"
    description = "Your open pull requests and assigned issues"
    setup = (
        "If you use the GitHub CLI, press Detect and there is nothing to fill in. "
        "Otherwise create a personal access token with the `repo` scope."
    )
    setup_url = "https://github.com/settings/tokens/new?scopes=repo&description=Personal%20HQ"
    fields: ClassVar[list[ConfigField]] = [
        ConfigField(
            key="token",
            label="Personal access token",
            kind="secret",
            placeholder="ghp_…",
            help="Needs the `repo` scope.",
            help_url="https://github.com/settings/tokens/new?scopes=repo&description=Personal%20HQ",
        ),
        ConfigField(key="username", label="Username", placeholder="your-username"),
        ConfigField(
            key="org",
            label="Organisation",
            placeholder="your-org",
            help="The organisation whose PRs and issues you want.",
        ),
    ]

    @classmethod
    async def detect(cls) -> Detection:
        token = await run_tool("gh", "auth", "token")
        if not token:
            return Detection(
                available=False,
                detail="The GitHub CLI isn't installed or isn't logged in. Run `gh auth login`.",
            )

        username = await run_tool("gh", "api", "user", "--jq", ".login")
        orgs = await run_tool("gh", "api", "user/orgs", "--jq", '[.[].login] | join("\\n")')

        values = {"token": token}
        if username:
            values["username"] = username

        who = f"@{username}" if username else "your account"
        return Detection(
            available=True,
            detail=f"Found a token for {who} via the GitHub CLI.",
            values=values,
            choices={"org": orgs.splitlines()} if orgs else {},
        )

    def detail(self) -> str:
        if not self.is_configured():
            return "Not configured"
        return f"{self.get('org')} · @{self.get('username')}"

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.get('token')}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def check(self) -> None:
        await super().check()
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{API_ROOT}/user", headers=self._headers())
            response.raise_for_status()

    async def fetch(self) -> list[RawItem]:
        if not self.is_configured():
            return []
        username, org = self.get("username"), self.get("org")
        merged_since = (datetime.now(UTC) - timedelta(days=MERGED_WINDOW_DAYS)).date().isoformat()
        queries = [
            (f"is:pr author:{username} org:{org} is:open", "pr"),
            (f"is:pr author:{username} org:{org} is:merged merged:>={merged_since}", "pr"),
            (f"is:issue assignee:{username} org:{org} is:open", "issue"),
        ]
        items: list[RawItem] = []
        async with httpx.AsyncClient(timeout=20) as client:
            for query, kind in queries:
                response = await client.get(
                    f"{API_ROOT}/search/issues",
                    headers=self._headers(),
                    params={"q": query, "per_page": 50, "sort": "updated"},
                )
                response.raise_for_status()
                for raw in response.json().get("items", []):
                    items.append(_to_item(raw, kind))

            review = await self._review_states(client, username, org)

        # A PR carries two independent facts: the overall review decision, and whether a
        # reviewer is still pending — a PR can be both "changes requested" and awaiting review.
        for item in items:
            if item.source != "pr":
                continue
            if item.status == "merged":
                # A merged PR is done — its review decision no longer matters, and the review
                # GraphQL only covers open PRs anyway. It refreshes a PR you've already filed
                # (so it shows "merged") but doesn't flood catch-up with every recent merge.
                item.extra["pr_status"] = "merged"
                item.refresh_only = True
                continue
            state = review.get(item.external_id, {})
            item.extra["pr_status"] = _pr_status(item.extra.get("draft", False), state.get("decision"))
            item.extra["pr_review_requested"] = state.get("pending", False)
            if state.get("head_branch"):
                # Lets the board join a PR to the local branch it was pushed from.
                item.extra["head_branch"] = state["head_branch"]
            for login in state.get("reviewers", []):
                _add_person(item.people, login, "reviewer")
        return items

    async def _review_states(self, client: httpx.AsyncClient, username: str, org: str) -> dict[str, dict]:
        """`{repo#number: {decision, pending, reviewers}}` for the open PRs.

        One GraphQL call, because the REST search exposes only the single overall decision —
        not that a changes-requested PR still has a review pending, nor who the reviewers are.
        """
        query = """
        query($q: String!) {
          search(query: $q, type: ISSUE, first: 50) {
            nodes {
              ... on PullRequest {
                number
                headRefName
                repository { nameWithOwner }
                reviewDecision
                reviewRequests(first: 20) { totalCount nodes { requestedReviewer { ... on User { login } } } }
                reviews(first: 50) { nodes { author { login } } }
              }
            }
          }
        }
        """
        variables = {"q": f"is:pr author:{username} org:{org} is:open"}
        try:
            response = await client.post(
                f"{API_ROOT}/graphql",
                headers=self._headers(),
                json={"query": query, "variables": variables},
            )
            nodes = response.json()["data"]["search"]["nodes"]
        except (httpx.HTTPError, KeyError, TypeError):
            # Review state is a nicety; a PR without it still shows as an open PR.
            return {}

        states: dict[str, dict] = {}
        for node in nodes:
            if not node:
                continue
            repo = (node.get("repository") or {}).get("nameWithOwner", "unknown/unknown")
            requests = node.get("reviewRequests") or {}
            reviewers = {(r.get("requestedReviewer") or {}).get("login") for r in requests.get("nodes") or []}
            reviewers |= {
                (r.get("author") or {}).get("login") for r in (node.get("reviews") or {}).get("nodes") or []
            }
            states[f"{repo}#{node['number']}"] = {
                "decision": node.get("reviewDecision"),
                "pending": requests.get("totalCount", 0) > 0,
                "reviewers": sorted(login for login in reviewers if login),
                "head_branch": node.get("headRefName"),
            }
        return states


def _add_person(people: list[dict], login: str | None, role: str) -> None:
    """Add a GitHub login once — a person keeps the first role they turn up in."""
    if login and not any(p["value"] == login for p in people):
        # GitHub serves every login's avatar at this URL, so no extra API call is needed.
        people.append(
            {
                "kind": "github",
                "value": login,
                "name": login,
                "role": role,
                "avatar": f"https://github.com/{login}.png?size=64",
            }
        )


def _to_item(raw: dict, kind: str) -> RawItem:
    repo = _repo_from_url(raw.get("repository_url", "")) or "unknown/unknown"
    number = raw["number"]
    labels = [label["name"] for label in raw.get("labels", [])]
    body = raw.get("body") or ""

    identity = github_key(repo, number)
    # A ticket or issue reference in the body is the strongest cross-source link available.
    references = all_reference_keys(raw["title"], body, default_repo=repo) - {identity}

    people: list[dict] = []
    _add_person(people, (raw.get("user") or {}).get("login"), "author")
    for assignee in raw.get("assignees") or []:
        _add_person(people, assignee.get("login"), "assignee")

    return RawItem(
        source=kind,
        external_id=f"{repo}#{number}",
        label=raw["title"],
        occurred_at=datetime.fromisoformat(raw["updated_at"].replace("Z", "+00:00")),
        url=raw["html_url"],
        context=f"#{number}",
        title=raw["title"],
        status=_status(raw, kind),
        tags=labels,
        identity_keys={identity},
        reference_keys=references,
        people=people,
        extra={"repo": repo, "labels": labels, "draft": raw.get("draft", False)},
    )


_REVIEW_DECISION = {
    "CHANGES_REQUESTED": "changes_requested",
    "APPROVED": "approved",
    "REVIEW_REQUIRED": "review_required",
}


def _pr_status(draft: bool, decision: str | None) -> str:
    if draft:
        return "draft"
    return _REVIEW_DECISION.get(decision or "", "open")


def _status(raw: dict, kind: str) -> str:
    if raw.get("pull_request", {}).get("merged_at"):
        return "merged"
    if raw.get("state") == "closed":
        return "done"
    if kind == "pr" and not raw.get("draft", False):
        return "in_progress"
    return "open"


def _repo_from_url(repository_url: str) -> str | None:
    parts = repository_url.rstrip("/").split("/")
    if len(parts) < 2:
        return None
    return f"{parts[-2]}/{parts[-1]}"
