"""Slack messages, via search.messages.

Needs a *user* token (xoxp-) with the `search:read` scope — a bot token cannot search.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import ClassVar

import httpx

from app.sources.base import ConfigField, RawItem, Source
from app.sources.keys import all_reference_keys

API_ROOT = "https://slack.com/api"
SEARCH_WINDOW_DAYS = 14
MAX_LABEL_CHARS = 100


# Slack has no CLI to read a token from, but it does take a manifest — which spares the
# user picking scopes out of a long list and getting it subtly wrong.
MANIFEST = """\
display_information:
  name: Personal HQ
  description: Reads your threads into your personal dashboard
  background_color: "#2c2d30"
oauth_config:
  scopes:
    user:
      - search:read
settings:
  org_deploy_enabled: false
  socket_mode_enabled: false
  token_rotation_enabled: false
"""


class SlackSource(Source):
    id = "slack"
    name = "Slack"
    description = "Threads you wrote in or were mentioned in"
    setup = (
        "Two ways in. If you can install an app: create one from the manifest below, install "
        "it, and paste the User OAuth Token (xoxp-). If your workspace requires admin approval "
        "you can't get, use your browser session instead — paste the xoxc- token and the xoxd- "
        "cookie your logged-in Slack already holds. The session route is your own login, needs "
        "no approval, but breaks when you log out of Slack and may run against your workspace's "
        "policy — that's your call."
    )
    setup_url = "https://api.slack.com/apps?new_app=1"
    manifest = MANIFEST
    manifest_hint = "Slack → Create an app → From a manifest → paste this"
    fields: ClassVar[list[ConfigField]] = [
        ConfigField(
            key="user_token",
            label="Token",
            kind="secret",
            placeholder="xoxp-… or xoxc-…",
            help="An app user token (xoxp-), or your browser session token (xoxc-). Not a bot token (xoxb-).",
            help_url="https://api.slack.com/apps",
        ),
        ConfigField(
            key="cookie",
            label="Session cookie",
            kind="secret",
            required=False,
            placeholder="xoxd-…",
            help="Only for a session (xoxc-) token: the `d` cookie from your browser. Leave blank for xoxp-.",
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
        token = self.get("user_token")
        if not token:
            return False
        # A session token is useless without the cookie that authenticates it.
        if token.startswith("xoxc-"):
            return bool(self.get("cookie"))
        return True

    def detail(self) -> str:
        if not self.is_configured():
            return "Not configured"
        via = "browser session" if self.get("user_token").startswith("xoxc-") else "app token"
        return f"Own messages + items, last {SEARCH_WINDOW_DAYS} days · {via}"

    def _headers(self) -> dict[str, str]:
        headers = {"Authorization": f"Bearer {self.get('user_token')}"}
        cookie = self.get("cookie")
        if cookie:
            # Slack authenticates a session token by the paired `d` cookie, not the header
            # alone. urlencode because the raw value contains characters a header rejects.
            from urllib.parse import quote

            headers["Cookie"] = f"d={quote(cookie, safe='')}"
        return headers

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

    async def fetch(self) -> list[RawItem]:
        if not self.is_configured():
            return []
        by_id: dict[str, RawItem] = {}
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
                    item = _to_item(match)
                    # The same thread surfaces once per matching message; keep one per thread.
                    by_id.setdefault(item.id, item)
        return list(by_id.values())


def _after_date() -> str:
    from datetime import timedelta

    return (datetime.now(UTC) - timedelta(days=SEARCH_WINDOW_DAYS)).strftime("%Y-%m-%d")


def _to_item(match: dict) -> RawItem:
    channel = match.get("channel", {}) or {}
    channel_name = channel.get("name") or channel.get("id") or "dm"
    text = (match.get("text") or "").strip()
    ts = match.get("ts", "0")
    thread_ts = match.get("thread_ts") or ts

    label = text[:MAX_LABEL_CHARS] + ("…" if len(text) > MAX_LABEL_CHARS else "")

    return RawItem(
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
