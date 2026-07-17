"""The people directory: humans and the handles they go by across sources.

A source contributes identities (a Slack id, a GitHub login) and a name for them; HQ keeps
one Person per human so a name learned once answers everywhere, and merging folds the
duplicates a first sync inevitably creates. No source is the owner — every identity is just
a `(kind, value)` that points at a person.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import SessionLocal
from app.models import Person, PersonIdentity

_UNSET = object()


def _person_id() -> str:
    return f"person:{uuid.uuid4().hex[:12]}"


def _identity_id() -> str:
    return f"pid:{uuid.uuid4().hex[:12]}"


async def _reload(db: AsyncSession, person_id: str) -> Person:
    stmt = select(Person).where(Person.id == person_id).execution_options(populate_existing=True)
    return (await db.execute(stmt)).scalars().one()


async def list_people(db: AsyncSession) -> list[Person]:
    stmt = select(Person).order_by(Person.display_name)
    return list((await db.execute(stmt)).scalars().all())


async def get_person(db: AsyncSession, person_id: str) -> Person | None:
    return await db.get(Person, person_id)


async def _identity_owner(db: AsyncSession, kind: str, value: str) -> PersonIdentity | None:
    stmt = select(PersonIdentity).where(PersonIdentity.kind == kind, PersonIdentity.value == value)
    return (await db.execute(stmt)).scalars().one_or_none()


async def _attach(db: AsyncSession, person: Person, kind: str, value: str, label: str | None) -> None:
    kind, value = kind.strip(), value.strip()
    if not kind or not value:
        raise ValueError("An identity needs both a kind and a value")
    if await _identity_owner(db, kind, value) is not None:
        raise ValueError(f"{kind}:{value} already belongs to someone")
    db.add(PersonIdentity(id=_identity_id(), person=person, kind=kind, value=value, label=label))


async def create_person(
    db: AsyncSession,
    display_name: str,
    email: str | None = None,
    note: str | None = None,
    identities: list[dict] | None = None,
) -> Person:
    name = display_name.strip()
    if not name:
        raise ValueError("A person needs a name")
    now = datetime.now(UTC)
    person = Person(id=_person_id(), display_name=name, email=email, note=note, updated_at=now)
    db.add(person)
    await db.flush()
    for identity in identities or []:
        await _attach(db, person, identity["kind"], identity["value"], identity.get("label"))
    await db.commit()
    return await _reload(db, person.id)


async def update_person(
    db: AsyncSession,
    person_id: str,
    *,
    display_name: str | None = None,
    email: str | None | object = _UNSET,
    note: str | None | object = _UNSET,
) -> Person:
    person = await db.get(Person, person_id)
    if person is None:
        raise LookupError(f"Person not found: {person_id}")
    if display_name is not None and display_name.strip():
        person.display_name = display_name.strip()
    if email is not _UNSET:
        person.email = email or None
    if note is not _UNSET:
        person.note = note or None
    person.updated_at = datetime.now(UTC)
    await db.commit()
    return await _reload(db, person_id)


async def delete_person(db: AsyncSession, person_id: str) -> None:
    person = await db.get(Person, person_id)
    if person is None:
        raise LookupError(f"Person not found: {person_id}")
    await db.delete(person)
    await db.commit()


async def add_identity(
    db: AsyncSession, person_id: str, kind: str, value: str, label: str | None = None
) -> Person:
    person = await db.get(Person, person_id)
    if person is None:
        raise LookupError(f"Person not found: {person_id}")
    await _attach(db, person, kind, value, label)
    await db.commit()
    return await _reload(db, person_id)


async def remove_identity(db: AsyncSession, person_id: str, identity_id: str) -> Person:
    identity = await db.get(PersonIdentity, identity_id)
    if identity is None or identity.person_id != person_id:
        raise LookupError(f"Identity not found: {identity_id}")
    await db.delete(identity)
    await db.commit()
    return await _reload(db, person_id)


async def merge(db: AsyncSession, source_id: str, target_id: str) -> Person:
    """Fold `source` into `target`: move its identities over, then delete it."""
    if source_id == target_id:
        raise ValueError("A person cannot merge into themselves")
    source = await db.get(Person, source_id)
    target = await db.get(Person, target_id)
    if source is None or target is None:
        raise LookupError("Both people must exist to merge")
    # Reassign through the relationship, not the raw FK: leaving them in source.identities
    # would let delete-orphan take them down with source.
    for identity in list(source.identities):
        identity.person = target
    target.email = target.email or source.email
    target.updated_at = datetime.now(UTC)
    await db.flush()
    await db.delete(source)
    await db.commit()
    return await _reload(db, target_id)


async def resolve_names(db: AsyncSession, kind: str, values: set[str]) -> dict[str, str]:
    if not values:
        return {}
    stmt = (
        select(PersonIdentity.value, Person.display_name)
        .join(Person, Person.id == PersonIdentity.person_id)
        .where(PersonIdentity.kind == kind, PersonIdentity.value.in_(values))
    )
    return dict((await db.execute(stmt)).all())


async def remember(db: AsyncSession, kind: str, names: dict[str, str]) -> None:
    """Record handle -> name pairs a source just discovered, one new Person each.

    Duplicates are folded later, by hand, in the People tab — auto-merging on a name match
    would silently conflate two different people who happen to share one.
    """
    if not names:
        return
    known = await resolve_names(db, kind, set(names))
    now = datetime.now(UTC)
    for value, name in names.items():
        if value in known:
            continue
        person = Person(id=_person_id(), display_name=name or value, updated_at=now)
        db.add(person)
        await db.flush()
        db.add(PersonIdentity(id=_identity_id(), person=person, kind=kind, value=value, label=name))
        try:
            await db.commit()
        except IntegrityError:
            # A concurrent sync got there first; its row is as good as ours.
            await db.rollback()


class DbDirectory:
    """The `PeopleDirectory` a source consults, backed by its own short-lived sessions so it
    never shares the sync's session across the concurrent fetch."""

    async def known(self, kind: str, values: set[str]) -> dict[str, str]:
        async with SessionLocal() as session:
            return await resolve_names(session, kind, values)

    async def remember(self, kind: str, names: dict[str, str]) -> None:
        async with SessionLocal() as session:
            await remember(session, kind, names)
