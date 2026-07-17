"""Runtime configuration: everything the user can change from the Admin panel.

Two stores, split by sensitivity:
  - non-secret values (username, org, globs, the app's name) live in the `app_config` table;
  - secrets live in the OS keychain via `app.security.secrets` and never enter the DB.

Resolution order for a value is DB -> environment -> default, so a fork with an existing
`.env` keeps working while anything set in the UI wins.
"""

from __future__ import annotations

import os

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AppConfig

APP_NAMESPACE = "app"
DEFAULT_APP_NAME = "Personal HQ"


async def get_value(db: AsyncSession, namespace: str, key: str) -> str | None:
    row = await db.get(AppConfig, {"namespace": namespace, "key": key})
    if row is not None and row.value:
        return row.value
    return os.environ.get(f"{namespace}_{key}".upper()) or None


async def set_value(db: AsyncSession, namespace: str, key: str, value: str | None) -> None:
    row = await db.get(AppConfig, {"namespace": namespace, "key": key})
    if value is None or value == "":
        if row is not None:
            await db.delete(row)
        return
    if row is None:
        db.add(AppConfig(namespace=namespace, key=key, value=value))
    else:
        row.value = value


async def get_namespace(db: AsyncSession, namespace: str) -> dict[str, str]:
    rows = (await db.execute(select(AppConfig).where(AppConfig.namespace == namespace))).scalars().all()
    return {row.key: row.value for row in rows if row.value}


async def get_app_name(db: AsyncSession) -> str:
    return await get_value(db, APP_NAMESPACE, "name") or DEFAULT_APP_NAME


async def set_app_name(db: AsyncSession, name: str) -> None:
    await set_value(db, APP_NAMESPACE, "name", name.strip() or None)


async def get_auto_sync(db: AsyncSession) -> bool:
    return (await get_value(db, APP_NAMESPACE, "auto_sync")) == "1"


async def set_auto_sync(db: AsyncSession, enabled: bool) -> None:
    # "0" is stored, not cleared, so an explicit off survives the DB->env->default fallback.
    await set_value(db, APP_NAMESPACE, "auto_sync", "1" if enabled else "0")
