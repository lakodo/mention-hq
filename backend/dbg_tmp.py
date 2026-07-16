import asyncio

from app.config import Settings
from app.database import SessionLocal
from app.services.grouping import group_mentions
from app.services.sources_factory import build_configured_sources
from app.services.sync import _fetch, _merge, _stored_mentions_to_keep


async def main():
    s = Settings()
    async with SessionLocal() as db:
        sources = await build_configured_sources(db, s)
        outcomes = [await _fetch(src) for src in sources]
        fetched = [m for o in outcomes for m in o.mentions]
        refreshed = {o.source_id for o in outcomes if o.authoritative}
        kept = await _stored_mentions_to_keep(db, refreshed)
        merged = _merge(kept, fetched)
        groups = group_mentions(merged)
        print(f"fetched={len(fetched)} kept={len(kept)} merged={len(merged)} groups={len(groups)}")
        for g in groups:
            print("   group:", g.id, "|", g.title[:40])


asyncio.run(main())
