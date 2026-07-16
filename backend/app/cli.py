"""Command-line sync, so you can populate the board without opening the UI."""

from __future__ import annotations

import argparse
import asyncio

from app.config import get_settings
from app.database import SessionLocal
from app.services.sync import sync_all


async def _sync(source: str | None) -> int:
    settings = get_settings()
    async with SessionLocal() as db:
        result = await sync_all(db, settings, only=source)

    if not result.sources_synced and not result.errors:
        print("No sources are configured, so there was nothing to sync.")
        print("Connect one in Admin (task dev, then http://localhost:5173).")
        return 0

    print(f"Synced {', '.join(result.sources_synced)} in {result.duration_seconds}s")
    print(f"  {result.tasks_added} tasks added, {result.tasks_updated} updated")
    for error in result.errors:
        print(f"  error: {error}")
    return 1 if result.errors else 0


def main() -> int:
    parser = argparse.ArgumentParser(prog="hq")
    subparsers = parser.add_subparsers(dest="command", required=True)
    sync_parser = subparsers.add_parser("sync", help="Fetch every source and rebuild the board")
    sync_parser.add_argument("--source", help="Sync only this source (e.g. github)")

    args = parser.parse_args()
    if args.command == "sync":
        return asyncio.run(_sync(args.source))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
