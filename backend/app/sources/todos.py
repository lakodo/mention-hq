"""Todo lines scraped out of local files."""

from __future__ import annotations

import glob
import hashlib
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from app.sources.base import ConfigField, RawItem, Source, SourceNotConfigured
from app.sources.keys import all_reference_keys

TODO_PATTERNS = [
    re.compile(r"^\s*[-*]\s*\[ \]\s+(?P<text>.+?)\s*$"),
    re.compile(r"^\s*TODO:\s*(?P<text>.+?)\s*$"),
    re.compile(r"^\s*[☐•]\s+(?P<text>.+?)\s*$"),
]


class TodoSource(Source):
    id = "todo"
    name = "Todo list"
    description = "Unchecked todo lines in your local files"
    setup = "No credentials — point it at the files you keep todos in."
    fields: ClassVar[list[ConfigField]] = [
        ConfigField(
            key="globs",
            label="File patterns",
            placeholder="/Users/you/todo.md, /Users/you/notes/**/*.md",
            help="Comma-separated globs. Matches '- [ ] …', 'TODO: …', '☐ …'",
        ),
    ]

    def detail(self) -> str:
        return " · ".join(self.get_list("globs")) or "Not configured"

    async def check(self) -> None:
        await super().check()
        if not self._files():
            raise SourceNotConfigured("No files matched those patterns")

    def _files(self) -> list[Path]:
        paths: list[Path] = []
        for pattern in self.get_list("globs"):
            paths.extend(Path(p) for p in glob.glob(pattern, recursive=True))
        return [p for p in paths if p.is_file()]

    async def fetch(self) -> list[RawItem]:
        items: list[RawItem] = []
        for path in self._files():
            items.extend(_scan_file(path))
        return items


def _scan_file(path: Path) -> list[RawItem]:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    # Ids must survive edits elsewhere in the file, so they hash the todo text
    # rather than the line number — otherwise inserting a line above re-creates every task.
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    file_key = hashlib.sha1(str(path).encode()).hexdigest()[:8]

    items = []
    for lineno, line in enumerate(content.splitlines(), start=1):
        text = _match_todo(line)
        if text is None:
            continue
        text_key = hashlib.sha1(text.encode()).hexdigest()[:8]
        items.append(
            RawItem(
                source="todo",
                external_id=f"{file_key}:{text_key}",
                label=text,
                occurred_at=modified,
                context=f"{path.name}:{lineno}",
                status="open",
                reference_keys=all_reference_keys(text),
                extra={"file_path": str(path), "line_number": lineno},
            )
        )
    return items


def _match_todo(line: str) -> str | None:
    for pattern in TODO_PATTERNS:
        match = pattern.match(line)
        if match:
            return match.group("text").strip()
    return None
