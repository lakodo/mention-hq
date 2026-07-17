from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.schemas import (
    PersonCreate,
    PersonIdentityIn,
    PersonMerge,
    PersonOut,
    PersonPatch,
)
from app.services import people

router = APIRouter(prefix="/people", tags=["people"])


@router.get("", response_model=list[PersonOut])
async def list_people(db: AsyncSession = Depends(get_db)):
    return await people.list_people(db)


@router.post("", response_model=PersonOut, status_code=201)
async def create_person(payload: PersonCreate, db: AsyncSession = Depends(get_db)):
    try:
        return await people.create_person(
            db,
            payload.display_name,
            email=payload.email,
            note=payload.note,
            identities=[i.model_dump() for i in payload.identities],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{person_id}", response_model=PersonOut)
async def get_person(person_id: str, db: AsyncSession = Depends(get_db)):
    person = await people.get_person(db, person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found")
    return person


@router.patch("/{person_id}", response_model=PersonOut)
async def update_person(person_id: str, patch: PersonPatch, db: AsyncSession = Depends(get_db)):
    fields = patch.model_dump(exclude_unset=True)
    try:
        return await people.update_person(db, person_id, **fields)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{person_id}", status_code=204)
async def delete_person(person_id: str, db: AsyncSession = Depends(get_db)):
    try:
        await people.delete_person(db, person_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{person_id}/identities", response_model=PersonOut, status_code=201)
async def add_identity(person_id: str, payload: PersonIdentityIn, db: AsyncSession = Depends(get_db)):
    try:
        return await people.add_identity(db, person_id, payload.kind, payload.value, payload.label)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.delete("/{person_id}/identities/{identity_id}", response_model=PersonOut)
async def remove_identity(person_id: str, identity_id: str, db: AsyncSession = Depends(get_db)):
    try:
        return await people.remove_identity(db, person_id, identity_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{person_id}/merge", response_model=PersonOut)
async def merge_people(person_id: str, payload: PersonMerge, db: AsyncSession = Depends(get_db)):
    """Fold this person into `into`, which survives with both sets of identities."""
    try:
        return await people.merge(db, source_id=person_id, target_id=payload.into)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
