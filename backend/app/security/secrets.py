"""Secret storage.

Secrets (API tokens) never go in the database, in `.env`, or anywhere near git. They go to
the OS keychain — Keychain on macOS, Credential Locker on Windows, Secret Service on Linux —
which is the only place on a personal machine that is encrypted at rest and unlocked by the
user's own login.

Headless boxes often have no Secret Service. Rather than refuse to run, we fall back to an
age-old but sound arrangement: a Fernet-encrypted file, with the key in a sibling file at
0600. That is meaningfully weaker than a keychain — it protects against stray backups and
`cat`, not against an attacker who already reads your home directory as you — so we surface
which backend is live at /admin/security, and never silently pretend it's as good.
"""

from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Protocol

import structlog

log = structlog.get_logger(__name__)

SERVICE_NAME = "personal-hq"


class SecretBackend(Protocol):
    name: str

    def get(self, key: str) -> str | None: ...
    def set(self, key: str, value: str) -> None: ...
    def delete(self, key: str) -> None: ...


class KeyringBackend:
    name = "keyring"

    def __init__(self) -> None:
        import keyring

        self._keyring = keyring

    @staticmethod
    def available() -> bool:
        try:
            import keyring
            from keyring.backends.fail import Keyring as FailKeyring
        except ImportError:
            return False
        return not isinstance(keyring.get_keyring(), FailKeyring)

    def get(self, key: str) -> str | None:
        return self._keyring.get_password(SERVICE_NAME, key)

    def set(self, key: str, value: str) -> None:
        self._keyring.set_password(SERVICE_NAME, key, value)

    def delete(self, key: str) -> None:
        import contextlib

        import keyring.errors

        # Deleting a key that was never set is the caller getting what they asked for.
        with contextlib.suppress(keyring.errors.PasswordDeleteError):
            self._keyring.delete_password(SERVICE_NAME, key)


class EncryptedFileBackend:
    name = "encrypted-file"

    def __init__(self, directory: Path) -> None:
        self._dir = directory
        self._dir.mkdir(parents=True, exist_ok=True)
        self._key_path = self._dir / "secret.key"
        self._store_path = self._dir / "secrets.enc"

    def _fernet(self):
        from cryptography.fernet import Fernet

        if not self._key_path.exists():
            self._write_private(self._key_path, Fernet.generate_key())
        return Fernet(self._key_path.read_bytes())

    @staticmethod
    def _write_private(path: Path, data: bytes) -> None:
        # Create with 0600 from the start; writing then chmod'ing leaves a window where the
        # file is world-readable.
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)

    def _load(self) -> dict[str, str]:
        if not self._store_path.exists():
            return {}
        from cryptography.fernet import InvalidToken

        try:
            return json.loads(self._fernet().decrypt(self._store_path.read_bytes()))
        except (InvalidToken, json.JSONDecodeError):
            log.warning("secret_store_unreadable", path=str(self._store_path))
            return {}

    def _save(self, data: dict[str, str]) -> None:
        self._write_private(self._store_path, self._fernet().encrypt(json.dumps(data).encode()))

    def get(self, key: str) -> str | None:
        return self._load().get(key)

    def set(self, key: str, value: str) -> None:
        data = self._load()
        data[key] = value
        self._save(data)

    def delete(self, key: str) -> None:
        data = self._load()
        if data.pop(key, None) is not None:
            self._save(data)


class SecretStore:
    def __init__(self, fallback_dir: Path) -> None:
        self._backend: SecretBackend = (
            KeyringBackend() if KeyringBackend.available() else EncryptedFileBackend(fallback_dir)
        )

    @property
    def backend_name(self) -> str:
        return self._backend.name

    @property
    def is_keychain(self) -> bool:
        return self._backend.name == "keyring"

    def get(self, source_id: str, key: str) -> str | None:
        return self.stored(source_id, key) or self.from_environment(source_id, key)

    def stored(self, source_id: str, key: str) -> str | None:
        """Only what this store holds. Anything set through the UI takes precedence."""
        return self._backend.get(_qualify(source_id, key)) or None

    def from_environment(self, source_id: str, key: str) -> str | None:
        """Env vars are a bootstrap path for an existing .env, and for CI.

        Kept separate from `stored` so callers can report *where* a credential came from:
        telling someone their key is saved in Admin when it actually came from the
        environment sends them looking in the wrong place.
        """
        return os.environ.get(f"{source_id}_{key}".upper()) or None

    def set(self, source_id: str, key: str, value: str) -> None:
        self._backend.set(_qualify(source_id, key), value)

    def delete(self, source_id: str, key: str) -> None:
        self._backend.delete(_qualify(source_id, key))

    def hint(self, source_id: str, key: str) -> str | None:
        """A masked echo, so the UI can show a field is set without ever shipping the value."""
        value = self.get(source_id, key)
        if not value:
            return None
        tail = value[-4:] if len(value) > 8 else ""
        return f"{'•' * 8}{tail}"


def _qualify(source_id: str, key: str) -> str:
    return f"{source_id}.{key}"
