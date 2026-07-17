"""The people directory: one human, many source handles, folded together by merge."""

from __future__ import annotations

import pytest

from app.services import people


async def test_a_person_carries_identities_across_sources(db):
    person = await people.create_person(
        db,
        "Ada Lovelace",
        email="ada@acme.dev",
        identities=[
            {"kind": "slack", "value": "U9", "label": "ada.l"},
            {"kind": "github", "value": "adal"},
        ],
    )

    assert person.display_name == "Ada Lovelace"
    assert {(i.kind, i.value) for i in person.identities} == {("slack", "U9"), ("github", "adal")}


async def test_remembering_a_handle_creates_a_person_then_resolves_it(db):
    assert await people.resolve_names(db, "slack", {"U9"}) == {}

    await people.remember(db, "slack", {"U9": "Ada"})

    assert await people.resolve_names(db, "slack", {"U9"}) == {"U9": "Ada"}
    assert len(await people.list_people(db)) == 1


async def test_remembering_a_known_handle_adds_no_duplicate(db):
    await people.remember(db, "slack", {"U9": "Ada"})
    await people.remember(db, "slack", {"U9": "Ada Lovelace"})

    everyone = await people.list_people(db)
    assert len(everyone) == 1
    # The first name sticks — a re-resolve must not silently rename.
    assert everyone[0].display_name == "Ada"


async def test_an_identity_belongs_to_one_person(db):
    await people.create_person(db, "Ada", identities=[{"kind": "slack", "value": "U9"}])
    other = await people.create_person(db, "Someone else")

    with pytest.raises(ValueError, match="already belongs"):
        await people.add_identity(db, other.id, "slack", "U9")


async def test_identities_can_be_added_and_removed(db):
    person = await people.create_person(db, "Ada")
    person = await people.add_identity(db, person.id, "email", "ada@acme.dev")
    identity_id = next(i.id for i in person.identities)

    person = await people.remove_identity(db, person.id, identity_id)
    assert person.identities == []


async def test_merge_folds_one_person_into_another(db):
    slack_side = await people.create_person(db, "ada.l", identities=[{"kind": "slack", "value": "U9"}])
    github_side = await people.create_person(
        db, "Ada Lovelace", identities=[{"kind": "github", "value": "adal"}]
    )

    merged = await people.merge(db, source_id=slack_side.id, target_id=github_side.id)

    assert merged.id == github_side.id
    assert merged.display_name == "Ada Lovelace"
    assert {(i.kind, i.value) for i in merged.identities} == {("slack", "U9"), ("github", "adal")}
    assert await people.get_person(db, slack_side.id) is None
    # And the slack id now resolves to the surviving person.
    assert await people.resolve_names(db, "slack", {"U9"}) == {"U9": "Ada Lovelace"}


async def test_merge_refuses_a_person_into_themselves(db):
    person = await people.create_person(db, "Ada")
    with pytest.raises(ValueError, match="themselves"):
        await people.merge(db, source_id=person.id, target_id=person.id)


async def test_updating_and_deleting_a_person(db):
    person = await people.create_person(db, "Ada", email="old@acme.dev")

    person = await people.update_person(db, person.id, display_name="Ada L", email="new@acme.dev")
    assert person.display_name == "Ada L"
    assert person.email == "new@acme.dev"

    await people.delete_person(db, person.id)
    assert await people.get_person(db, person.id) is None
