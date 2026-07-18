"""Notion pages you created, own, or are mentioned in, via the API."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import ClassVar

import httpx

from app.sources.base import ConfigField, RawItem, Source, SourceNotConfigured
from app.sources.keys import all_reference_keys

API_ROOT = "https://api.notion.com/v1"
AUTHORIZE_URL = f"{API_ROOT}/oauth/authorize"
TOKEN_URL = f"{API_ROOT}/oauth/token"
# Pinned: Notion versions its API by date and rejects requests without this header.
NOTION_VERSION = "2022-06-28"
# Refresh a little before the token actually lapses, so a sync never races the expiry.
_EXPIRY_SKEW = timedelta(minutes=5)


class NotionSource(Source):
    id = "notion"
    name = "Notion"
    description = "Pages you created, own, or are mentioned in"
    setup = (
        "In the Notion developer portal, create a New connection with the OAuth method, then "
        "copy its Client ID and Client secret below. Register the redirect URI HQ shows you, "
        "enable the read content / comments / user information capabilities, and click Connect. "
        "If your admin allows static tokens instead, paste a personal access token as the token."
    )
    setup_url = "https://www.notion.so/my-integrations"
    fields: ClassVar[list[ConfigField]] = [
        ConfigField(
            key="client_id",
            label="OAuth client ID",
            placeholder="From the connection's settings",
            help="Create a connection (OAuth) in the developer portal and copy its Client ID.",
            help_url="https://www.notion.so/my-integrations",
            required=False,
        ),
        ConfigField(
            key="client_secret",
            label="OAuth client secret",
            kind="secret",
            help="The connection's Client secret. Used only to exchange the login for a token.",
            required=False,
        ),
        ConfigField(
            key="token",
            label="Token",
            kind="secret",
            placeholder="Filled by Connect — or paste a personal token",
            help="Set by the OAuth Connect flow. You can also paste a personal access token here.",
            required=False,
        ),
        ConfigField(
            key="user_id",
            label="Your Notion user ID",
            placeholder="UUID",
            help="Whose pages to surface. Left blank, it is read from the token owner.",
            required=False,
        ),
        ConfigField(key="refresh_token", label="Refresh token", kind="secret", required=False, hidden=True),
        ConfigField(key="token_expiry", label="Token expiry", required=False, hidden=True),
    ]

    def detail(self) -> str:
        return "Pages you created, own or are mentioned in" if self.is_configured() else "Not configured"

    def is_configured(self) -> bool:
        return bool(self.get("token"))

    def oauth_configured(self) -> bool:
        return bool(self.get("client_id") and self.get("client_secret"))

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.get('token')}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        }

    async def check(self) -> None:
        if not self.is_configured():
            raise SourceNotConfigured("Connect to Notion, or paste a token")
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.get(f"{API_ROOT}/users/me", headers=self._headers())
            response.raise_for_status()

    def authorize_url(self, redirect_uri: str, state: str) -> str:
        params = httpx.QueryParams(
            client_id=self.get("client_id"),
            redirect_uri=redirect_uri,
            response_type="code",
            owner="user",
            state=state,
        )
        return f"{AUTHORIZE_URL}?{params}"

    async def exchange_code(self, code: str, redirect_uri: str) -> dict[str, str]:
        """Trade the one-time code from the consent redirect for tokens."""
        return await self._token_request(
            {"grant_type": "authorization_code", "code": code, "redirect_uri": redirect_uri}
        )

    async def prepare(self) -> dict[str, str] | None:
        """Refresh the access token when it's about to lapse, so the coming sync uses a live one.
        Only possible with a refresh token, which only the OAuth flow yields."""
        if not self.get("refresh_token") or not self._expired():
            return None
        return await self._token_request(
            {"grant_type": "refresh_token", "refresh_token": self.get("refresh_token")}
        )

    async def _token_request(self, payload: dict[str, str]) -> dict[str, str]:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                TOKEN_URL,
                auth=(self.get("client_id"), self.get("client_secret")),
                headers={"Notion-Version": NOTION_VERSION},
                json=payload,
            )
            response.raise_for_status()
            body = response.json()

        updates = {
            "token": body["access_token"],
            "user_id": ((body.get("owner") or {}).get("user") or {}).get("id", "") or self.get("user_id"),
        }
        if body.get("refresh_token"):
            updates["refresh_token"] = body["refresh_token"]
        # Notion tokens may or may not expire; only track it when told an expiry.
        if body.get("expires_in"):
            expiry = datetime.now(UTC) + timedelta(seconds=int(body["expires_in"]))
            updates["token_expiry"] = expiry.isoformat()
        return updates

    def _expired(self) -> bool:
        raw = self.get("token_expiry")
        if not raw:
            return False
        return datetime.fromisoformat(raw) - _EXPIRY_SKEW <= datetime.now(UTC)

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
