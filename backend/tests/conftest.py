from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import enable_sqlite_foreign_keys, get_db
from app.main import app
from app.models import Base
from app.sources.base import RawItem


@pytest_asyncio.fixture
async def db() -> AsyncIterator[AsyncSession]:
    # A per-test in-memory database. StaticPool keeps every connection on the same
    # instance — without it each connection gets its own blank database.
    from sqlalchemy.pool import StaticPool

    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    # Mirror production: without the pragma, SQLite silently ignores every FK cascade.
    enable_sqlite_foreign_keys(engine)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # expire_on_commit=False mirrors app.database.SessionLocal — with it left on, objects
    # expire at commit and every attribute read becomes lazy IO, which fails under async.
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture
async def client(db: AsyncSession) -> AsyncIterator[AsyncClient]:
    async def override_get_db() -> AsyncIterator[AsyncSession]:
        yield db

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


@pytest.fixture
def now() -> datetime:
    return datetime(2026, 7, 16, 12, 0, tzinfo=UTC)


@pytest.fixture
def item(now):
    def _make(source: str, external_id: str, **kwargs) -> RawItem:
        kwargs.setdefault("label", f"{source} {external_id}")
        kwargs.setdefault("occurred_at", now - timedelta(minutes=10))
        return RawItem(source=source, external_id=external_id, **kwargs)

    return _make


@pytest.fixture(autouse=True)
def isolated_secrets(tmp_path, monkeypatch):
    """Never touch the developer's real keychain from a test."""
    from app.security import secrets as secrets_module

    monkeypatch.setattr(secrets_module.KeyringBackend, "available", staticmethod(lambda: False))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)

    import app.security as security_module

    security_module.get_secret_store.cache_clear()
    store = secrets_module.SecretStore(fallback_dir=tmp_path / "secrets")
    monkeypatch.setattr(security_module, "get_secret_store", lambda: store)

    for module in ("app.routers.admin", "app.services.sources_factory", "app.services.ai"):
        monkeypatch.setattr(f"{module}.get_secret_store", lambda: store, raising=False)
    yield store
