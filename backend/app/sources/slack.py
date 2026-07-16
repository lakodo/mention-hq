"""Slack messages, via search.messages.

Needs a *user* token (xoxp-) with the `search:read` scope — a bot token cannot search.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

import httpx

from app.sources.base import ConfigField, RawMention, Source
from app.sources.keys import all_reference_keys

API_ROOT = "https://slack.com/api"
SEARCH_WINDOW_DAYS = 14
MAX_LABEL_CHARS = 100


class SlackSource(Source):
    id = "slack"
    name = "Slack"
    description = "Threads you wrote in or were mentioned in"
    fields: ClassVar[list[ConfigField]] = [
        ConfigField(
            key="user_token",
            label="User token",
            kind="secret",
            placeholder="xoxp-…",
            help="Must be a user token with the search:read scope — a bot token cannot search",
        ),
        ConfigField(
            key="user_id",
            label="Your Slack user ID",
            placeholder="U01234567",
            help="Leave blank to detect it from the token",
            required=False,
        ),
    ]

    def is_configured(self) -> bool:
        return bool(self.get("user_token"))

    def detail(self) -> str:
        if not self.is_configured():
            return "Not configured"
        return f"Own messages + mentions, last {SEARCH_WINDOW_DAYS} days"

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.get('user_token')}"}

    async def _call(self, client: httpx.AsyncClient, method: str, params: dict) -> dict:
        response = await client.get(f"{API_ROOT}/{method}", headers=self._headers(), params=params)
        response.raise_for_status()
        payload = response.json()
        # Slack returns HTTP 200 with ok:false for auth and scope errors.
        if not payload.get("ok"):
            raise RuntimeError(f"Slack {method} failed: {payload.get('error', 'unknown error')}")
        return payload

    async def check(self) -> None:
        await super().check()
        async with httpx.AsyncClient(timeout=10) as client:
            await self._call(client, "auth.test", {})

    async def _user_id(self, client: httpx.AsyncClient) -> str:
        configured = self.get("user_id")
        if configured:
            return configured
        # The token identifies the user, so make them paste an ID only if we can't ask.
        payload = await self._call(client, "auth.test", {})
        return payload["user_id"]

    async def fetch(self) -> list[RawMention]:
        if not self.is_configured():
            return []
        by_id: dict[str, RawMention] = {}
        async with httpx.AsyncClient(timeout=20) as client:
            user_id = await self._user_id(client)
            queries = [f"from:<@{user_id}>", f"to:<@{user_id}>"]
            for query in queries:
                payload = await self._call(
                    client,
                    "search.messages",
                    {"query": f"{query} after:{_after_date()}", "count": 50, "sort": "timestamp"},
                )
                for match in payload.get("messages", {}).get("matches", []):
                    mention = _to_mention(match)
                    # The same thread surfaces once per matching message; keep one per thread.
                    by_id.setdefault(mention.id, mention)
        return list(by_id.values())


def _after_date() -> str:
    from datetime import timedelta

    return (datetime.now(UTC) - timedelta(days=SEARCH_WINDOW_DAYS)).strftime("%Y-%m-%d")


def _to_mention(match: dict) -> RawMention:
    channel = match.get("channel", {}) or {}
    channel_name = channel.get("name") or channel.get("id") or "dm"
    text = (match.get("text") or "").strip()
    ts = match.get("ts", "0")
    thread_ts = match.get("thread_ts") or ts

    label = text[:MAX_LABEL_CHARS] + ("…" if len(text) > MAX_LABEL_CHARS else "")

    return RawMention(
        source="slack",
        external_id=f"{channel.get('id', 'unknown')}:{thread_ts}",
        label=label or "(no text)",
        occurred_at=datetime.fromtimestamp(float(ts), tz=UTC),
        url=match.get("permalink"),
        context=f"#{channel_name}",
        status=None,
        # Slack never names a subject; it only ever points at one. So it contributes
        # references but no identity, and never wins the task title.
        reference_keys=all_reference_keys(text),
        extra={"channel_name": channel_name, "thread_ts": thread_ts},
    )
