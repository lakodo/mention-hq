"""Slack messages, via search.messages.

Needs a *user* token (xoxp-) with the `search:read` scope — a bot token cannot search.
"""

from __future__ import annotations

import html
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

import emoji as emoji_lib
import httpx

from app.sources.base import ConfigField, RawItem, Source
from app.sources.keys import all_reference_keys

API_ROOT = "https://slack.com/api"
SEARCH_WINDOW_DAYS = 14
# The message part of a label — kept short so catch-up stays scannable; the full thread is
# a click away on its permalink.
MAX_BODY_CHARS = 50

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
        ConfigField(
            key="emoji_urls",
            label="Custom emoji image URLs",
            placeholder="https://emoji.slack-edge.com/T…/party-parrot/….png https://…/marmot-wave/….gif",
            help=(
                "Paste the image URLs of your workspace's custom emoji (space-separated). "
                "HQ reads the emoji name from each URL and renders those :shortcodes: as the "
                "image. Standard emoji already render without this."
            ),
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
                    # One item per thread: a name pinged on the root and again in replies must
                    # not turn into a pile of items. Group on the thread's root, and keep the
                    # earliest match — the root itself when it surfaced, else the first reply.
                    key = _external_id(match)
                    current = matches.get(key)
                    if current is None or _ts(match) < _ts(current):
                        matches[key] = match

            names = await self._resolve_users(
                client, {uid for match in matches.values() for uid in _mention_ids(match)}
            )
        emoji = _parse_emoji_urls(self.get("emoji_urls"))
        return [_to_item(match, names, emoji) for match in matches.values()]

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


def _ts(match: dict) -> float:
    try:
        return float(match.get("ts", "0"))
    except ValueError:
        return 0.0


def _thread_ts(match: dict) -> str:
    """The thread's root timestamp, which every message in it shares.

    Search results drop `thread_ts` on replies as often as not, so fall back to the one
    Slack always puts in a reply's permalink (`…?thread_ts=…`). A message in no thread is
    its own root.
    """
    if match.get("thread_ts"):
        return match["thread_ts"]
    found = re.search(r"[?&]thread_ts=([0-9.]+)", match.get("permalink") or "")
    return found.group(1) if found else match.get("ts", "0")


def _external_id(match: dict) -> str:
    channel = match.get("channel") or {}
    return f"{channel.get('id', 'unknown')}:{_thread_ts(match)}"


def _parse_emoji_urls(raw: str | None) -> dict[str, str]:
    """Map a custom emoji name to its image URL from space-separated Slack emoji URLs.

    A Slack emoji URL ends `.../{name}/{hash}.{ext}`, so the name is the second-to-last path
    segment: `…/emoji.slack-edge.com/T04/party-parrot/abc.png` -> `party-parrot`.
    """
    out: dict[str, str] = {}
    for url in (raw or "").split():
        parts = url.rstrip("/").split("/")
        if len(parts) >= 2 and parts[-2]:
            out[parts[-2]] = url
    return out


def _to_item(match: dict, names: dict[str, str], emoji: dict[str, str]) -> RawItem:
    channel = match.get("channel") or {}
    raw = _message_text(match)
    thread_ts = _thread_ts(match)

    body = _render(raw, names) or _fallback_label(match)
    if len(body) > MAX_BODY_CHARS:
        body = body[:MAX_BODY_CHARS].rstrip() + "…"
    # "#channel - message" (or "DM with @x - message"), so an item reads as itself without a
    # second line, and a thread that pinged you five times still shows as one.
    label = f"{_channel_label(channel, names)} - {body}"

    # Which configured custom emoji actually appear, so the frontend can render just those.
    used = {name: url for name, url in emoji.items() if f":{name}:" in label}

    return RawItem(
        source="slack",
        external_id=f"{channel.get('id', 'unknown')}:{thread_ts}",
        label=label,
        occurred_at=datetime.fromtimestamp(_ts(match), tz=UTC),
        url=match.get("permalink"),
        context=None,
        status=None,
        # Slack never names a subject; it only ever points at one. So it contributes
        # references but no identity, and never wins the task title. Keys read the raw text
        # so a ticket ref inside a link or mention isn't lost to rendering.
        reference_keys=all_reference_keys(raw),
        extra={"thread_ts": thread_ts, "emoji": used},
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
    # Sharing a Slack message posts its permalink as the text and unfurls the quoted message
    # into an attachment. The bare link reads as nothing, so prefer the quoted content.
    shared = _shared_message_text(match)
    if shared and (not text or _is_only_slack_link(text)):
        return shared
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


_SLACK_LINK_ONLY = re.compile(r"^<?https?://[\w.-]+\.slack\.com/archives/\S+?>?$")


def _is_only_slack_link(text: str) -> bool:
    return bool(_SLACK_LINK_ONLY.match(text.strip()))


def _shared_message_text(match: dict) -> str | None:
    """The quoted message from a shared/unfurled Slack link, as `author in #channel: body`."""
    for att in match.get("attachments") or []:
        is_share = att.get("is_msg_unfurl") or att.get("is_share")
        if not is_share and "/archives/" not in (att.get("from_url") or ""):
            continue
        body = (att.get("text") or att.get("fallback") or "").strip()
        author = att.get("author_name") or att.get("author_subname")
        channel_name = att.get("channel_name")
        # Show it as Slack does — "#mo". `footer` is the fallback and is usually pre-formatted.
        channel = f"#{channel_name}" if channel_name else att.get("footer")
        where = f" in {channel}" if channel else ""
        prefix = f"{author}{where}" if author else (channel or "")
        if prefix and body:
            return f"{prefix}: {body}"
        return body or prefix or None
    return None


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
    # :fire: -> 🔥. Custom workspace emoji (:party-parrot:) have no Unicode, so stay as-is.
    text = emoji_lib.emojize(text, language="alias")
    return " ".join(text.split()).strip()
