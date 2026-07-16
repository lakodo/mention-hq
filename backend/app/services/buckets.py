"""Bucket assignment by keyword match.

No buckets ship with the app. Until the user creates some, `assign` returns UNCATEGORIZED
for everything, which is the honest answer — HQ has no idea what your topics are.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Bucket

UNCATEGORIZED = "Uncategorized"


@dataclass
class BucketRule:
    name: str
    keywords: list[str]


@dataclass
class BucketMatcher:
    rules: list[BucketRule]

    @property
    def names(self) -> list[str]:
        return [*(rule.name for rule in self.rules), UNCATEGORIZED]

    def assign(self, title: str, tags: list[str] | None = None) -> str:
        haystack = " ".join([title, *(tags or [])]).lower()
        for rule in self.rules:
            if any(keyword.lower() in haystack for keyword in rule.keywords if keyword.strip()):
                return rule.name
        return UNCATEGORIZED


async def load_matcher(db: AsyncSession) -> BucketMatcher:
    rows = (await db.execute(select(Bucket).order_by(Bucket.position, Bucket.name))).scalars().all()
    return BucketMatcher(rules=[BucketRule(name=row.name, keywords=list(row.keywords)) for row in rows])
