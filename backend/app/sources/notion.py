"""Notion pages you created, own, or are mentioned in, via the API."""

from __future__ import annotations

from datetime import datetime
from typing import ClassVar

import httpx

from app.sources.base import ConfigField, RawItem, Source
from app.sources.keys import all_reference_keys

API_ROOT = "https://api.notion.com/v1"
# Pinned: Notion versions its API by date and rejects requests without this header.
NOTION_VERSION = "2022-06-28"


class NotionSource(Source):
    id = "notion"
    name = "Notion"
    description = "Pages you created, own, or are mentioned in"
    setup = (
        "Notion → Settings → Connections → Develop or manage integrations → New internal "
        "integration. Copy its token, then open each page or database you want HQ to see and, "
        "under ••• → Connections, add the integration — it only ever sees what it is shared with."
    )
    setup_url = "https://www.notion.so/my-integrations"
    fields: ClassVar[list[ConfigField]] = [
        ConfigField(
            key="token",
            label="Integration token",
            kind="secret",
            placeholder="ntn_… / secret_…",
            help="An internal integration token, shared with the pages you want surfaced.",
            help_url="https://www.notion.so/my-integrations",
        ),
        ConfigField(
            key="user_id",
            label="Your Notion user ID",
            placeholder="UUID",
            help="Whose pages to surface. Leave blank and Test connection reads it from the token.",
            required=False,
        ),
    ]

    def detail(self) -> str:
        return "Pages you created, own or are mentioned in" if self.is_configured() else "Not configured"

    def is_configured(self) -> bool:
        return bool(self.get("token"))

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.get('token')}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    async def check(self) -> None:
        await super().check()
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{API_ROOT}/users/me", headers=self._headers())
            response.raise_for_status()

    async def _resolve_user_id(self, client: httpx.AsyncClient) -> str:
        """Who 'you' are. A token's bot user isn't the human, so an internal integration owned
        by a person carries them in `bot.owner.user`; that spares pasting a UUID by hand."""
        configured = self.get("user_id")
        if configured:
            return configured
        response = await client.get(f"{API_ROOT}/users/me", headers=self._headers())
        response.raise_for_status()
        owner = (response.json().get("bot") or {}).get("owner") or {}
        return (owner.get("user") or {}).get("id", "")

    async def fetch(self) -> list[RawItem]:
        if not self.is_configured():
            return []
        async with httpx.AsyncClient(timeout=20) as client:
            user_id = await self._resolve_user_id(client)
            # Without knowing who you are, creator and owner are unanswerable — surface nothing
            # rather than everything the integration happens to see.
            if not user_id:
                return []
            pages = await self._search_pages(client)
            names: dict[str, str] = {}
            items = []
            for page in pages:
                item = await self._page_item(client, page, user_id, names)
                if item is not None:
                    items.append(item)
            return items

    async def _search_pages(self, client: httpx.AsyncClient) -> list[dict]:
        response = await client.post(
            f"{API_ROOT}/search",
            headers=self._headers(),
            json={
                "filter": {"value": "page", "property": "object"},
                "sort": {"direction": "descending", "timestamp": "last_edited_time"},
                "page_size": 50,
            },
        )
        response.raise_for_status()
        return [r for r in response.json().get("results", []) if r.get("object") == "page"]

    async def _page_item(
        self, client: httpx.AsyncClient, page: dict, user_id: str, names: dict[str, str]
    ) -> RawItem | None:
        creator = _user_id_of(page.get("created_by"))
        owner = _user_id_of(page.get("last_edited_by"))
        _seed_name(names, page.get("created_by"))
        _seed_name(names, page.get("last_edited_by"))

        commenters, mentioned = await self._scan_comments(client, page["id"], names)

        involved = user_id in {creator, owner} or user_id in mentioned or user_id in commenters
        if not involved:
            return None

        people: list[dict] = []
        _add_person(people, "notion", creator, await self._name(client, creator, names), "creator")
        if owner != creator:
            _add_person(people, "notion", owner, await self._name(client, owner, names), "owner")
        for uid in commenters:
            _add_person(people, "notion", uid, await self._name(client, uid, names), "commenter")
        for uid in mentioned:
            _add_person(people, "notion", uid, await self._name(client, uid, names), "mentioned")

        title = _page_title(page)
        return RawItem(
            source="notion",
            external_id=page["id"],
            label=title,
            occurred_at=datetime.fromisoformat(page["last_edited_time"].replace("Z", "+00:00")),
            url=page.get("url"),
            title=title,
            reference_keys=all_reference_keys(title),
            people=people,
            extra={},
        )

    async def _scan_comments(
        self, client: httpx.AsyncClient, page_id: str, names: dict[str, str]
    ) -> tuple[list[str], list[str]]:
        """Who commented on a page and who a comment mentions. Comment access is a distinct
        capability an integration may lack, so a failure here just means no comment signal —
        it never sinks the page or the sync."""
        try:
            response = await client.get(
                f"{API_ROOT}/comments", headers=self._headers(), params={"block_id": page_id}
            )
            response.raise_for_status()
        except httpx.HTTPError:
            return [], []

        commenters: list[str] = []
        mentioned: list[str] = []
        for comment in response.json().get("results", []):
            author = _user_id_of(comment.get("created_by"))
            _seed_name(names, comment.get("created_by"))
            if author and author not in commenters:
                commenters.append(author)
            for span in comment.get("rich_text", []):
                mention = (span.get("mention") or {}).get("user") if span.get("type") == "mention" else None
                if mention and mention.get("id"):
                    _seed_name(names, mention)
                    if mention["id"] not in mentioned:
                        mentioned.append(mention["id"])
        return commenters, mentioned

    async def _name(self, client: httpx.AsyncClient, uid: str, names: dict[str, str]) -> str:
        if not uid:
            return uid
        if uid in names:
            return names[uid]
        try:
            response = await client.get(f"{API_ROOT}/users/{uid}", headers=self._headers())
            if response.is_success:
                names[uid] = response.json().get("name") or uid
        except httpx.HTTPError:
            pass
        return names.get(uid, uid)


def _user_id_of(ref: dict | None) -> str:
    return (ref or {}).get("id", "")


def _seed_name(names: dict[str, str], ref: dict | None) -> None:
    """Take a name off a user object Notion already embedded, to save a /users lookup."""
    ref = ref or {}
    if ref.get("id") and ref.get("name"):
        names[ref["id"]] = ref["name"]


def _add_person(people: list[dict], kind: str, value: str, name: str, role: str) -> None:
    if not value or any(p["value"] == value for p in people):
        return
    people.append({"kind": kind, "value": value, "name": name, "role": role})


def _page_title(page: dict) -> str:
    """A page's title lives in whichever property has type 'title' — the key isn't fixed."""
    for prop in (page.get("properties") or {}).values():
        if prop.get("type") == "title":
            text = "".join(span.get("plain_text", "") for span in prop.get("title", [])).strip()
            if text:
                return text
    return "Untitled"
