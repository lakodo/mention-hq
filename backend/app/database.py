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
    """Per-connection pragmas.

    foreign_keys: off by default, so without it every ON DELETE CASCADE in models.py is
    decorative. WAL + busy_timeout let the background matcher and a sync touch the DB at
    once: WAL keeps a reader from blocking the writer, and busy_timeout makes a brief
    writer overlap wait rather than raise "database is locked".
    """

    @event.listens_for(engine_.sync_engine, "connect")
    def _set_pragma(dbapi_connection, _record):  # pragma: no cover - driver callback
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.close()


if engine.dialect.name == "sqlite":
    enable_sqlite_foreign_keys(engine)


async def get_db() -> AsyncIterator[AsyncSession]:
    async with SessionLocal() as session:
        yield session
