"""Settings, loaded from .env. Every integration is optional — a source with no
credentials configured reports itself as unconfigured rather than failing the sync.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = f"sqlite+aiosqlite:///{BACKEND_DIR / 'hq.db'}"

    # Only used when no OS keychain is available; see app/security/secrets.py.
    secrets_dir: Path = Path.home() / ".config" / "personal-hq"

    # Built frontend. Served by the API when present, so a production run is one process
    # on one origin; absent in dev, where Vite serves it with hot reload.
    frontend_dist: Path = BACKEND_DIR.parent / "frontend" / "dist"

    sync_on_startup: bool = False
    cors_origins: str = "http://localhost:5173"

    # Binding beyond loopback would expose an unauthenticated API that can read your
    # keychain-backed tokens. Changing this is a deliberate, documented risk.
    host: str = "127.0.0.1"
    port: int = 8000

    @property
    def cors_origin_list(self) -> list[str]:
        return _split(self.cors_origins)


def _split(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
