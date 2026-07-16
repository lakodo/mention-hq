import asyncio

from app.config import Settings
from app.database import SessionLocal
from app.services.app_config import set_value
from app.services.sync import sync_all

SP = "/private/tmp/claude-501/-Users-jorgu-workspace-hq/c6a47805-1a09-4d11-95d5-51f0cc75e92b/scratchpad"


async def main():
    s = Settings()
    async with SessionLocal() as db:
        await set_value(db, "todo", "globs", f"{SP}/demo/todo.md")
        await set_value(db, "git", "repos", f"{SP}/demo/repo")
        await db.commit()
        r = await sync_all(db, s)
        print(f"REPORTED added={r.tasks_added} updated={r.tasks_updated}")
        from sqlalchemy import select

        from app.models import Task

        actual = len((await db.execute(select(Task))).scalars().all())
        print(f"ACTUAL tasks in db = {actual}")


asyncio.run(main())
