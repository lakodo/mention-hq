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

from dataclasses import dataclass

import structlog
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Task
from app.security import get_secret_store
from app.services.buckets import UNCATEGORIZED, load_matcher

log = structlog.get_logger(__name__)

MODEL = "claude-opus-4-8"
SECRET_NAMESPACE = "anthropic"

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


@dataclass
class AIStatus:
    available: bool
    source: str  # "keychain" | "environment" | "cli-login" | "none"
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


def status() -> AIStatus:
    try:
        import anthropic  # noqa: F401
    except ImportError:
        return AIStatus(False, "none", "The anthropic package is not installed")

    if _stored_key():
        return AIStatus(True, "keychain", "Using the API key you saved in Admin")

    import os

    if _api_key() or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return AIStatus(True, "environment", "Using a key from the environment")

    if _has_cli_profile():
        return AIStatus(True, "cli-login", "Using your local `ant auth login` session")

    return AIStatus(
        False,
        "none",
        "No credentials. Run `ant auth login`, or add an API key in Admin.",
    )


def _has_cli_profile() -> bool:
    import os
    from pathlib import Path

    config_dir = Path(os.environ.get("ANTHROPIC_CONFIG_DIR", Path.home() / ".config" / "anthropic"))
    credentials = config_dir / "credentials"
    return credentials.is_dir() and any(credentials.glob("*.json"))


async def suggest_bucket(db: AsyncSession, task: Task) -> BucketSuggestion:
    if not status().available:
        raise RuntimeError(status().detail)

    matcher = await load_matcher(db)
    existing = [rule.name for rule in matcher.rules]

    sources = sorted({item.source for item in task.items})
    mention_lines = "\n".join(f"- [{m.source}] {m.label}" for m in task.items[:8])

    prompt = f"""Existing buckets: {", ".join(existing) if existing else "none yet"}

Task: {task.title}
Tags: {", ".join(task.tags) or "none"}
Appears in: {", ".join(sources)}

Where it was mentioned:
{mention_lines}"""

    client = _client()
    response = await client.messages.parse(
        model=MODEL,
        max_tokens=1024,
        system=SYSTEM_PROMPT,
        output_config={"effort": "low"},
        messages=[{"role": "user", "content": prompt}],
        output_format=BucketSuggestion,
    )

    suggestion = response.parsed_output
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
