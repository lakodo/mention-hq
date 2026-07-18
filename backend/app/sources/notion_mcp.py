"""Notion via its hosted MCP server (https://mcp.notion.com/mcp).

The plain Notion source needs a workspace token or an OAuth app, both of which an admin can
disable org-wide. The MCP server authorises differently: it supports dynamic client
registration (RFC 7591) and PKCE, so HQ registers itself on the fly and logs the user in
with no admin-provisioned credential — the path that survives a locked-down workspace.

Reads happen over MCP: initialize a session, then call the server's `search` tool and map
what it returns into items. The OAuth mechanics are pinned by tests; the tool's exact output
shape is verified against a live connection.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
from datetime import UTC, datetime, timedelta
from typing import ClassVar

import httpx

from app.sources.base import ConfigField, RawItem, Source, SourceNotConfigured
from app.sources.keys import all_reference_keys

MCP_URL = "https://mcp.notion.com/mcp"
REGISTER_URL = "https://mcp.notion.com/register"
AUTHORIZE_URL = "https://mcp.notion.com/authorize"
TOKEN_URL = "https://mcp.notion.com/token"
# The MCP protocol revision HQ speaks; the server echoes the one it settles on.
PROTOCOL_VERSION = "2025-06-18"
_EXPIRY_SKEW = timedelta(minutes=5)


def pkce_pair() -> tuple[str, str]:
    """A PKCE (verifier, S256 challenge). The verifier is kept until the token exchange; the
    challenge goes out in the authorize URL, so a stolen code alone can't be redeemed."""
    verifier = base64.urlsafe_b64encode(hashlib.sha256(_rand()).digest()).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    return verifier, challenge


def _rand() -> bytes:
    from secrets import token_bytes

    return token_bytes(32)


class NotionMcpSource(Source):
    id = "notion_mcp"
    name = "Notion MCP"
    description = "Notion pages, over the hosted MCP server (no admin token needed)"
    setup = (
        "No credentials to paste: click Connect, log in to Notion in the popup, and approve "
        "access. HQ registers itself with Notion's MCP server automatically. Works even where "
        "an admin has disabled API tokens and OAuth apps, as long as you have MCP access."
    )
    setup_url = "https://mcp.notion.com"
    fields: ClassVar[list[ConfigField]] = [
        ConfigField(
            key="query",
            label="Search terms",
            required=False,
            placeholder="e.g. a project or team name — one per line",
            help="Notion MCP search is query-based (there's no list-everything). Give a term "
            "per line or comma; each is searched and the results merged.",
        ),
        ConfigField(key="token", label="Access token", kind="secret", required=False, hidden=True),
        ConfigField(key="refresh_token", label="Refresh token", kind="secret", required=False, hidden=True),
        ConfigField(key="token_expiry", label="Token expiry", required=False, hidden=True),
        ConfigField(key="client_id", label="MCP client id", required=False, hidden=True),
    ]

    def detail(self) -> str:
        return "Connected over MCP" if self.is_configured() else "Not connected"

    def is_configured(self) -> bool:
        return bool(self.get("token"))

    async def check(self) -> None:
        if not self.is_configured():
            raise SourceNotConfigured("Connect to Notion MCP first")
        async with httpx.AsyncClient(timeout=15) as client:
            session_id, protocol = await self._open_session(client)
            await self._rpc(client, "tools/list", {}, session_id=session_id, protocol=protocol, req_id=2)

    # -- OAuth (dynamic client registration + PKCE) -------------------------------------

    async def register_client(self, redirect_uri: str) -> str:
        """Register HQ as an OAuth client for this exact redirect URI, returning a client id.
        No secret: it's a public client that proves itself with PKCE instead."""
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(
                REGISTER_URL,
                json={
                    "client_name": "Personal HQ",
                    "redirect_uris": [redirect_uri],
                    "token_endpoint_auth_method": "none",
                    "grant_types": ["authorization_code", "refresh_token"],
                    "response_types": ["code"],
                },
            )
            response.raise_for_status()
            return response.json()["client_id"]

    def authorize_url(self, redirect_uri: str, state: str, challenge: str, client_id: str) -> str:
        params = httpx.QueryParams(
            response_type="code",
            client_id=client_id,
            redirect_uri=redirect_uri,
            code_challenge=challenge,
            code_challenge_method="S256",
            state=state,
            resource=MCP_URL,
        )
        return f"{AUTHORIZE_URL}?{params}"

    async def exchange_code(
        self, code: str, redirect_uri: str, verifier: str, client_id: str
    ) -> dict[str, str]:
        return await self._token_request(
            {
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "code_verifier": verifier,
            },
            client_id=client_id,
        )

    async def prepare(self) -> dict[str, str] | None:
        if not self.get("refresh_token") or not self.get("client_id") or not self._expired():
            return None
        return await self._token_request(
            {
                "grant_type": "refresh_token",
                "refresh_token": self.get("refresh_token"),
                "client_id": self.get("client_id"),
            },
            client_id=self.get("client_id"),
        )

    async def _token_request(self, payload: dict[str, str], client_id: str) -> dict[str, str]:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(TOKEN_URL, data=payload)
            response.raise_for_status()
            body = response.json()

        updates = {"token": body["access_token"], "client_id": client_id}
        if body.get("refresh_token"):
            updates["refresh_token"] = body["refresh_token"]
        if body.get("expires_in"):
            expiry = datetime.now(UTC) + timedelta(seconds=int(body["expires_in"]))
            updates["token_expiry"] = expiry.isoformat()
        return updates

    def _expired(self) -> bool:
        raw = self.get("token_expiry")
        if not raw:
            return False
        return datetime.fromisoformat(raw) - _EXPIRY_SKEW <= datetime.now(UTC)

    # -- MCP transport (Streamable HTTP) ------------------------------------------------

    def _queries(self) -> list[str]:
        return [part.strip() for part in re.split(r"[\n,]", self.get("query")) if part.strip()]

    async def fetch(self) -> list[RawItem]:
        # notion-search needs a non-empty query — there's no list-everything mode — so with no
        # search terms configured there's nothing to fetch.
        queries = self._queries()
        if not self.is_configured() or not queries:
            return []
        by_id: dict[str, RawItem] = {}
        async with httpx.AsyncClient(timeout=30) as client:
            session_id, protocol = await self._open_session(client)
            for offset, query in enumerate(queries):
                result = await self._rpc(
                    client,
                    "tools/call",
                    {"name": "notion-search", "arguments": {"query": query}},
                    session_id=session_id,
                    protocol=protocol,
                    req_id=2 + offset,
                )
                for item in _items_from_search(result):
                    by_id.setdefault(item.external_id, item)
        return list(by_id.values())

    async def _open_session(self, client: httpx.AsyncClient) -> tuple[str | None, str]:
        response = await self._post(
            client,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "Personal HQ", "version": "1"},
                },
            },
        )
        session_id = response.headers.get("mcp-session-id")
        result = _rpc_result(response)
        protocol = result.get("protocolVersion") or PROTOCOL_VERSION
        await self._post(
            client,
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            session_id=session_id,
            protocol=protocol,
        )
        return session_id, protocol

    async def _rpc(
        self,
        client: httpx.AsyncClient,
        method: str,
        params: dict,
        *,
        session_id: str | None,
        protocol: str,
        req_id: int,
    ) -> dict:
        response = await self._post(
            client,
            {"jsonrpc": "2.0", "id": req_id, "method": method, "params": params},
            session_id=session_id,
            protocol=protocol,
        )
        return _rpc_result(response)

    async def _post(
        self,
        client: httpx.AsyncClient,
        payload: dict,
        *,
        session_id: str | None = None,
        protocol: str | None = None,
    ) -> httpx.Response:
        headers = {
            "Authorization": f"Bearer {self.get('token')}",
            "Accept": "application/json, text/event-stream",
            "Content-Type": "application/json",
        }
        if session_id:
            headers["Mcp-Session-Id"] = session_id
        if protocol:
            headers["MCP-Protocol-Version"] = protocol
        response = await client.post(MCP_URL, headers=headers, json=payload)
        response.raise_for_status()
        return response


def _rpc_result(response: httpx.Response) -> dict:
    """Pull the JSON-RPC result out of a response that may be JSON or an SSE stream."""
    message = _decode(response)
    if message.get("error"):
        raise RuntimeError(message["error"].get("message", "MCP error"))
    return message.get("result") or {}


def _decode(response: httpx.Response) -> dict:
    if "text/event-stream" in response.headers.get("content-type", ""):
        # One JSON-RPC message per `data:` line; the last one carries the result.
        message: dict = {}
        for line in response.text.splitlines():
            if line.startswith("data:"):
                message = json.loads(line[5:].strip())
        return message
    body = response.text.strip()
    return json.loads(body) if body else {}


def _items_from_search(result: dict) -> list[RawItem]:
    """Map an MCP `search` result into items. The server returns tool output either as
    `structuredContent` or as JSON inside a text content block; accept both, and read each
    entry defensively — the exact field names are confirmed against a live workspace."""
    entries = _search_entries(result)
    items = []
    for entry in entries:
        page_id = str(entry.get("id") or entry.get("url") or "").strip()
        if not page_id:
            continue
        title = _entry_title(entry)
        highlight = entry.get("highlight")
        items.append(
            RawItem(
                source="notion_mcp",
                external_id=page_id,
                label=title,
                occurred_at=_entry_time(entry),
                url=entry.get("url"),
                context=highlight if isinstance(highlight, str) else None,
                title=title,
                reference_keys=all_reference_keys(title),
                extra={"notion_type": entry.get("type")},
            )
        )
    return items


def _search_entries(result: dict) -> list[dict]:
    structured = result.get("structuredContent")
    if isinstance(structured, dict) and isinstance(structured.get("results"), list):
        return [e for e in structured["results"] if isinstance(e, dict)]
    for block in result.get("content", []):
        if isinstance(block, dict) and block.get("type") == "text":
            try:
                parsed = json.loads(block.get("text", ""))
            except (json.JSONDecodeError, TypeError):
                continue
            if isinstance(parsed, dict) and isinstance(parsed.get("results"), list):
                return [e for e in parsed["results"] if isinstance(e, dict)]
            if isinstance(parsed, list):
                return [e for e in parsed if isinstance(e, dict)]
    return []


def _entry_title(entry: dict) -> str:
    for key in ("title", "name"):
        value = entry.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return "Untitled"


def _entry_time(entry: dict) -> datetime:
    for key in ("timestamp", "last_edited_time", "last_edited", "updated_at"):
        raw = entry.get(key)
        if isinstance(raw, str) and raw:
            try:
                return datetime.fromisoformat(raw.replace("Z", "+00:00"))
            except ValueError:
                pass
    return datetime.now(UTC)
