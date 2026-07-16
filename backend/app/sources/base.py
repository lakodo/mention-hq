"""Source adapter interface.

Sources never create tasks. They emit `RawMention`s, and `services/grouping.py` decides
which mentions describe the same subject. That keeps the grouping heuristics in one
testable place rather than smeared across eight adapters.

Each source also declares its own `fields`, which is what lets the Admin panel render a
setup form for a source it has never heard of: add an adapter here and the UI grows a
working form for it, with secret fields handled as secrets.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar, Literal

TITLE_PRIORITY = ["linear", "issue", "pr", "markdown", "todo", "branch", "dust", "slack"]

STATUS_PRIORITY = ["in_progress", "open", "merged", "done"]


@dataclass(frozen=True)
class ConfigField:
    key: str
    label: str
    kind: Literal["text", "secret"] = "text"
    required: bool = True
    placeholder: str = ""
    help: str = ""


@dataclass
class RawMention:
    source: str
    external_id: str
    label: str
    occurred_at: datetime
    url: str | None = None
    context: str | None = None
    title: str | None = None
    status: str | None = None
    tags: list[str] = field(default_factory=list)
    # Keys naming *this* mention, e.g. {"PAY-88"} for a Linear issue.
    identity_keys: set[str] = field(default_factory=set)
    # Keys this mention points at, e.g. a PR body citing "PAY-88". Grouping merges a
    # mention into a task when its references hit another mention's identity.
    reference_keys: set[str] = field(default_factory=set)
    extra: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"{self.source}:{self.external_id}"

    def task_title(self) -> str:
        return self.title or self.label


class Source(abc.ABC):
    id: ClassVar[str]
    name: ClassVar[str]
    description: ClassVar[str] = ""
    fields: ClassVar[list[ConfigField]] = []

    def __init__(self, config: dict[str, str] | None = None) -> None:
        self._config = config or {}

    def get(self, key: str, default: str = "") -> str:
        return (self._config.get(key) or default).strip()

    def get_list(self, key: str) -> list[str]:
        return [part.strip() for part in self.get(key).split(",") if part.strip()]

    @property
    def secret_keys(self) -> list[str]:
        return [f.key for f in self.fields if f.kind == "secret"]

    def is_configured(self) -> bool:
        return all(self.get(f.key) for f in self.fields if f.required)

    @abc.abstractmethod
    async def fetch(self) -> list[RawMention]: ...

    def detail(self) -> str:
        return ""

    async def check(self) -> None:
        """Raise if the source is unreachable or misconfigured. Backs /admin/sources/{id}/test."""
        if not self.is_configured():
            missing = [f.label for f in self.fields if f.required and not self.get(f.key)]
            raise SourceNotConfigured(f"Missing: {', '.join(missing)}")


class SourceNotConfigured(RuntimeError):
    pass
