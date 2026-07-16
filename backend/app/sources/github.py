"""GitHub PRs and issues, via the REST search API."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

import httpx

from app.sources.base import ConfigField, Detection, RawItem, Source
from app.sources.keys import all_reference_keys, github_key
from app.sources.tools import run_tool

API_ROOT = "https://api.github.com"


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
        queries = [
            (f"is:pr author:{username} org:{org} is:open", "pr"),
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
        return items


def _to_item(raw: dict, kind: str) -> RawItem:
    repo = _repo_from_url(raw.get("repository_url", "")) or "unknown/unknown"
    number = raw["number"]
    labels = [label["name"] for label in raw.get("labels", [])]
    body = raw.get("body") or ""

    identity = github_key(repo, number)
    # A ticket or issue reference in the body is the strongest cross-source link available.
    references = all_reference_keys(raw["title"], body, default_repo=repo) - {identity}

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
        extra={"repo": repo, "labels": labels, "draft": raw.get("draft", False)},
    )


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
