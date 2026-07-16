"""HTTP-level tests.

The service tests call functions directly, which means they can't see routing bugs — ids
with slashes in them 404'd for a while precisely because nothing exercised the URL.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.models import Bucket, Mention, Task, TaskMention
from app.sources.base import RawMention, url_safe


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("joris/pay-88-refunds", "joris~pay-88-refunds"),
        ("alan-eu/alan-apps#1201", "alan-eu~alan-apps~1201"),
        ("C01ABC:1712.0001", "C01ABC:1712.0001"),
        ("plain", "plain"),
    ],
)
def test_url_safe_strips_path_breaking_characters(raw, expected):
    assert url_safe(raw) == expected


def test_mention_id_is_url_safe():
    mention = RawMention(
        source="branch",
        external_id="repo:joris/pay-88",
        label="x",
        occurred_at=datetime.now(UTC),
    )
    assert "/" not in mention.id
    assert mention.id == "branch:repo:joris~pay-88"


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


async def _make_mention(db, mention_id="branch:repo:joris~pay-88") -> Mention:
    mention = Mention(
        id=mention_id,
        source="branch",
        label="[repo] joris/pay-88",
        url=None,
        context="repo",
        occurred_at=datetime.now(UTC),
        extra={},
    )
    db.add(mention)
    await db.flush()
    return mention


async def test_health(client):
    assert (await client.get("/health")).json() == {"status": "ok"}


async def test_no_buckets_ship_with_the_app(client):
    assert (await client.get("/buckets")).json() == []


async def test_bucket_crud(client, db):
    created = await client.post("/buckets", json={"name": "Payments", "keywords": ["refund"]})
    assert created.status_code == 201
    assert created.json()["count"] == 0

    duplicate = await client.post("/buckets", json={"name": "Payments"})
    assert duplicate.status_code == 409

    reserved = await client.post("/buckets", json={"name": "Uncategorized"})
    assert reserved.status_code == 400

    patched = await client.patch("/buckets/Payments", json={"keywords": ["refund", "invoice"]})
    assert patched.json()["keywords"] == ["refund", "invoice"]


async def test_deleting_a_bucket_rehomes_its_tasks_rather_than_deleting_them(client, db):
    db.add(Bucket(name="Payments", keywords=[], position=1))
    await _make_task(db, bucket="Payments")
    await db.commit()

    assert (await client.delete("/buckets/Payments")).status_code == 204

    task = (await client.get("/tasks/task:1")).json()
    assert task["bucket"] == "Uncategorized"


async def test_reassign_applies_new_keywords(client, db):
    await _make_task(db, title="Refund flow throws")
    db.add(Bucket(name="Payments", keywords=["refund"], position=1))
    await db.commit()

    await client.post("/buckets/reassign")
    assert (await client.get("/tasks/task:1")).json()["bucket"] == "Payments"


async def test_reassign_leaves_manual_buckets_alone(client, db):
    task = await _make_task(db, title="Refund flow throws")
    task.bucket = "Infra"
    task.bucket_override = True
    db.add(Bucket(name="Payments", keywords=["refund"], position=1))
    await db.commit()

    await client.post("/buckets/reassign")
    assert (await client.get("/tasks/task:1")).json()["bucket"] == "Infra"


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


async def test_attach_a_mention_whose_id_contains_a_slash(client, db):
    """The routing regression: branch ids used to 404 because of the slash."""
    await _make_task(db)
    mention = await _make_mention(db)
    await db.commit()

    response = await client.post(f"/catchup/{mention.id}/attach", json={"task_ids": ["task:1"]})
    assert response.status_code == 200, response.text
    assert response.json()["triaged"] is True
    assert [t["id"] for t in response.json()["tasks"]] == ["task:1"]


async def test_one_mention_attaches_to_several_tasks(client, db):
    await _make_task(db, "task:1", "Refund bug")
    await _make_task(db, "task:2", "CI migration")
    mention = await _make_mention(db)
    await db.commit()

    response = await client.post(f"/catchup/{mention.id}/attach", json={"task_ids": ["task:1", "task:2"]})
    assert {t["id"] for t in response.json()["tasks"]} == {"task:1", "task:2"}


async def test_attaching_to_an_unknown_task_404s(client, db):
    mention = await _make_mention(db)
    await db.commit()
    response = await client.post(f"/catchup/{mention.id}/attach", json={"task_ids": ["nope"]})
    assert response.status_code == 404


async def test_detach_removes_the_link(client, db):
    await _make_task(db)
    mention = await _make_mention(db)
    db.add(TaskMention(task_id="task:1", mention_id=mention.id, linked_by="auto"))
    await db.commit()

    response = await client.delete(f"/catchup/{mention.id}/attach/task:1")
    assert response.json()["tasks"] == []


async def test_catchup_lists_only_untriaged(client, db):
    mention = await _make_mention(db)
    await db.commit()
    assert len((await client.get("/catchup")).json()) == 1

    await client.post(f"/catchup/{mention.id}/triage", json={"triaged": True})
    assert (await client.get("/catchup")).json() == []


async def test_new_task_from_a_mention(client, db):
    mention = await _make_mention(db)
    await db.commit()

    response = await client.post(f"/catchup/{mention.id}/new-task", json={"title": "Fix the refund flow"})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Fix the refund flow"
    assert body["origin"] == "manual"
    assert [m["id"] for m in body["mentions"]] == [mention.id]


async def test_filter_tasks_by_source(client, db):
    await _make_task(db, "task:1")
    await _make_task(db, "task:2", title="Unrelated")
    mention = await _make_mention(db)
    db.add(TaskMention(task_id="task:1", mention_id=mention.id, linked_by="auto"))
    await db.commit()

    assert [t["id"] for t in (await client.get("/tasks?source=branch")).json()] == ["task:1"]
    assert (await client.get("/tasks?source=slack")).json() == []


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

    await client.patch("/admin/settings", json={"app_name": "Jojo HQ"})
    assert (await client.get("/admin/settings")).json()["app_name"] == "Jojo HQ"


async def test_sync_rejects_an_unknown_source(client):
    response = await client.post("/sync", json={"source": "nope"})
    assert response.status_code == 400
