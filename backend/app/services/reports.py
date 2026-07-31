"""Per-task Markdown reports written under `hq_dir` (default ~/.hq).

A report gathers everything HQ knows about a task — its items with their full content (a PR body
and comments, a Linear description and comments, a Slack message, a local file) — into one file a
person, or another tool, can read without opening eight tabs. A `task-map.md` indexes them by
priority. HQ writes these on a deliberate action; it never posts anything back to a source.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import Settings
from app.models import Item, Task
from app.services.backup import _open_in_file_manager
from app.services.sources_factory import build_connected
from app.sources.base import Source


@dataclass
class ReportsResult:
    count: int
    task_map_path: Path


def _short_id(task_id: str) -> str:
    """A path-safe folder name — the task id without its `task:` prefix."""
    return task_id.removeprefix("task:")


async def generate_all_reports(db: AsyncSession, settings: Settings) -> ReportsResult:
    """(Re)write every task's report and the task-map index. Returns the count and map path."""
    tasks = list(
        (await db.execute(select(Task).order_by(Task.priority.desc(), Task.updated_at.desc())))
        .scalars()
        .all()
    )
    sources = {c.instance.id: c.source for c in await build_connected(db)}

    tasks_dir = settings.hq_dir / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    for task in tasks:
        details = await _item_details(task.items, sources)
        folder = tasks_dir / _short_id(task.id)
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "report.md").write_text(render_report(task, details), encoding="utf-8")

    map_path = settings.hq_dir / "task-map.md"
    map_path.write_text(render_task_map(tasks), encoding="utf-8")
    return ReportsResult(count=len(tasks), task_map_path=map_path)


async def _item_details(items: list[Item], sources: dict[str, Source]) -> dict[str, str | None]:
    """Live-fetch each item's rich content concurrently; a failure just leaves that item to its
    stored fields rather than sinking the whole report."""

    async def one(item: Item) -> tuple[str, str | None]:
        source = sources.get(item.instance_id or "")
        if source is None:
            return item.id, None
        try:
            return item.id, await source.item_detail(item)
        except Exception:
            return item.id, None

    return dict(await asyncio.gather(*(one(item) for item in items)))


def reveal_reports(settings: Settings) -> Path:
    folder = settings.hq_dir
    folder.mkdir(parents=True, exist_ok=True)
    _open_in_file_manager(folder)
    return folder


# --- rendering (pure) ---------------------------------------------------------------------


def render_task_map(tasks: list[Task]) -> str:
    lines = [
        "# Task map",
        "",
        "Every task, most urgent first. Skip the archived ones for active work.",
        "",
        "| Priority | Task | Status | Bucket | Archived | Items | Report |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for task in tasks:
        title = task.title.replace("|", "\\|")
        archived = "✓" if task.archived else "—"
        report = f"[report](tasks/{_short_id(task.id)}/report.md)"
        lines.append(
            f"| {task.priority} | {title} | {task.status} | {task.bucket} | "
            f"{archived} | {len(task.items)} | {report} |"
        )
    return "\n".join(lines) + "\n"


def render_report(task: Task, details: dict[str, str | None]) -> str:
    out: list[str] = [f"# {task.title}", ""]

    meta = [
        f"- **Status:** {task.status}",
        f"- **Bucket:** {task.bucket}",
        f"- **Priority:** {task.priority}",
        f"- **Archived:** {'yes' if task.archived else 'no'}",
    ]
    if task.tags:
        meta.append(f"- **Tags:** {', '.join(task.tags)}")
    out += [*meta, ""]

    if task.description:
        out += ["## Description", "", task.description, ""]
    if task.next_action:
        out += ["## Next action", "", task.next_action, ""]

    people = _people(task)
    if people:
        out += ["## People", "", *people, ""]

    out += ["## Items", ""]
    if not task.items:
        out += ["_No items filed on this task yet._", ""]
    for item in task.items:
        out += _item_section(item, details.get(item.id))
    return "\n".join(out).rstrip() + "\n"


def _item_section(item: Item, detail: str | None) -> list[str]:
    heading = f"### [{item.source}] {item.label}"
    lines = [heading, ""]
    if item.url:
        lines.append(f"- **Link:** {item.url}")
    if item.context:
        lines.append(f"- **Ref:** {item.context}")
    if item.item_status:
        lines.append(f"- **State:** {item.item_status}")
    elif item.pr_status:
        lines.append(f"- **Review:** {item.pr_status}")
    if item.done:
        lines.append("- **Done:** yes")
    lines.append("")

    body = detail or _stored_content(item)
    if body:
        lines += [body, ""]
    return lines


def _stored_content(item: Item) -> str | None:
    """Rich content already stored (no live fetch): the full Slack message, a note's text."""
    extra = item.extra or {}
    if item.source == "slack":
        parts = [extra["message_text"]] if extra.get("message_text") else []
        parts += [f"Attachment: {url}" for url in extra.get("files") or []]
        return "\n\n".join(parts) or None
    if item.source == "note":
        return extra.get("text") or None
    return None


def _people(task: Task) -> list[str]:
    seen: dict[tuple[str, str], str] = {}
    for item in task.items:
        for person in item.people:
            key = (person.get("kind", ""), person.get("value", ""))
            if key in seen:
                continue
            name = person.get("name") or person.get("value") or "someone"
            avatar = person.get("avatar")
            seen[key] = f"- {name} ({person.get('role', 'involved')})" + (f" — {avatar}" if avatar else "")
    return list(seen.values())
