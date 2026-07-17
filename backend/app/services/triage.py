"""Triage rules: standing "skip this" filters so noise never reaches the catch-up inbox.

A rule tests an item's label and, on a match, skips it (marks it triaged, with the rule as
the reason). Rules only ever skip — they never file an item onto a task.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Item, TriageRule

CONDITIONS = ("starts_with", "contains")


def _rule_id() -> str:
    return f"rule:{uuid.uuid4().hex[:12]}"


def matches(rule: TriageRule, item: Item) -> bool:
    if rule.sources and item.source not in rule.sources:
        return False
    text = (item.label or "").lower()
    value = rule.value.lower()
    if rule.condition == "starts_with":
        return text.startswith(value)
    return value in text


async def enabled_rules(db: AsyncSession) -> list[TriageRule]:
    stmt = select(TriageRule).where(TriageRule.enabled.is_(True))
    return list((await db.execute(stmt)).scalars().all())


async def apply_rules(db: AsyncSession, items: list[Item], rules: list[TriageRule] | None = None) -> int:
    """Skip every untriaged item that matches an enabled rule. Caller commits."""
    rules = rules if rules is not None else await enabled_rules(db)
    if not rules:
        return 0
    now = datetime.now(UTC)
    skipped = 0
    for item in items:
        if item.triaged:
            continue
        for rule in rules:
            if matches(rule, item):
                item.triaged = True
                item.triage_reason = f"Rule: {rule.name}"
                item.triaged_at = now
                skipped += 1
                break
    return skipped


async def apply_to_inbox(db: AsyncSession) -> int:
    """Retroactively skip untriaged items that match — used when a rule is added."""
    items = list((await db.execute(select(Item).where(Item.triaged.is_(False)))).scalars().all())
    count = await apply_rules(db, items)
    await db.commit()
    return count


async def list_rules(db: AsyncSession) -> list[TriageRule]:
    stmt = select(TriageRule).order_by(TriageRule.created_at.desc())
    return list((await db.execute(stmt)).scalars().all())


async def create_rule(
    db: AsyncSession, name: str, sources: list[str], condition: str, value: str, enabled: bool = True
) -> TriageRule:
    if condition not in CONDITIONS:
        raise ValueError(f"Unknown condition: {condition}")
    if not value.strip():
        raise ValueError("A rule needs something to match on")
    rule = TriageRule(
        id=_rule_id(),
        name=name.strip() or value.strip(),
        sources=[s for s in sources if s and s != "*"],
        condition=condition,
        value=value.strip(),
        enabled=enabled,
    )
    db.add(rule)
    await db.commit()
    return await _reload(db, rule.id)


async def update_rule(db: AsyncSession, rule_id: str, *, enabled: bool | None = None) -> TriageRule:
    rule = await db.get(TriageRule, rule_id)
    if rule is None:
        raise LookupError(f"Rule not found: {rule_id}")
    if enabled is not None:
        rule.enabled = enabled
    await db.commit()
    return await _reload(db, rule_id)


async def delete_rule(db: AsyncSession, rule_id: str) -> None:
    rule = await db.get(TriageRule, rule_id)
    if rule is None:
        raise LookupError(f"Rule not found: {rule_id}")
    await db.delete(rule)
    await db.commit()


async def _reload(db: AsyncSession, rule_id: str) -> TriageRule:
    stmt = select(TriageRule).where(TriageRule.id == rule_id).execution_options(populate_existing=True)
    return (await db.execute(stmt)).scalars().one()
