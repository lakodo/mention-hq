"""Building source adapters from stored configuration.

Sources are constructed per request, not cached: a token changed in the Admin panel must
take effect on the next sync without a restart.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.security import get_secret_store
from app.services.app_config import get_namespace
from app.sources.dust import DustSource
from app.sources.git import GitSource
from app.sources.github import GitHubSource
from app.sources.linear import LinearSource
from app.sources.markdown import MarkdownSource
from app.sources.slack import SlackSource
from app.sources.todos import TodoSource

SOURCE_CLASSES = [
    GitHubSource,
    LinearSource,
    SlackSource,
    GitSource,
    TodoSource,
    MarkdownSource,
    DustSource,
]


async def resolve_config(db: AsyncSession, source_class) -> dict[str, str]:
    stored = await get_namespace(db, source_class.id)
    secrets = get_secret_store()

    config: dict[str, str] = {}
    for spec in source_class.fields:
        value = secrets.get(source_class.id, spec.key) if spec.kind == "secret" else stored.get(spec.key)
        if value:
            config[spec.key] = value
    return config


async def build_configured_sources(db: AsyncSession, settings: Settings) -> list:
    del settings  # sources take their config from the DB/keychain, not the process env
    return [cls(await resolve_config(db, cls)) for cls in SOURCE_CLASSES]


def source_class_by_id(source_id: str):
    return next((cls for cls in SOURCE_CLASSES if cls.id == source_id), None)
