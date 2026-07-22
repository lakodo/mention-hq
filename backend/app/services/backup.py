"""Point-in-time copies of the SQLite database.

A migration or a hand-driven Admin click drops a dated copy next to the live file, so the
one irreplaceable thing here — your data — always has a recent fallback before anything
touches its schema.
"""

from __future__ import annotations

import sqlite3
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.config import Settings


def backups_dir(settings: Settings) -> Path:
    return settings.db_path.parent / "backups"


def backup_database(settings: Settings) -> Path:
    """Copy the live DB to `backups/<name>-<timestamp>.db` beside it, and return the copy.

    Uses SQLite's own backup API rather than a file copy so the snapshot is consistent even
    while the app is writing to the database.
    """
    source = settings.db_path
    if str(source) == ":memory:" or not source.exists():
        raise FileNotFoundError(f"No database file to back up at {source}")

    backups = source.parent / "backups"
    backups.mkdir(exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    destination = backups / f"{source.stem}-{stamp}.db"

    src = sqlite3.connect(str(source))
    try:
        dst = sqlite3.connect(str(destination))
        try:
            src.backup(dst)
        finally:
            dst.close()
    finally:
        src.close()

    return destination


def reveal_backups(settings: Settings) -> Path:
    """Open the backups folder in the OS file manager and return its path. HQ runs locally, so
    the machine serving the API is the one in front of you. The folder is created first, so the
    button works even before the first backup exists."""
    folder = backups_dir(settings)
    folder.mkdir(parents=True, exist_ok=True)
    _open_in_file_manager(folder)
    return folder


def _open_in_file_manager(path: Path) -> None:
    opener = {"darwin": "open", "win32": "explorer"}.get(sys.platform, "xdg-open")
    subprocess.Popen([opener, str(path)])
