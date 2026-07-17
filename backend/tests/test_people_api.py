"""People over HTTP — the surface the People tab codes against."""

from __future__ import annotations


async def test_create_list_and_get_a_person(client):
    created = await client.post(
        "/api/people",
        json={
            "display_name": "Bruno Vegreville",
            "email": "bruno@acme.dev",
            "identities": [{"kind": "slack", "value": "U9", "label": "bruno.v"}],
        },
    )
    assert created.status_code == 201
    person = created.json()
    assert person["display_name"] == "Bruno Vegreville"
    assert [i["kind"] for i in person["identities"]] == ["slack"]

    listed = (await client.get("/api/people")).json()
    assert [p["id"] for p in listed] == [person["id"]]

    fetched = await client.get(f"/api/people/{person['id']}")
    assert fetched.json()["email"] == "bruno@acme.dev"


async def test_patch_can_clear_a_field(client):
    person = (await client.post("/api/people", json={"display_name": "Bruno", "email": "x@y.z"})).json()

    patched = await client.patch(f"/api/people/{person['id']}", json={"email": None})
    assert patched.json()["email"] is None


async def test_adding_a_claimed_identity_conflicts(client):
    a = (
        await client.post(
            "/api/people",
            json={"display_name": "Bruno", "identities": [{"kind": "slack", "value": "U9"}]},
        )
    ).json()
    b = (await client.post("/api/people", json={"display_name": "Someone"})).json()

    clash = await client.post(f"/api/people/{b['id']}/identities", json={"kind": "slack", "value": "U9"})
    assert clash.status_code == 409

    added = await client.post(f"/api/people/{a['id']}/identities", json={"kind": "github", "value": "brunov"})
    assert {i["kind"] for i in added.json()["identities"]} == {"slack", "github"}


async def test_remove_identity(client):
    person = (
        await client.post(
            "/api/people",
            json={"display_name": "Bruno", "identities": [{"kind": "email", "value": "b@a.dev"}]},
        )
    ).json()
    identity_id = person["identities"][0]["id"]

    stripped = await client.delete(f"/api/people/{person['id']}/identities/{identity_id}")
    assert stripped.json()["identities"] == []


async def test_merge_two_people(client):
    slack_side = (
        await client.post(
            "/api/people",
            json={"display_name": "bruno.v", "identities": [{"kind": "slack", "value": "U9"}]},
        )
    ).json()
    github_side = (
        await client.post(
            "/api/people",
            json={"display_name": "Bruno Vegreville", "identities": [{"kind": "github", "value": "bv"}]},
        )
    ).json()

    merged = await client.post(f"/api/people/{slack_side['id']}/merge", json={"into": github_side["id"]})
    assert merged.json()["id"] == github_side["id"]
    assert {i["kind"] for i in merged.json()["identities"]} == {"slack", "github"}
    assert (await client.get(f"/api/people/{slack_side['id']}")).status_code == 404


async def test_delete_a_person(client):
    person = (await client.post("/api/people", json={"display_name": "Bruno"})).json()
    assert (await client.delete(f"/api/people/{person['id']}")).status_code == 204
    assert (await client.get(f"/api/people/{person['id']}")).status_code == 404


async def test_unknown_person_404s(client):
    assert (await client.get("/api/people/nope")).status_code == 404
    assert (await client.patch("/api/people/nope", json={"display_name": "x"})).status_code == 404
