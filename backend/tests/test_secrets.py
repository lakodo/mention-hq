"""Secret storage.

Security-critical, so the tests are about the guarantees rather than the happy path: the
fallback file must never be readable by anyone else, a corrupted store must not take the
app down, and nothing here may ever hand back a value the caller shouldn't see.
"""

from __future__ import annotations

import os
import stat

import pytest

from app.security.secrets import EncryptedFileBackend, KeyringBackend, SecretStore


@pytest.fixture
def store(tmp_path) -> SecretStore:
    """Forced onto the file backend — a test must never touch a real keychain."""
    store = SecretStore.__new__(SecretStore)
    store._backend = EncryptedFileBackend(tmp_path / "secrets")
    return store


class TestEncryptedFileBackend:
    def test_round_trip(self, store):
        store.set("github", "token", "ghp_x")
        assert store.get("github", "token") == "ghp_x"

    def test_missing_key_is_none(self, store):
        assert store.get("github", "token") is None

    def test_delete(self, store):
        store.set("github", "token", "ghp_x")
        store.delete("github", "token")
        assert store.get("github", "token") is None

    def test_deleting_something_that_was_never_set_is_not_an_error(self, store):
        store.delete("github", "token")

    def test_keys_are_namespaced_by_source(self, store):
        store.set("github", "token", "gh")
        store.set("linear", "token", "lin")

        assert store.get("github", "token") == "gh"
        assert store.get("linear", "token") == "lin"

    def test_the_secret_is_not_on_disk_in_the_clear(self, tmp_path):
        backend = EncryptedFileBackend(tmp_path / "secrets")
        backend.set("github.token", "ghp_supersecret")

        raw = (tmp_path / "secrets" / "secrets.enc").read_bytes()

        assert b"ghp_supersecret" not in raw
        assert b"github" not in raw

    @pytest.mark.parametrize("filename", ["secret.key", "secrets.enc"])
    def test_files_are_not_readable_by_anyone_else(self, tmp_path, filename):
        backend = EncryptedFileBackend(tmp_path / "secrets")
        backend.set("github.token", "ghp_x")

        mode = stat.S_IMODE(os.stat(tmp_path / "secrets" / filename).st_mode)

        assert mode == 0o600, f"{filename} must be owner read/write only, got {oct(mode)}"

    def test_a_corrupted_store_does_not_take_the_app_down(self, tmp_path):
        backend = EncryptedFileBackend(tmp_path / "secrets")
        backend.set("github.token", "ghp_x")
        (tmp_path / "secrets" / "secrets.enc").write_bytes(b"not a fernet token")

        assert backend.get("github.token") is None

    def test_a_second_backend_reads_what_the_first_wrote(self, tmp_path):
        EncryptedFileBackend(tmp_path / "secrets").set("github.token", "ghp_x")

        assert EncryptedFileBackend(tmp_path / "secrets").get("github.token") == "ghp_x"


class TestEnvironmentFallback:
    def test_the_environment_is_a_fallback_not_a_source_of_truth(self, store, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "from-env")
        assert store.get("github", "token") == "from-env"

        store.set("github", "token", "from-admin")
        assert store.get("github", "token") == "from-admin"

    def test_stored_and_environment_are_distinguishable(self, store, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "from-env")

        assert store.stored("github", "token") is None
        assert store.from_environment("github", "token") == "from-env"

    def test_an_empty_environment_variable_is_not_a_credential(self, store, monkeypatch):
        monkeypatch.setenv("GITHUB_TOKEN", "")
        assert store.get("github", "token") is None


class TestHint:
    def test_a_hint_masks_all_but_the_tail(self, store):
        store.set("github", "token", "ghp_abcdefgh1234")

        hint = store.hint("github", "token")

        assert hint == "••••••••1234"
        assert "abcdefgh" not in hint

    def test_a_short_secret_gives_away_nothing(self, store):
        store.set("github", "token", "short")
        assert store.hint("github", "token") == "••••••••"

    def test_no_secret_means_no_hint(self, store):
        assert store.hint("github", "token") is None


class TestBackendSelection:
    def test_the_keychain_is_preferred_when_available(self, tmp_path, monkeypatch):
        monkeypatch.setattr(KeyringBackend, "available", staticmethod(lambda: True))
        monkeypatch.setattr(KeyringBackend, "__init__", lambda self: None)

        assert SecretStore(fallback_dir=tmp_path).backend_name == "keyring"

    def test_it_falls_back_to_a_file_without_a_keychain(self, tmp_path, monkeypatch):
        monkeypatch.setattr(KeyringBackend, "available", staticmethod(lambda: False))

        store = SecretStore(fallback_dir=tmp_path)

        assert store.backend_name == "encrypted-file"
        assert store.is_keychain is False
