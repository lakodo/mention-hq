"""GitHub PRs and issues, via the REST search API."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

import httpx

from app.sources.base import ConfigField, RawMention, Source
from app.sources.keys import all_reference_keys, github_key

API_ROOT = "https://api.github.com"


class GitHubSource(Source):
    id = "github"
    name = "GitHub"
    description = "Your open pull requests and assigned issues"
    fields: ClassVar[list[ConfigField]] = [
        ConfigField(
            key="token",
            label="Personal access token",
            kind="secret",
            placeholder="ghp_…",
            help="Needs the `repo` scope. Create one at github.com/settings/tokens",
        ),
        ConfigField(key="username", label="Username", placeholder="joris-guerry"),
        ConfigField(key="org", label="Organisation", placeholder="alan-eu"),
    ]

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

    async def fetch(self) -> list[RawMention]:
        if not self.is_configured():
            return []
        username, org = self.get("username"), self.get("org")
        queries = [
            (f"is:pr author:{username} org:{org} is:open", "pr"),
            (f"is:issue assignee:{username} org:{org} is:open", "issue"),
        ]
        mentions: list[RawMention] = []
        async with httpx.AsyncClient(timeout=20) as client:
            for query, kind in queries:
                response = await client.get(
                    f"{API_ROOT}/search/issues",
                    headers=self._headers(),
                    params={"q": query, "per_page": 50, "sort": "updated"},
                )
                response.raise_for_status()
                for raw in response.json().get("items", []):
                    mentions.append(_to_mention(raw, kind))
        return mentions


def _to_mention(raw: dict, kind: str) -> RawMention:
    repo = _repo_from_url(raw.get("repository_url", "")) or "unknown/unknown"
    number = raw["number"]
    labels = [label["name"] for label in raw.get("labels", [])]
    body = raw.get("body") or ""

    identity = github_key(repo, number)
    # A PR body citing "PAY-88" or "#1201" is the strongest cross-source link we get.
    references = all_reference_keys(raw["title"], body, default_repo=repo) - {identity}

    return RawMention(
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
