"""Building source adapters from the connections the user has added.

Adapters are constructed per request, not cached: a token changed in Admin must take
effect on the next sync without a restart.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SourceInstance
from app.security import get_secret_store
from app.services.app_config import get_namespace, set_value
from app.sources.base import Source
from app.sources.dust import DustSource
from app.sources.git import GitSource
from app.sources.github import GitHubSource
from app.sources.linear import LinearSource
from app.sources.markdown import MarkdownSource
from app.sources.notion import NotionSource
from app.sources.notion_mcp import NotionMcpSource
from app.sources.slack import SlackSource
from app.sources.todos import TodoSource

SOURCE_CLASSES: list[type[Source]] = [
    GitHubSource,
    LinearSource,
    SlackSource,
    NotionSource,
    NotionMcpSource,
    GitSource,
    TodoSource,
    MarkdownSource,
    DustSource,
]

BY_KIND = {cls.id: cls for cls in SOURCE_CLASSES}

_SLUG_UNSAFE = re.compile(r"[^a-z0-9]+")


@dataclass
class Connected:
    """A connection paired with the adapter built from its settings."""

    instance: SourceInstance
    source: Source


def source_class_by_id(kind: str) -> type[Source] | None:
    return BY_KIND.get(kind)


def new_instance_id(kind: str, name: str) -> str:
    """A readable id that survives a rename, since config is keyed by it."""
    slug = _SLUG_UNSAFE.sub("-", name.strip().lower()).strip("-")
    return f"{kind}-{slug}" if slug else f"{kind}-{uuid.uuid4().hex[:6]}"


async def resolve_config(db: AsyncSession, instance: SourceInstance) -> dict[str, str]:
    source_class = BY_KIND[instance.kind]
    stored = await get_namespace(db, instance.id)
    secrets = get_secret_store()

    config: dict[str, str] = {}
    for spec in source_class.fields:
        value = secrets.get(instance.id, spec.key) if spec.kind == "secret" else stored.get(spec.key)
        if value:
            config[spec.key] = value
    return config


async def persist_config(db: AsyncSession, instance: SourceInstance, updates: dict[str, str]) -> None:
    """Write config back for one source: secret keys to the keychain, the rest to app_config.
    Also updates the live source's in-memory config so the change takes effect immediately."""
    source_class = BY_KIND[instance.kind]
    secret_keys = {f.key for f in source_class.fields if f.kind == "secret"}
    secrets = get_secret_store()
    for key, value in updates.items():
        if key in secret_keys:
            secrets.set(instance.id, key, value)
        else:
            await set_value(db, instance.id, key, value)
    await db.commit()


async def instances(db: AsyncSession) -> list[SourceInstance]:
    stmt = select(SourceInstance).order_by(SourceInstance.position, SourceInstance.created_at)
    return list((await db.execute(stmt)).scalars().all())


async def build_connected(db: AsyncSession) -> list[Connected]:
    return [
        Connected(instance=instance, source=BY_KIND[instance.kind](await resolve_config(db, instance)))
        for instance in await instances(db)
        if instance.kind in BY_KIND
    ]
