"""HTTP-level tests.

Service-level tests call functions directly and so cannot catch routing or serialisation
bugs. Anything reachable over an endpoint is exercised through the URL here.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models import CONFIRMED, PROPOSED, REJECTED, Bucket, Item, Link, Task
from app.sources.base import RawItem, url_safe


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("owner/branch-name", "owner~branch-name"),
        ("org/repo#1201", "org~repo~1201"),
        ("C01ABC:1712.0001", "C01ABC:1712.0001"),
        ("plain", "plain"),
    ],
)
def test_url_safe_strips_path_breaking_characters(raw, expected):
    assert url_safe(raw) == expected


def test_item_id_is_url_safe():
    item = RawItem(
        source="branch",
        external_id="repo:owner/feature",
        label="x",
        occurred_at=datetime.now(UTC),
    )
    assert "/" not in item.id
    assert item.id == "branch:repo:owner~feature"


async def _make_task(db, task_id="task:1", title="A task", bucket="Uncategorized") -> Task:
    task = Task(
        id=task_id,
        title=title,
        bucket=bucket,
        status="open",
        tags=[],
        unread=True,
        origin="auto",
        updated_at=datetime.now(UTC),
    )
    db.add(task)
    await db.flush()
    return task


async def _make_item(db, item_id="branch:repo:owner~feature") -> Item:
    item = Item(
        id=item_id,
        source="branch",
        label="[repo] owner/feature",
        url=None,
        context="repo",
        occurred_at=datetime.now(UTC),
        extra={},
    )
    db.add(item)
    await db.flush()
    return item


async def test_health(client):
    assert (await client.get("/health")).json() == {"status": "ok"}


async def test_a_fresh_install_has_no_buckets(client):
    assert (await client.get("/buckets")).json() == []


async def test_bucket_crud(client, db):
    created = await client.post("/buckets", json={"name": "Infra", "keywords": ["deploy"]})
    assert created.status_code == 201
    assert created.json()["count"] == 0

    duplicate = await client.post("/buckets", json={"name": "Infra"})
    assert duplicate.status_code == 409

    reserved = await client.post("/buckets", json={"name": "Uncategorized"})
    assert reserved.status_code == 400

    patched = await client.patch("/buckets/Infra", json={"keywords": ["deploy", "ci"]})
    assert patched.json()["keywords"] == ["deploy", "ci"]


async def test_deleting_a_bucket_rehomes_its_tasks_rather_than_deleting_them(client, db):
    db.add(Bucket(name="Infra", keywords=[], position=1))
    await _make_task(db, bucket="Infra")
    await db.commit()

    assert (await client.delete("/buckets/Infra")).status_code == 204
    assert (await client.get("/tasks/task:1")).json()["bucket"] == "Uncategorized"


async def test_reassign_applies_new_keywords(client, db):
    await _make_task(db, title="Terraform apply hangs")
    db.add(Bucket(name="Infra", keywords=["terraform"], position=1))
    await db.commit()

    await client.post("/buckets/reassign")
    assert (await client.get("/tasks/task:1")).json()["bucket"] == "Infra"


async def test_reassign_leaves_a_hand_picked_bucket_alone(client, db):
    task = await _make_task(db, title="Terraform apply hangs")
    task.bucket = "Elsewhere"
    task.bucket_override = True
    db.add(Bucket(name="Infra", keywords=["terraform"], position=1))
    await db.commit()

    await client.post("/buckets/reassign")
    assert (await client.get("/tasks/task:1")).json()["bucket"] == "Elsewhere"


async def test_patch_task_marks_bucket_as_overridden(client, db):
    await _make_task(db)
    await db.commit()

    response = await client.patch("/tasks/task:1", json={"bucket": "Infra", "unread": False})
    assert response.json()["bucket"] == "Infra"
    assert response.json()["unread"] is False

    task = await db.get(Task, "task:1")
    await db.refresh(task)
    assert task.bucket_override is True


async def test_patch_unknown_task_404s(client):
    assert (await client.patch("/tasks/nope", json={"unread": False})).status_code == 404


async def test_confirm_an_item_whose_id_contains_a_slash(client, db):
    """Branch ids contain a slash, which a URL path segment cannot carry unescaped."""
    await _make_task(db)
    item = await _make_item(db)
    await db.commit()

    response = await client.post(f"/catchup/{item.id}/confirm", json={"task_ids": ["task:1"]})
    assert response.status_code == 200, response.text
    assert response.json()["triaged"] is True
    assert [link["task"]["id"] for link in response.json()["links"]] == ["task:1"]


async def test_one_item_confirms_onto_several_tasks(client, db):
    await _make_task(db, "task:1", "One subject")
    await _make_task(db, "task:2", "Another subject")
    item = await _make_item(db)
    await db.commit()

    response = await client.post(f"/catchup/{item.id}/confirm", json={"task_ids": ["task:1", "task:2"]})
    links = response.json()["links"]
    assert {link["task"]["id"] for link in links} == {"task:1", "task:2"}
    assert {link["state"] for link in links} == {CONFIRMED}


async def test_confirming_onto_an_unknown_task_404s(client, db):
    item = await _make_item(db)
    await db.commit()
    response = await client.post(f"/catchup/{item.id}/confirm", json={"task_ids": ["nope"]})
    assert response.status_code == 404


async def test_rejecting_a_proposal_records_the_decision(client, db):
    await _make_task(db)
    item = await _make_item(db)
    db.add(
        Link(
            task_id="task:1",
            item_id=item.id,
            state=PROPOSED,
            engine="keys",
            confidence=0.9,
            reason="…",
        )
    )
    await db.commit()

    response = await client.post(f"/catchup/{item.id}/reject/task:1")
    assert response.status_code == 200, response.text
    assert [link["state"] for link in response.json()["links"]] == [REJECTED]


async def test_a_proposal_is_exposed_with_its_reasoning(client, db):
    await _make_task(db)
    item = await _make_item(db)
    db.add(
        Link(
            task_id="task:1",
            item_id=item.id,
            state=PROPOSED,
            engine="title-similarity",
            confidence=0.72,
            reason='Title looks like "A task" (90% similar)',
        )
    )
    await db.commit()

    link = (await client.get("/catchup")).json()[0]["links"][0]
    assert link["state"] == PROPOSED
    assert link["engine"] == "title-similarity"
    assert link["confidence"] == 0.72
    assert "similar" in link["reason"]


async def test_catchup_lists_only_untriaged(client, db):
    item = await _make_item(db)
    await db.commit()
    assert len((await client.get("/catchup")).json()) == 1

    await client.post(f"/catchup/{item.id}/triage", json={"triaged": True})
    assert (await client.get("/catchup")).json() == []


async def test_new_task_from_an_item(client, db):
    item = await _make_item(db)
    await db.commit()

    response = await client.post(f"/catchup/{item.id}/new-task", json={"title": "A new subject"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "A new subject"
    assert body["origin"] == "manual"
    assert [i["id"] for i in body["items"]] == [item.id]


async def test_filter_tasks_by_source(client, db):
    await _make_task(db, "task:1")
    await _make_task(db, "task:2", title="Unrelated")
    item = await _make_item(db)
    db.add(Link(task_id="task:1", item_id=item.id, state=CONFIRMED))
    await db.commit()

    assert [t["id"] for t in (await client.get("/tasks?source=branch")).json()] == ["task:1"]
    assert (await client.get("/tasks?source=slack")).json() == []


async def test_a_rejected_link_does_not_put_the_item_on_the_task(client, db):
    await _make_task(db)
    item = await _make_item(db)
    db.add(Link(task_id="task:1", item_id=item.id, state=REJECTED))
    await db.commit()

    assert (await client.get("/tasks/task:1")).json()["items"] == []
    assert (await client.get("/tasks?source=branch")).json() == []


async def test_manual_task_can_be_deleted_but_auto_cannot(client, db):
    await _make_task(db, "task:auto")
    await db.commit()
    assert (await client.delete("/tasks/task:auto")).status_code == 400

    created = (await client.post("/tasks", json={"title": "Mine"})).json()
    assert (await client.delete(f"/tasks/{created['id']}")).status_code == 204


async def test_admin_reports_source_fields_without_leaking_secrets(client, isolated_secrets):
    isolated_secrets.set("github", "token", "ghp_supersecrettoken1234")

    sources = {s["id"]: s for s in (await client.get("/admin/sources")).json()}
    token_field = next(f for f in sources["github"]["fields"] if f["key"] == "token")

    assert token_field["is_set"] is True
    assert "supersecret" not in str(sources["github"])
    assert token_field["value"].endswith("1234")


async def test_app_name_is_configurable(client):
    assert (await client.get("/admin/settings")).json()["app_name"] == "Personal HQ"

    await client.patch("/admin/settings", json={"app_name": "My HQ"})
    assert (await client.get("/admin/settings")).json()["app_name"] == "My HQ"


async def test_sync_rejects_an_unknown_source(client):
    assert (await client.post("/sync", json={"source": "nope"})).status_code == 400
