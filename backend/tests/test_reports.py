from __future__ import annotations

from datetime import UTC, datetime

import httpx
import respx

from app.config import Settings
from app.models import CONFIRMED, Item, Link, Task
from app.services.reports import render_report
from app.sources.github import GitHubSource
from app.sources.linear import LinearSource
from app.sources.slack import _to_item

NOW = datetime.now(UTC)


def _task(**kw) -> Task:
    base = {
        "title": "A task",
        "bucket": "Infra",
        "status": "open",
        "priority": 50,
        "tags": [],
        "unread": False,
        "origin": "manual",
        "updated_at": NOW,
    }
    return Task(**{**base, **kw})


async def test_generate_writes_a_report_per_task_and_a_priority_ordered_map(
    client, db, monkeypatch, tmp_path
):
    hq = tmp_path / "hq"
    monkeypatch.setattr("app.routers.tasks.get_settings", lambda: Settings(hq_dir=hq))

    db.add_all(
        [
            _task(id="task:aaa", title="Ship the API", priority=90),
            _task(id="task:bbb", title="Old thing", priority=10, archived_at=NOW),
        ]
    )
    item = Item(
        id="slack:C01:1.0",
        source="slack",
        label="#eng - hey",
        url="https://acme.slack.com/p1",
        context=None,
        occurred_at=NOW,
        extra={"message_text": "the full slack message, well past fifty characters of content"},
    )
    db.add(item)
    await db.flush()
    db.add(Link(task_id="task:aaa", item_id=item.id, state=CONFIRMED))
    await db.commit()

    result = (await client.post("/api/tasks/reports")).json()
    assert result["count"] == 2

    task_map = (hq / "task-map.md").read_text(encoding="utf-8")
    assert "Ship the API" in task_map and "Old thing" in task_map
    # Priority-ordered: the 90 comes before the 10.
    assert task_map.index("Ship the API") < task_map.index("Old thing")
    # Archived is marked (the archived row carries the ✓).
    archived_row = next(line for line in task_map.splitlines() if "Old thing" in line)
    assert "✓" in archived_row

    report = (hq / "tasks" / "aaa" / "report.md").read_text(encoding="utf-8")
    assert report.startswith("# Ship the API")
    # Full Slack message content — not just the 50-char label — lands in the report.
    assert "the full slack message, well past fifty characters of content" in report


def test_render_report_uses_the_live_detail_when_present():
    task = _task(id="task:x", title="Fix the thing")
    item = Item(
        id="pr:acme~api~7",
        source="pr",
        label="feat: add pagination",
        url="https://github.com/acme/api/pull/7",
        context="#7",
        occurred_at=NOW,
        extra={"repo": "acme/api", "pr_status": "approved"},
    )
    link = Link(task_id=task.id, item_id=item.id, state=CONFIRMED)
    link.item = item
    task.links = [link]

    md = render_report(task, {item.id: "The full PR body\n\n#### Comments\n\n**@ada**:\n\nnice"})

    assert "# Fix the thing" in md
    assert "### [pr] feat: add pagination" in md
    assert "The full PR body" in md and "**@ada**" in md
    assert "**Review:** approved" in md


@respx.mock
async def test_github_item_detail_pulls_the_body_and_comments():
    item = Item(
        id="pr:acme~api~7",
        source="pr",
        label="feat",
        url=None,
        context="#7",
        occurred_at=NOW,
        extra={"repo": "acme/api"},
    )
    respx.get("https://api.github.com/repos/acme/api/pulls/7").mock(
        return_value=httpx.Response(200, json={"body": "Adds pagination to search."})
    )
    respx.get("https://api.github.com/repos/acme/api/issues/7/comments").mock(
        return_value=httpx.Response(
            200,
            json=[{"user": {"login": "ada"}, "body": "Looks good", "created_at": "2026-01-01"}],
        )
    )
    respx.get("https://api.github.com/repos/acme/api/pulls/7/comments").mock(
        return_value=httpx.Response(200, json=[])
    )

    detail = await GitHubSource({"token": "ghp_x", "username": "me", "org": "acme"}).item_detail(item)

    assert "Adds pagination to search." in detail
    assert "**@ada**" in detail and "Looks good" in detail


@respx.mock
async def test_linear_item_detail_pulls_the_description_and_comments():
    item = Item(id="linear:abc-123", source="linear", label="x", context="ENG-1", occurred_at=NOW, extra={})
    respx.post("https://api.linear.app/graphql").mock(
        return_value=httpx.Response(
            200,
            json={
                "data": {
                    "issue": {
                        "description": "Reproduce with the failing invoice.",
                        "comments": {"nodes": [{"body": "On it", "user": {"displayName": "Mo"}}]},
                    }
                }
            },
        )
    )

    detail = await LinearSource({"api_key": "lin_x"}).item_detail(item)

    assert "Reproduce with the failing invoice." in detail
    assert "**Mo**" in detail and "On it" in detail


def test_slack_keeps_the_full_message_text_even_though_the_label_is_truncated():
    long_text = "This is a long Slack message that runs well past the fifty character label cap."
    match = {
        "ts": "1752660000.0001",
        "thread_ts": "1752660000.0001",
        "text": long_text,
        "permalink": "https://acme.slack.com/archives/C01/p1",
        "channel": {"id": "C01", "name": "eng"},
    }

    item = _to_item(match, {}, {})

    assert item.extra["message_text"] == long_text
    assert item.label.endswith("…"), "the UI label is still truncated"
    assert len(item.label) < len(long_text)
