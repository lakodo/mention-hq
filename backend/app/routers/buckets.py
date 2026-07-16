from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Bucket, Task
from app.schemas import BucketCreate, BucketOut, BucketPatch, BucketSuggestionOut
from app.services import ai
from app.services.buckets import UNCATEGORIZED, load_matcher

router = APIRouter(prefix="/buckets", tags=["buckets"])


@router.post("/suggest/{task_id}", response_model=BucketSuggestionOut)
async def suggest(task_id: str, db: AsyncSession = Depends(get_db)) -> BucketSuggestionOut:
    """Ask Claude where a task belongs. Suggests only — the user decides."""
    task = await db.get(Task, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail=f"Task not found: {task_id}")
    try:
        suggestion = await ai.suggest_bucket(db, task)
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return BucketSuggestionOut(**suggestion.model_dump())


@router.get("", response_model=list[BucketOut])
async def list_buckets(db: AsyncSession = Depends(get_db)) -> list[BucketOut]:
    rows = await db.execute(select(Task.bucket, func.count(Task.id)).group_by(Task.bucket))
    counts = dict(rows.all())

    buckets = (await db.execute(select(Bucket).order_by(Bucket.position, Bucket.name))).scalars().all()

    out = [
        BucketOut(name=b.name, keywords=list(b.keywords), position=b.position, count=counts.get(b.name, 0))
        for b in buckets
    ]
    # Uncategorized is implicit — it has no row, but the board still needs the column
    # whenever anything landed there.
    if counts.get(UNCATEGORIZED):
        out.append(BucketOut(name=UNCATEGORIZED, keywords=[], position=len(out), count=counts[UNCATEGORIZED]))
    return out


@router.post("", response_model=BucketOut, status_code=201)
async def create_bucket(payload: BucketCreate, db: AsyncSession = Depends(get_db)) -> BucketOut:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Name is required")
    if name == UNCATEGORIZED:
        raise HTTPException(status_code=400, detail=f"{UNCATEGORIZED} is reserved")
    if await db.get(Bucket, name) is not None:
        raise HTTPException(status_code=409, detail=f"Bucket already exists: {name}")

    position = payload.position
    if position is None:
        highest = (await db.execute(select(func.max(Bucket.position)))).scalar()
        position = (highest or 0) + 1

    bucket = Bucket(name=name, keywords=payload.keywords, position=position)
    db.add(bucket)
    await db.commit()
    return BucketOut(name=bucket.name, keywords=list(bucket.keywords), position=bucket.position, count=0)


@router.patch("/{name}", response_model=BucketOut)
async def patch_bucket(name: str, payload: BucketPatch, db: AsyncSession = Depends(get_db)) -> BucketOut:
    bucket = await db.get(Bucket, name)
    if bucket is None:
        raise HTTPException(status_code=404, detail=f"Bucket not found: {name}")

    if payload.keywords is not None:
        bucket.keywords = payload.keywords
    if payload.position is not None:
        bucket.position = payload.position
    await db.commit()

    count = (await db.execute(select(func.count(Task.id)).where(Task.bucket == name))).scalar() or 0
    return BucketOut(name=bucket.name, keywords=list(bucket.keywords), position=bucket.position, count=count)


@router.delete("/{name}", status_code=204)
async def delete_bucket(name: str, db: AsyncSession = Depends(get_db)) -> None:
    bucket = await db.get(Bucket, name)
    if bucket is None:
        raise HTTPException(status_code=404, detail=f"Bucket not found: {name}")

    await db.delete(bucket)
    # Tasks outlive their bucket; re-home them rather than cascade-deleting real work.
    tasks = (await db.execute(select(Task).where(Task.bucket == name))).scalars().all()
    for task in tasks:
        task.bucket = UNCATEGORIZED
        task.bucket_override = False
    await db.commit()


@router.post("/reassign", response_model=list[BucketOut])
async def reassign(db: AsyncSession = Depends(get_db)) -> list[BucketOut]:
    """Re-run keyword matching over every task — for after you edit bucket keywords."""
    matcher = await load_matcher(db)
    tasks = (await db.execute(select(Task))).scalars().all()
    for task in tasks:
        if not task.bucket_override:
            task.bucket = matcher.assign(task.title, task.tags)
    await db.commit()
    return await list_buckets(db)
