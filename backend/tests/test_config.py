"""Settings.

DB_PATH is the one people reach for by hand, so the URL it derives is worth pinning.
"""

from __future__ import annotations

from pathlib import Path

from app.config import BACKEND_DIR, Settings


def test_the_default_is_the_app_database():
    assert Settings().db_path == BACKEND_DIR / "hq.db"


def test_db_path_points_the_app_somewhere_else(monkeypatch, tmp_path):
    monkeypatch.setenv("DB_PATH", str(tmp_path / "throwaway.db"))
    assert Settings().db_path == tmp_path / "throwaway.db"


def test_an_absolute_path_keeps_its_leading_slash():
    """SQLite wants four slashes for an absolute path; three silently means relative."""
    url = Settings(db_path=Path("/tmp/hq.db")).database_url

    assert url == "sqlite+aiosqlite:////tmp/hq.db"


def test_a_relative_path_stays_relative():
    assert Settings(db_path=Path("hq.db")).database_url == "sqlite+aiosqlite:///hq.db"


def test_in_memory_works_for_tests():
    assert Settings(db_path=":memory:").database_url == "sqlite+aiosqlite:///:memory:"
