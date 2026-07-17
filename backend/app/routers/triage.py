from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import TriageRuleCreate, TriageRuleOut, TriageRulePatch
from app.services import triage

router = APIRouter(prefix="/triage-rules", tags=["triage"])


@router.get("", response_model=list[TriageRuleOut])
async def list_rules(db: AsyncSession = Depends(get_db)):
    return await triage.list_rules(db)


@router.post("", response_model=TriageRuleOut, status_code=201)
async def create_rule(payload: TriageRuleCreate, db: AsyncSession = Depends(get_db)):
    try:
        rule = await triage.create_rule(db, payload.name, payload.sources, payload.condition, payload.value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    # Apply it right away, so the inbox items it would have skipped disappear now.
    await triage.apply_to_inbox(db)
    return rule


@router.patch("/{rule_id}", response_model=TriageRuleOut)
async def update_rule(rule_id: str, patch: TriageRulePatch, db: AsyncSession = Depends(get_db)):
    try:
        rule = await triage.update_rule(db, rule_id, enabled=patch.enabled)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if rule.enabled:
        await triage.apply_to_inbox(db)
    return rule


@router.delete("/{rule_id}", status_code=204)
async def delete_rule(rule_id: str, db: AsyncSession = Depends(get_db)):
    try:
        await triage.delete_rule(db, rule_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
