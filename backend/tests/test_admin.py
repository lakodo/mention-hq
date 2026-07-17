"""Admin endpoints that act on the machine rather than the domain model."""

from __future__ import annotations

import sqlite3

import pytest

from app.config import Settings


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
