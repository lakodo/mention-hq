"""Serving the built frontend from the API.

A production run should be one process on one origin. The risk is the API and the SPA
disagreeing about who owns a path, so that is what these pin.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient

from app.main import _serve_frontend

BROWSER = {"Accept": "text/html,application/xhtml+xml", "Sec-Fetch-Mode": "navigate"}


@pytest.fixture
def dist(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>Mention HQ</title>")
    (tmp_path / "assets").mkdir()
    (tmp_path / "assets" / "app.js").write_text("console.log(1)")
    return tmp_path


@pytest.fixture
def app_with_frontend(dist, monkeypatch):
    from app import main
    from app.config import Settings, get_settings

    settings = Settings(frontend_dist=dist)
    monkeypatch.setattr(main, "get_settings", lambda: settings)
    get_settings.cache_clear()

    app = FastAPI()

    @app.get("/buckets")
    async def buckets():
        return [{"name": "Infra"}]

    _serve_frontend(app)
    return app


@pytest.fixture
async def web(app_with_frontend):
    async with AsyncClient(transport=ASGITransport(app=app_with_frontend), base_url="http://test") as client:
        yield client


async def test_the_index_is_served_at_the_root(web):
    response = await web.get("/", headers=BROWSER)
    assert response.status_code == 200
    assert "Mention HQ" in response.text


async def test_assets_are_served(web):
    assert (await web.get("/assets/app.js")).status_code == 200


async def test_a_client_side_route_gets_the_app(web):
    """A deep link like /task/abc is the SPA's route, not a missing file."""
    response = await web.get("/task/abc", headers=BROWSER)

    assert response.status_code == 200
    assert "Mention HQ" in response.text


async def test_the_api_still_owns_its_own_paths(web):
    response = await web.get("/buckets")

    assert response.status_code == 200
    assert response.json() == [{"name": "Infra"}]


async def test_an_api_path_wins_even_when_a_browser_asks_for_html(web):
    response = await web.get("/buckets", headers=BROWSER)
    assert response.json() == [{"name": "Infra"}]


async def test_a_missing_endpoint_404s_for_a_client_rather_than_returning_html(web):
    """An XHR expecting json must not be handed the index page instead."""
    response = await web.get("/nope", headers={"Accept": "application/json"})

    assert response.status_code == 404
    assert "<title>" not in response.text


async def test_a_missing_asset_404s(web):
    assert (await web.get("/assets/nope.js")).status_code == 404


async def test_nothing_is_served_without_a_build(tmp_path, monkeypatch):
    """Dev has no build, and that is normal rather than an error."""
    from app import main
    from app.config import Settings

    monkeypatch.setattr(main, "get_settings", lambda: Settings(frontend_dist=tmp_path / "absent"))
    app = FastAPI()

    _serve_frontend(app)

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        assert (await client.get("/", headers=BROWSER)).status_code == 404
