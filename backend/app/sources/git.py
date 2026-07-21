"""Local git branches, including git-spice stacks."""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import ClassVar

from app.sources.base import ConfigField, RawItem, Source, SourceNotConfigured
from app.sources.keys import all_reference_keys

DEFAULT_MAX_AGE_DAYS = 30
# git-spice keeps its stack state in this ref: a commit whose tree has a `repo` file (the
# trunk) and a `branches/<name>` file per tracked branch, each JSON with `base.name` — the
# branch it's stacked on. Reading it directly means no dependency on the `gs` CLI.
SPICE_REF = "refs/spice/data"


class GitSource(Source):
    id = "git"
    name = "Local Git"
    description = "Branches you're working on in local repositories, and their git-spice stacks"
    setup = (
        "No credentials — it reads the repositories on this machine. git-spice stacks are "
        "detected automatically where a repo uses them."
    )
    fields: ClassVar[list[ConfigField]] = [
        ConfigField(
            key="repos",
            label="Repository paths",
            placeholder="/Users/you/code/one, /Users/you/code/two",
            help="Comma-separated absolute paths",
            browse=True,
        ),
        ConfigField(
            key="branch_prefix",
            label="Your branch prefix",
            required=False,
            placeholder="your-name/",
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

    async def fetch(self) -> list[RawItem]:
        if not self.is_configured():
            return []
        results = await asyncio.gather(
            *(self._fetch_repo(repo) for repo in self._repos), return_exceptions=True
        )
        items: list[RawItem] = []
        for result in results:
            if not isinstance(result, BaseException):
                items.extend(result)
        return items

    async def _fetch_repo(self, repo_path: str) -> list[RawItem]:
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

        items = []
        for line in stdout.decode().splitlines():
            if "\t" not in line:
                continue
            branch, raw_date = line.split("\t", 1)
            committed = datetime.fromisoformat(raw_date.strip()).astimezone(UTC)
            # Every branch that still exists is reported so the sync can tell a deleted branch
            # (gone from this list) from one that has merely aged out. A stale branch rides in
            # as refresh-only: it keeps an item you filed current without putting old branches
            # back in catch-up.
            fresh = bool(prefix and branch.startswith(prefix)) or committed >= cutoff
            items.append(
                RawItem(
                    source="branch",
                    external_id=f"{repo_name}:{branch}",
                    label=f"[{repo_name}] {branch}",
                    occurred_at=committed,
                    context=repo_name,
                    status="in_progress",
                    refresh_only=not fresh,
                    # Most branch-naming conventions embed the ticket ref, which is the
                    # cheapest cross-source link available.
                    reference_keys=all_reference_keys(branch.upper()),
                    extra={"repo_path": repo_path, "repo_name": repo_name, "branch": branch},
                )
            )

        await _add_spice_stacks(repo_path, repo_name, items)
        return items


async def _run_git(repo_path: str, *args: str) -> tuple[int, bytes]:
    proc = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        repo_path,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _ = await proc.communicate()
    return proc.returncode or 0, stdout


async def _spice_state(repo_path: str) -> tuple[str | None, dict[str, str]]:
    """git-spice's stack as (trunk, {branch: base}). Empty when the repo doesn't use it."""
    code, _ = await _run_git(repo_path, "rev-parse", "--verify", "--quiet", SPICE_REF)
    if code != 0:
        return None, {}

    trunk = None
    code, out = await _run_git(repo_path, "cat-file", "-p", f"{SPICE_REF}:repo")
    if code == 0:
        trunk = _read_json(out).get("trunk")

    code, out = await _run_git(repo_path, "ls-tree", "-r", "--name-only", f"{SPICE_REF}:branches")
    bases: dict[str, str] = {}
    if code == 0:
        for branch in out.decode().splitlines():
            got, blob = await _run_git(repo_path, "cat-file", "-p", f"{SPICE_REF}:branches/{branch}")
            base = (_read_json(blob).get("base") or {}).get("name") if got == 0 else None
            if base:
                bases[branch] = base
    return trunk, bases


def _read_json(raw: bytes) -> dict:
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except json.JSONDecodeError:
        return {}


def _stack_chain(branch: str, bases: dict[str, str], trunk: str | None) -> list[str]:
    """The downstack chain from the base of the stack up to `branch` (trunk excluded)."""
    chain = [branch]
    seen = {branch}
    current = branch
    while (base := bases.get(current)) and base != trunk and base not in seen:
        chain.insert(0, base)
        seen.add(base)
        current = base
    return chain


async def _add_spice_stacks(repo_path: str, repo_name: str, items: list[RawItem]) -> None:
    """Note each branch's git-spice stack on its item — the branch it's stacked on and the whole
    downstack chain. The chain rides in `stack` for the UI to draw; context stays the repo name."""
    trunk, bases = await _spice_state(repo_path)
    if not bases:
        return
    for item in items:
        branch = item.extra["branch"]
        if branch not in bases:
            continue
        item.extra["stacked_on"] = bases[branch]
        item.extra["stack"] = _stack_chain(branch, bases, trunk)
