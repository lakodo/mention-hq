from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from app.security.secrets import SecretStore

__all__ = ["SecretStore", "get_secret_store"]


@lru_cache
def get_secret_store() -> SecretStore:
    from app.config import get_settings

    return SecretStore(fallback_dir=Path(get_settings().secrets_dir))
