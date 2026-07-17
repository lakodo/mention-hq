"""Bucket suggestions via the Claude API.

Auth deliberately has no HQ-specific mechanism. The Anthropic SDK resolves credentials
itself — ANTHROPIC_API_KEY, then ANTHROPIC_AUTH_TOKEN, then the OAuth profile written by
`ant auth login`. So on a machine where you're already logged in, a zero-argument client
just works and no key is stored anywhere. An API key set in Admin goes to the keychain and
takes precedence; it exists for machines without a login, not as the happy path.

This is a suggestion engine, never an authority: it proposes, `/buckets/suggest` returns,
and the user accepts. Nothing here writes a bucket.
"""

from __future__ import annotations

import asyncio
import json
import re
import shutil
from dataclasses import dataclass
from typing import TypeVar

import structlog
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Item, Task
from app.security import get_secret_store
from app.services.buckets import UNCATEGORIZED, load_matcher

_Structured = TypeVar("_Structured", bound=BaseModel)

log = structlog.get_logger(__name__)

MODEL = "claude-opus-4-8"
SECRET_NAMESPACE = "anthropic"
CLI_TIMEOUT_S = 120
# Below this the brain isn't sure enough to file the item for you.
MATCH_FLOOR = 0.6

SYSTEM_PROMPT = """You sort a person's work into topic buckets on a personal dashboard.

You will be given one task — a subject they need to handle — and the buckets that already \
exist. Decide where it belongs.

Prefer an existing bucket. Only propose a new one when the task clearly belongs to an \
ongoing area of work that none of the existing buckets covers, and that you'd expect to \
recur. A bucket is a lasting area of work, not a restatement of one task.

If you cannot place it confidently, say so and leave it uncategorised. A wrong bucket is \
worse than no bucket: it hides work in a column the person isn't looking at."""


class BucketSuggestion(BaseModel):
    bucket: str = Field(description="Bucket name — an existing one, a new one, or 'Uncategorized'")
    is_new: bool = Field(description="True only if this bucket does not already exist")
    keywords: list[str] = Field(
        default_factory=list,
        description="For a new bucket only: lowercase keywords that should match future tasks",
    )
    confidence: float = Field(ge=0, le=1, description="0 to 1")
    reasoning: str = Field(description="One short sentence explaining the choice")


MATCH_SYSTEM_PROMPT = """You attach an incoming item — a PR, a chat thread, an issue, a \
branch — to the tasks it belongs to on a personal dashboard.

You are given one item and the list of tasks that already exist, each with an id. Return \
only the tasks this item is genuinely, specifically part of.

Matching is NOT mandatory, and no match is the normal, expected outcome. Most items do not \
belong to any existing task — return an empty list unless you have a concrete reason (a shared \
ticket key, the same PR or branch, the same clearly-named subject). Do not stretch to find a \
match, and do not match on a vague topical resemblance ("both about the frontend"). A wrong \
attachment buries the item under the wrong subject, which is worse than leaving it to be filed \
by hand. When in doubt, return nothing. Never invent a task id: use only the ids given."""


class TaskMatch(BaseModel):
    task_id: str = Field(description="The id of an existing task this item belongs to")
    confidence: float = Field(ge=0, le=1, description="0 to 1")
    reason: str = Field(description="One short sentence on why it belongs to that task")


class TaskMatches(BaseModel):
    matches: list[TaskMatch] = Field(default_factory=list)


NEXT_ACTION_SYSTEM_PROMPT = (
    "You are a personal productivity assistant. Given a task and its recent items, predict the "
    "single most important next action the person should take.\n\n"
    'Be concrete and specific — not "review the PR" but "check the review comments on PR #42 and '
    'address the change-request from the last reviewer". If the items provide no clear signal, say '
    "so honestly. Keep the answer to one or two sentences."
)


class NextAction(BaseModel):
    action: str = Field(description="The next action to take, in one or two sentences")
    confidence: float = Field(ge=0, le=1, description="Confidence that this is the right next step")


@dataclass
class AIStatus:
    available: bool
    source: str  # "keychain" | "environment" | "cli-login" | "claude-cli" | "none"
    detail: str


def _api_key() -> str | None:
    return get_secret_store().get(SECRET_NAMESPACE, "api_key")


def _stored_key() -> str | None:
    return get_secret_store().stored(SECRET_NAMESPACE, "api_key")


def _client():
    from anthropic import AsyncAnthropic

    key = _api_key()
    # Passing api_key=None would blow away the SDK's own resolution chain, which is what
    # finds the `ant auth login` profile.
    return AsyncAnthropic(api_key=key) if key else AsyncAnthropic()


def _claude_cli() -> str | None:
    """The path to the local `claude` CLI, if it's installed — the subscription-priced brain."""
    return shutil.which("claude")


def status() -> AIStatus:
    if _stored_key():
        return AIStatus(True, "keychain", "Using the API key you saved in Admin")

    import os

    if _api_key() or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return AIStatus(True, "environment", "Using a key from the environment")

    if _has_cli_profile():
        return AIStatus(True, "cli-login", "Using your local `ant auth login` session")

    if _claude_cli():
        return AIStatus(True, "claude-cli", "Using your local `claude` CLI (subscription pricing)")

    return AIStatus(
        False,
        "none",
        "No credentials. Add an API key (console.anthropic.com → API Keys), run "
        "`ant auth login`, or install the `claude` CLI to use your subscription.",
    )


def _has_cli_profile() -> bool:
    import os
    from pathlib import Path

    config_dir = Path(os.environ.get("ANTHROPIC_CONFIG_DIR", Path.home() / ".config" / "anthropic"))
    credentials = config_dir / "credentials"
    return credentials.is_dir() and any(credentials.glob("*.json"))


async def suggest_bucket(db: AsyncSession, task: Task) -> BucketSuggestion:
    current = status()
    if not current.available:
        raise RuntimeError(current.detail)
    matcher = await load_matcher(db)
    existing = [rule.name for rule in matcher.rules]
    suggestion = await _structured(SYSTEM_PROMPT, _build_prompt(task, existing), BucketSuggestion)

    # The model can call a bucket new that already exists, differing only in case.
    matched = next((name for name in existing if name.lower() == suggestion.bucket.lower()), None)
    if matched:
        suggestion.bucket = matched
        suggestion.is_new = False
    elif suggestion.bucket.strip().lower() == UNCATEGORIZED.lower():
        suggestion.bucket = UNCATEGORIZED
        suggestion.is_new = False

    log.info("bucket_suggested", task=task.id, bucket=suggestion.bucket, is_new=suggestion.is_new)
    return suggestion


async def suggest_tasks(db: AsyncSession, item: Item) -> list[TaskMatch]:
    """Ask the brain which existing tasks an item belongs to. On-demand, never on sync."""
    current = status()
    if not current.available:
        raise RuntimeError(current.detail)
    stmt = select(Task).where(Task.archived_at.is_(None)).order_by(Task.updated_at.desc())
    tasks = list((await db.execute(stmt)).scalars().all())
    if not tasks:
        return []

    result = await _structured(MATCH_SYSTEM_PROMPT, _build_match_prompt(item, tasks), TaskMatches)

    # The brain often drops the "task:" id prefix, so resolve on the bare id — otherwise a
    # genuine, confident match is silently discarded as an unknown id. Then keep only the
    # confident ones: a half-hearted guess is worse than leaving the item to be filed by hand.
    by_bare = {task.id.removeprefix("task:"): task.id for task in tasks}
    matches = []
    for m in result.matches:
        real_id = by_bare.get(m.task_id.removeprefix("task:"))
        if real_id is not None and m.confidence >= MATCH_FLOOR:
            matches.append(TaskMatch(task_id=real_id, confidence=m.confidence, reason=m.reason))
    matches.sort(key=lambda m: m.confidence, reverse=True)
    log.info("tasks_suggested", item=item.id, matches=len(matches))
    return matches


def _build_match_prompt(item: Item, tasks: list[Task]) -> str:
    keys = (item.extra.get("reference_keys") or []) + (item.extra.get("identity_keys") or [])
    lines = "\n".join(
        f"- {t.id} | {t.title}{f' — {t.description}' if t.description else ''} | bucket: {t.bucket}"
        for t in tasks[:40]
    )
    return f"""Item:
  source: {item.source}
  label: {item.label}
  context: {item.context or "none"}
  keys: {", ".join(keys) or "none"}

Existing tasks (id | title[description] | bucket):
{lines}

Which of these tasks does the item belong to? Return only genuine matches, none if unsure."""


def _build_prompt(task: Task, existing: list[str]) -> str:
    all_items = [link.item for link in task.links if link.state != "rejected"]
    sources = sorted({item.source for item in all_items})
    mention_lines = "\n".join(f"- [{m.source}] {m.label}" for m in all_items[:8])
    return f"""Existing buckets: {", ".join(existing) if existing else "none yet"}

Task: {task.title}
Tags: {", ".join(task.tags) or "none"}
Appears in: {", ".join(sources)}

Where it was mentioned:
{mention_lines}"""


async def next_action(task: Task) -> NextAction:
    """Ask the brain for the most important next step on a task, using its confirmed items."""
    current = status()
    if not current.available:
        raise RuntimeError(current.detail)
    return await _structured(NEXT_ACTION_SYSTEM_PROMPT, _build_next_action_prompt(task), NextAction)


def _build_next_action_prompt(task: Task) -> str:
    all_items = [link.item for link in task.links if link.state != "rejected"]
    item_lines = "\n".join(
        f"- [{item.source}] {item.label}{f' — {item.context}' if item.context else ''}"
        for item in all_items[:12]
    )
    desc_line = f"\nDescription: {task.description}" if task.description else ""
    return f"""Task: {task.title}{desc_line}
Bucket: {task.bucket}
Status: {task.status}

Items (most recent first):
{item_lines or "(no items yet)"}

What is the single most important next action?"""


async def _structured(system: str, prompt: str, model_cls: type[_Structured]) -> _Structured:
    """Ask the available brain for a structured answer — SDK when there's a key, the local
    `claude` CLI otherwise. Both are held to the same schema."""
    current = status()
    if not current.available:
        raise RuntimeError(current.detail)
    if current.source == "claude-cli":
        return await _structured_via_cli(system, prompt, model_cls)
    return await _structured_via_sdk(system, prompt, model_cls)


async def _structured_via_sdk(system: str, prompt: str, model_cls: type[_Structured]) -> _Structured:
    client = _client()
    response = await client.messages.parse(
        model=MODEL,
        max_tokens=1024,
        system=system,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": prompt}],
        output_format=model_cls,
    )
    return response.parsed_output


async def _structured_via_cli(system: str, prompt: str, model_cls: type[_Structured]) -> _Structured:
    schema = json.dumps(model_cls.model_json_schema())
    ask = (
        f"{system}\n\n{prompt}\n\n"
        f"Respond with ONLY a JSON object — no markdown fences, no prose — matching this "
        f"JSON schema:\n{schema}"
    )
    raw = await _run_claude_cli(ask)
    return model_cls.model_validate(_extract_json(raw))


async def _run_claude_cli(prompt: str) -> str:
    """Run `claude -p` once and return the assistant's text. `--output-format json` wraps the
    reply in an envelope whose `result` is what we want."""
    claude = _claude_cli()
    if claude is None:
        raise RuntimeError("The `claude` CLI is not on PATH")

    proc = await asyncio.create_subprocess_exec(
        claude,
        "-p",
        prompt,
        "--output-format",
        "json",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=CLI_TIMEOUT_S)
    except TimeoutError as exc:
        proc.kill()
        raise RuntimeError("The `claude` CLI timed out") from exc

    if proc.returncode != 0:
        detail = err.decode(errors="replace").strip() or "unknown error"
        raise RuntimeError(f"The `claude` CLI failed: {detail[:300]}")

    text = out.decode(errors="replace")
    try:
        envelope = json.loads(text)
    except json.JSONDecodeError:
        return text
    return envelope.get("result", "") if isinstance(envelope, dict) else text


def _extract_json(text: str) -> dict:
    """Pull the JSON object out of a reply, tolerating stray markdown fences or prose."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        block = re.search(r"\{.*\}", text, re.DOTALL)
        if block:
            return json.loads(block.group(0))
        raise RuntimeError("The `claude` CLI did not return JSON") from exc
