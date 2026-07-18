"""Admin endpoints that act on the machine rather than the domain model."""

from __future__ import annotations

import sqlite3
from urllib.parse import parse_qs, urlparse

import httpx
import pytest
import respx

from app.config import Settings
from app.models import SourceInstance
from app.services.app_config import set_value


@pytest.fixture
def point_backup_at(monkeypatch, tmp_path):
    """Aim the backup endpoint at a throwaway DB, never the developer's real one."""

    def _point(db_path) -> Settings:
        settings = Settings(db_path=db_path)
        monkeypatch.setattr("app.routers.admin.get_settings", lambda: settings)
        return settings

    return _point


class TestBackup:
    async def test_writes_a_dated_copy_beside_the_live_file(self, client, tmp_path, point_backup_at):
        live = tmp_path / "hq.db"
        sqlite3.connect(str(live)).executescript("create table t(x); insert into t values (1);")
        point_backup_at(live)

        response = await client.post("/api/admin/backup")

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["filename"].startswith("hq-")
        assert body["size_bytes"] > 0
        copy = tmp_path / "backups" / body["filename"]
        assert copy.exists(), "the reported copy is on disk"
        # It is a real, readable snapshot — not an empty placeholder.
        assert sqlite3.connect(str(copy)).execute("select x from t").fetchone() == (1,)

    async def test_a_missing_database_is_a_clean_400_not_a_500(self, client, tmp_path, point_backup_at):
        point_backup_at(tmp_path / "nothing-here.db")

        response = await client.post("/api/admin/backup")

        assert response.status_code == 400


async def _add_notion_oauth(db, secrets) -> None:
    db.add(SourceInstance(id="notion-x", kind="notion", name="Notion"))
    await set_value(db, "notion-x", "client_id", "cid")
    await db.commit()
    secrets.set("notion-x", "client_secret", "csec")


class TestNotionOAuth:
    async def test_info_detects_the_redirect_uri_from_the_browser_origin(self, client, db, isolated_secrets):
        await _add_notion_oauth(db, isolated_secrets)

        response = await client.get("/api/admin/sources/notion-x/notion", headers={"Origin": "http://jojohq"})

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["redirect_uri"] == "http://jojohq/api/admin/oauth/notion/callback"
        assert body["oauth_ready"] is True
        assert body["connected"] is False

    async def test_authorize_builds_a_consent_url_carrying_the_client_and_state(
        self, client, db, isolated_secrets
    ):
        await _add_notion_oauth(db, isolated_secrets)

        response = await client.post(
            "/api/admin/sources/notion-x/notion/authorize", headers={"Origin": "http://jojohq"}
        )

        assert response.status_code == 200, response.text
        url = response.json()["authorize_url"]
        assert url.startswith("https://api.notion.com/v1/oauth/authorize")
        query = parse_qs(urlparse(url).query)
        assert query["client_id"] == ["cid"]
        assert query["redirect_uri"] == ["http://jojohq/api/admin/oauth/notion/callback"]
        assert query["state"], "a state nonce ties the callback back to this source"

    async def test_callback_exchanges_the_code_and_stores_the_token(
        self, client, db, isolated_secrets, monkeypatch
    ):
        await _add_notion_oauth(db, isolated_secrets)
        authorize = await client.post(
            "/api/admin/sources/notion-x/notion/authorize", headers={"Origin": "http://jojohq"}
        )
        state = parse_qs(urlparse(authorize.json()["authorize_url"]).query)["state"][0]

        async def fake_exchange(self, code, redirect_uri):
            assert code == "abc"
            assert redirect_uri == "http://jojohq/api/admin/oauth/notion/callback"
            return {"token": "ntn_new", "user_id": "me", "refresh_token": "r2"}

        monkeypatch.setattr("app.sources.notion.NotionSource.exchange_code", fake_exchange)

        callback = await client.get(f"/api/admin/oauth/notion/callback?code=abc&state={state}")

        assert callback.status_code == 200
        assert isolated_secrets.get("notion-x", "token") == "ntn_new"
        info = await client.get("/api/admin/sources/notion-x/notion", headers={"Origin": "http://jojohq"})
        assert info.json()["connected"] is True

    async def test_callback_rejects_a_state_it_never_issued(self, client, db, isolated_secrets):
        await _add_notion_oauth(db, isolated_secrets)

        callback = await client.get("/api/admin/oauth/notion/callback?code=abc&state=forged")

        assert callback.status_code == 200, "an error still renders a close-me page, not a 500"
        assert isolated_secrets.get("notion-x", "token") is None, "no token from an unknown state"

    async def test_a_used_state_cannot_be_replayed(self, client, db, isolated_secrets, monkeypatch):
        await _add_notion_oauth(db, isolated_secrets)
        authorize = await client.post(
            "/api/admin/sources/notion-x/notion/authorize", headers={"Origin": "http://jojohq"}
        )
        state = parse_qs(urlparse(authorize.json()["authorize_url"]).query)["state"][0]

        calls = {"n": 0}

        async def fake_exchange(self, code, redirect_uri):
            calls["n"] += 1
            return {"token": "ntn_new", "user_id": "me"}

        monkeypatch.setattr("app.sources.notion.NotionSource.exchange_code", fake_exchange)

        await client.get(f"/api/admin/oauth/notion/callback?code=abc&state={state}")
        await client.get(f"/api/admin/oauth/notion/callback?code=abc&state={state}")

        assert calls["n"] == 1, "the nonce is burned on first use"


class TestNotionMcpOAuth:
    async def test_info_is_always_ready_and_detects_the_redirect_uri(self, client, db):
        db.add(SourceInstance(id="notion_mcp-x", kind="notion_mcp", name="Notion MCP"))
        await db.commit()

        response = await client.get(
            "/api/admin/sources/notion_mcp-x/notion-mcp", headers={"Origin": "http://jojohq"}
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["redirect_uri"] == "http://jojohq/api/admin/oauth/notion-mcp/callback"
        # Nothing to paste — Connect registers HQ itself — so it is ready with no config.
        assert body["oauth_ready"] is True
        assert body["connected"] is False

    @respx.mock
    async def test_authorize_registers_a_client_and_builds_a_pkce_url(self, client, db):
        db.add(SourceInstance(id="notion_mcp-x", kind="notion_mcp", name="Notion MCP"))
        await db.commit()
        respx.post("https://mcp.notion.com/register").mock(
            return_value=httpx.Response(200, json={"client_id": "cid-mcp"})
        )

        response = await client.post(
            "/api/admin/sources/notion_mcp-x/notion-mcp/authorize", headers={"Origin": "http://jojohq"}
        )

        assert response.status_code == 200, response.text
        url = response.json()["authorize_url"]
        assert url.startswith("https://mcp.notion.com/authorize")
        query = parse_qs(urlparse(url).query)
        assert query["client_id"] == ["cid-mcp"]
        assert query["code_challenge_method"] == ["S256"]
        assert query["code_challenge"], "a PKCE challenge protects the code in transit"
        assert query["state"]

    @respx.mock
    async def test_callback_exchanges_the_code_and_stores_the_token(self, client, db, isolated_secrets):
        db.add(SourceInstance(id="notion_mcp-x", kind="notion_mcp", name="Notion MCP"))
        await db.commit()
        respx.post("https://mcp.notion.com/register").mock(
            return_value=httpx.Response(200, json={"client_id": "cid-mcp"})
        )
        respx.post("https://mcp.notion.com/token").mock(
            return_value=httpx.Response(
                200, json={"access_token": "mcp-tok", "refresh_token": "r2", "expires_in": 3600}
            )
        )
        authorize = await client.post(
            "/api/admin/sources/notion_mcp-x/notion-mcp/authorize", headers={"Origin": "http://jojohq"}
        )
        state = parse_qs(urlparse(authorize.json()["authorize_url"]).query)["state"][0]

        callback = await client.get(f"/api/admin/oauth/notion-mcp/callback?code=abc&state={state}")

        assert callback.status_code == 200
        assert isolated_secrets.get("notion_mcp-x", "token") == "mcp-tok"
        assert isolated_secrets.get("notion_mcp-x", "refresh_token") == "r2"
