"""Slack messages, via search.messages.

Needs a *user* token (xoxp-) with the `search:read` scope — a bot token cannot search.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import httpx

from app.sources.base import ConfigField, RawItem, Source
from app.sources.keys import all_reference_keys

API_ROOT = "https://slack.com/api"
SEARCH_WINDOW_DAYS = 14
MAX_LABEL_CHARS = 100

# A Slack member id: U (user) or W (Enterprise Grid) then its base-32-ish tail.
_USER_ID = re.compile(r"[UW][A-Z0-9]{7,}")
# Bare user mention (`<@U123>`) — one carrying a name (`<@U123|joe>`) needs no lookup.
_BARE_MENTION = re.compile(r"<@([UW][A-Z0-9]+)>")


# Slack takes a manifest — which spares the user picking scopes out of a long list and
# getting them subtly wrong. It lives beside this file as YAML so it stays editable as the
# thing it is. Most scopes are provisioned ahead of the features that use them: each added
# scope means another round of admin approval, so the ones an HQ user is likely to want are
# in the one manifest they get approved. Today only search:read is exercised (see fetch).
MANIFEST = (Path(__file__).parent / "slack_manifest.yaml").read_text(encoding="utf-8")


class SlackSource(Source):
    id = "slack"
    name = "Slack"
    description = "Threads you wrote in or were mentioned in"
    setup = (
        "Create an app from the manifest below, then open OAuth & Permissions and Install to "
        "Workspace — the token you want is the User OAuth Token (xoxp-) at the top of that "
        "page. Not the Client Secret or Signing Secret on the App Credentials page, and not a "
        "bot token (xoxb-). If installing needs admin approval, the manifest is what they approve."
    )
    setup_url = "https://api.slack.com/apps?new_app=1"
    manifest = MANIFEST
    manifest_hint = "Slack → Create an app → From a manifest → paste this"
    fields: ClassVar[list[ConfigField]] = [
        ConfigField(
            key="user_token",
            label="User token",
            kind="secret",
            placeholder="xoxp-…",
            help="A user token with the search:read scope. A bot token (xoxb-) cannot search.",
            help_url="https://api.slack.com/apps",
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
        return f"Own messages + items, last {SEARCH_WINDOW_DAYS} days"

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

    async def fetch(self) -> list[RawItem]:
        if not self.is_configured():
            return []
        matches: dict[str, dict] = {}
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
                    # The same thread surfaces once per matching message; keep one per thread.
                    matches.setdefault(_external_id(match), match)

            names = await self._resolve_users(
                client, {uid for match in matches.values() for uid in _mention_ids(match)}
            )
        return [_to_item(match, names) for match in matches.values()]

    async def _resolve_users(self, client: httpx.AsyncClient, ids: set[str]) -> dict[str, str]:
        """Ids -> display names. The directory answers first, so an id learned on an earlier
        sync (by any source) is never looked up again; only genuine misses hit users.info,
        and what they find is handed back to the directory. Best-effort: a missing users:read
        scope just leaves those names raw."""
        if not ids:
            return {}
        names = dict(await self.directory.known("slack", ids)) if self.directory else {}
        discovered: dict[str, str] = {}
        for uid in ids - names.keys():
            try:
                payload = await self._call(client, "users.info", {"user": uid})
            except (RuntimeError, httpx.HTTPError):
                continue
            discovered[uid] = _display_name(payload.get("user") or {})
        if self.directory and discovered:
            await self.directory.remember("slack", discovered)
        return {**names, **discovered}


def _after_date() -> str:
    from datetime import timedelta

    return (datetime.now(UTC) - timedelta(days=SEARCH_WINDOW_DAYS)).strftime("%Y-%m-%d")


def _external_id(match: dict) -> str:
    channel = match.get("channel") or {}
    ts = match.get("ts", "0")
    return f"{channel.get('id', 'unknown')}:{match.get('thread_ts') or ts}"


def _to_item(match: dict, names: dict[str, str]) -> RawItem:
    channel = match.get("channel") or {}
    raw = _message_text(match)
    ts = match.get("ts", "0")
    thread_ts = match.get("thread_ts") or ts

    rendered = _render(raw, names)
    label = rendered or _fallback_label(match)
    if len(label) > MAX_LABEL_CHARS:
        label = label[:MAX_LABEL_CHARS].rstrip() + "…"

    return RawItem(
        source="slack",
        external_id=f"{channel.get('id', 'unknown')}:{thread_ts}",
        label=label,
        occurred_at=datetime.fromtimestamp(float(ts), tz=UTC),
        url=match.get("permalink"),
        context=_channel_label(channel, names),
        status=None,
        # Slack never names a subject; it only ever points at one. So it contributes
        # references but no identity, and never wins the task title. Keys read the raw text
        # so a ticket ref inside a link or mention isn't lost to rendering.
        reference_keys=all_reference_keys(raw),
        extra={"thread_ts": thread_ts},
    )


def _display_name(user: dict) -> str:
    profile = user.get("profile") or {}
    return (
        profile.get("display_name")
        or profile.get("real_name")
        or user.get("real_name")
        or user.get("name")
        or user.get("id", "someone")
    )


def _mention_ids(match: dict) -> set[str]:
    """User ids the rendering will need a name for: bare in-text mentions and a DM's peer."""
    ids = {m.group(1) for m in _BARE_MENTION.finditer(_message_text(match))}
    channel = match.get("channel") or {}
    peer = _dm_peer(channel)
    if peer:
        ids.add(peer)
    return ids


def _message_text(match: dict) -> str:
    """The message's readable content, wherever it lives.

    A person's own message keeps it in `text`, but an app (a GitHub PR notice, a Linear
    bot, a quiz bot answering in a DM) puts everything in Block Kit `blocks` or in
    `attachments`, leaving `text` empty. Reading those is what stops such messages showing
    up as "(no text)".
    """
    text = (match.get("text") or "").strip()
    if text:
        return text
    blocks = _blocks_text(match.get("blocks"))
    if blocks:
        return blocks
    for attachment in match.get("attachments") or []:
        found = (
            _blocks_text(attachment.get("blocks"))
            or attachment.get("text")
            or attachment.get("fallback")
            or attachment.get("title")
            or attachment.get("pretext")
        )
        if found:
            return str(found).strip()
    return ""


def _blocks_text(blocks: list | None) -> str:
    parts: list[str] = []
    for block in blocks or []:
        kind = block.get("type")
        if kind in ("section", "header"):
            main = (block.get("text") or {}).get("text")
            if main:
                parts.append(main)
            parts += [f.get("text", "") for f in block.get("fields") or [] if f.get("text")]
        elif kind == "context":
            parts += [e.get("text", "") for e in block.get("elements") or [] if e.get("text")]
        elif kind == "rich_text":
            parts.append(_rich_text(block))
    return " ".join(part for part in parts if part).strip()


def _rich_text(block: dict) -> str:
    """Flatten a rich_text block back to a line, in Slack's own `<...>` markup so `_render`
    resolves the mentions, links and emoji it contains just like it does for plain text."""
    out: list[str] = []
    for section in block.get("elements") or []:
        for element in section.get("elements") or []:
            kind = element.get("type")
            if kind == "text":
                out.append(element.get("text", ""))
            elif kind == "link":
                out.append(element.get("text") or element.get("url", ""))
            elif kind == "emoji":
                out.append(f":{element.get('name', '')}:")
            elif kind == "user":
                out.append(f"<@{element.get('user_id', '')}>")
            elif kind == "usergroup":
                out.append(f"<!subteam^{element.get('usergroup_id', '')}>")
            elif kind == "broadcast":
                out.append(f"<!{element.get('range', '')}>")
    return "".join(out)


def _dm_peer(channel: dict) -> str:
    """The other person's id for a DM, or "" when this isn't a one-to-one channel."""
    if channel.get("is_mpim"):
        return ""
    name = (channel.get("name") or "").strip()
    if channel.get("is_im") or _USER_ID.fullmatch(name):
        return channel.get("user") or (name if _USER_ID.fullmatch(name) else "")
    return ""


def _channel_label(channel: dict, names: dict[str, str]) -> str:
    if channel.get("is_mpim"):
        return "group DM"
    peer = _dm_peer(channel)
    if peer or channel.get("is_im"):
        who = names.get(peer)
        return f"DM with @{who}" if who else "direct message"
    name = (channel.get("name") or "").strip()
    if name:
        return f"#{name}"
    return f"#{channel.get('id')}" if channel.get("id") else "Slack"


def _fallback_label(match: dict) -> str:
    """A message can be all file or attachment and no text — name it by what it carries."""
    for file in match.get("files") or []:
        title = file.get("title") or file.get("name")
        if title:
            return f"shared a file: {title}"
    for attachment in match.get("attachments") or []:
        for key in ("fallback", "title", "text", "pretext"):
            if attachment.get(key):
                return " ".join(str(attachment[key]).split())
    return "(no message text)"


def _render(text: str, names: dict[str, str]) -> str:
    """Turn Slack's control markup into plain, readable text.

    Slack wraps mentions, channels and links in angle brackets — `<@U123|joe>`,
    `<#C1|eng>`, `<https://x|label>` — and escapes only `& < >` in the visible text. Left
    raw these dominate the line, so each becomes what a person would read.
    """
    if not text:
        return ""

    def mention(m: re.Match) -> str:
        uid, name = m.group(1), m.group(2)
        return f"@{name or names.get(uid) or 'someone'}"

    text = re.sub(r"<@([UW][A-Z0-9]+)(?:\|([^>]+))?>", mention, text)
    text = re.sub(r"<#[CG][A-Z0-9]+(?:\|([^>]+))?>", lambda m: f"#{m.group(1) or 'channel'}", text)
    text = re.sub(r"<!subteam\^[A-Z0-9]+(?:\|([^>]+))?>", lambda m: f"@{m.group(1) or 'team'}", text)
    text = re.sub(r"<!(here|channel|everyone)>", lambda m: f"@{m.group(1)}", text)
    text = re.sub(r"<!date\^\d+\^[^>|]*(?:\|([^>]+))?>", lambda m: m.group(1) or "", text)
    # Links keep their label, or the bare URL when they carry none.
    text = re.sub(r"<(?:https?://|mailto:)[^>|]+\|([^>]+)>", lambda m: m.group(1), text)
    text = re.sub(r"<(?:mailto:)?((?:https?://)?[^>|]+)>", lambda m: m.group(1), text)

    text = html.unescape(text)
    return " ".join(text.split()).strip()
