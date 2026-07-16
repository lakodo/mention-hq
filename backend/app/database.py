"""Async SQLAlchemy engine and session factory."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings

_settings = get_settings()

engine = create_async_engine(_settings.database_url, echo=False, future=True)

# expire_on_commit=False: with it on, every attribute read after a commit is lazy IO,
# which raises under async.
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


def enable_sqlite_foreign_keys(engine_) -> None:
    """SQLite ignores foreign keys unless asked, per connection.

    Without this every ON DELETE CASCADE in models.py is decorative, and deleting an item
    leaves links pointing at a row that no longer exists.
    """

    @event.listens_for(engine_.sync_engine, "connect")
    def _set_pragma(dbapi_connection, _record):  # pragma: no cover - driver callback
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


if engine.dialect.name == "sqlite":
    enable_sqlite_foreign_keys(engine)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
