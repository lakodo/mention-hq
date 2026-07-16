"""Local git branches."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar

from app.sources.base import ConfigField, RawMention, Source, SourceNotConfigured
from app.sources.keys import all_reference_keys

DEFAULT_MAX_AGE_DAYS = 30


class GitSource(Source):
    id = "git"
    name = "Local Git"
    description = "Branches you're working on in local repositories"
    fields: ClassVar[list[ConfigField]] = [
        ConfigField(
            key="repos",
            label="Repository paths",
            placeholder="/Users/you/code/one, /Users/you/code/two",
            help="Comma-separated absolute paths",
        ),
        ConfigField(
            key="branch_prefix",
            label="Your branch prefix",
            required=False,
            placeholder="joris/",
            help="Branches with this prefix are always included, however old",
        ),
        ConfigField(
            key="max_age_days",
            label="Include branches committed in the last N days",
            required=False,
            placeholder=str(DEFAULT_MAX_AGE_DAYS),
        ),
    ]

    @property
    def _repos(self) -> list[str]:
        return self.get_list("repos")

    @property
    def _max_age_days(self) -> int:
        try:
            return int(self.get("max_age_days") or DEFAULT_MAX_AGE_DAYS)
        except ValueError:
            return DEFAULT_MAX_AGE_DAYS

    def detail(self) -> str:
        return " · ".join(self._repos) or "Not configured"

    async def check(self) -> None:
        await super().check()
        for repo in self._repos:
            if not (Path(repo) / ".git").exists():
                raise SourceNotConfigured(f"Not a git repository: {repo}")

    async def fetch(self) -> list[RawMention]:
        if not self.is_configured():
            return []
        results = await asyncio.gather(
            *(self._fetch_repo(repo) for repo in self._repos), return_exceptions=True
        )
        mentions: list[RawMention] = []
        for result in results:
            if not isinstance(result, BaseException):
                mentions.extend(result)
        return mentions

    async def _fetch_repo(self, repo_path: str) -> list[RawMention]:
        proc = await asyncio.create_subprocess_exec(
            "git",
            "-C",
            repo_path,
            "for-each-ref",
            "--format=%(refname:short)%09%(committerdate:iso-strict)",
            "--sort=-committerdate",
            "refs/heads/",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode != 0:
            raise RuntimeError(stderr.decode().strip() or f"git failed in {repo_path}")

        repo_name = Path(repo_path).name
        cutoff = datetime.now(UTC) - timedelta(days=self._max_age_days)
        prefix = self.get("branch_prefix")

        mentions = []
        for line in stdout.decode().splitlines():
            if "\t" not in line:
                continue
            branch, raw_date = line.split("\t", 1)
            committed = datetime.fromisoformat(raw_date.strip()).astimezone(UTC)
            if not (prefix and branch.startswith(prefix)) and committed < cutoff:
                continue
            mentions.append(
                RawMention(
                    source="branch",
                    external_id=f"{repo_name}:{branch}",
                    label=f"[{repo_name}] {branch}",
                    occurred_at=committed,
                    context=repo_name,
                    status="in_progress",
                    # Branch names carry the ticket ref in most conventions
                    # (joris/pay-88-refunds), which is the cheapest link we get.
                    reference_keys=all_reference_keys(branch.upper()),
                    extra={"repo_path": repo_path, "repo_name": repo_name, "branch": branch},
                )
            )
        return mentions
