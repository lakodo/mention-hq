"""Local markdown docs — surfaced as reference material attached to a subject."""

from __future__ import annotations

import glob
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import ClassVar

from app.sources.base import ConfigField, RawMention, Source
from app.sources.keys import all_reference_keys

H1_RE = re.compile(r"^#\s+(?P<title>.+?)\s*$", re.MULTILINE)


class MarkdownSource(Source):
    id = "markdown"
    name = "Markdown docs"
    description = "Local docs and specs, attached to the subjects they mention"
    fields: ClassVar[list[ConfigField]] = [
        ConfigField(
            key="globs",
            label="File patterns",
            placeholder="/Users/you/docs/**/*.md",
            help="Comma-separated globs",
        ),
    ]

    def detail(self) -> str:
        return " · ".join(self.get_list("globs")) or "Not configured"

    async def fetch(self) -> list[RawMention]:
        mentions = []
        for pattern in self.get_list("globs"):
            for raw_path in glob.glob(pattern, recursive=True):
                path = Path(raw_path)
                if not path.is_file():
                    continue
                mention = _read_doc(path)
                if mention:
                    mentions.append(mention)
        return mentions


def _read_doc(path: Path) -> RawMention | None:
    try:
        content = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None

    heading = H1_RE.search(content)
    title = heading.group("title") if heading else path.stem.replace("-", " ").replace("_", " ").title()

    # Only the head of the doc is scanned for refs: a long doc citing every ticket in the
    # backlog would otherwise merge unrelated subjects into one giant task.
    head = content[:2000]

    return RawMention(
        source="markdown",
        external_id=str(path),
        label=title,
        occurred_at=datetime.fromtimestamp(path.stat().st_mtime, tz=UTC),
        context=str(path),
        status="open",
        reference_keys=all_reference_keys(title, head),
        extra={"file_path": str(path)},
    )
