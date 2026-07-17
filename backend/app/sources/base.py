"""Source adapter interface.

Sources never create tasks. They emit `RawItem`s, and `app/engine/` proposes where each
one attaches. That keeps attachment heuristics in one testable place rather than smeared
across eight adapters.

Each source declares its own `fields`, which is what lets the Admin panel render a setup
form for a source it has never heard of: add an adapter here and the UI grows a working
form for it, with secret fields handled as secrets.
"""

from __future__ import annotations

import abc
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import ClassVar, Literal, Protocol

TITLE_PRIORITY = ["linear", "issue", "pr", "markdown", "todo", "branch", "dust", "slack"]

# Item ids travel in URL paths, and a path segment cannot hold a slash — which branch
# names and repo-qualified ids both contain. Ids are restricted to RFC 3986 unreserved
# characters plus ':' at construction, rather than leaving every route to remember to
# encode them.
_URL_UNSAFE = re.compile(r"[^A-Za-z0-9._~:-]")

STATUS_PRIORITY = ["in_progress", "open", "merged", "done"]


@dataclass(frozen=True)
class ConfigField:
    key: str
    label: str
    kind: Literal["text", "secret"] = "text"
    required: bool = True
    placeholder: str = ""
    help: str = ""
    # Where the user goes to obtain this value, when it comes from a web page.
    help_url: str = ""


@dataclass
class Detection:
    """What a local tool already knows, so the user doesn't retype it.

    Secrets in `values` are written straight to the keychain and never returned to the
    browser; `choices` offers the user a pick where a tool knows the options but not the
    answer.
    """

    available: bool
    detail: str
    values: dict[str, str] = field(default_factory=dict)
    choices: dict[str, list[str]] = field(default_factory=dict)


@dataclass
class RawItem:
    source: str
    external_id: str
    label: str
    occurred_at: datetime
    url: str | None = None
    context: str | None = None
    title: str | None = None
    status: str | None = None
    tags: list[str] = field(default_factory=list)
    # Keys naming this item, such as the issue key of a tracker issue.
    identity_keys: set[str] = field(default_factory=set)
    # Keys this item points at, such as a ticket cited in a PR body. An engine proposes a
    # link when one item's references hit another's identity.
    reference_keys: set[str] = field(default_factory=set)
    # People the item concerns, each `{kind, value, name, role}` — a source names them its own
    # way (a Slack mention, a PR reviewer, a Linear assignee). Aggregated onto the task.
    people: list[dict] = field(default_factory=list)
    extra: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return f"{self.source}:{url_safe(self.external_id)}"

    def task_title(self) -> str:
        return self.title or self.label


def url_safe(value: str) -> str:
    """Make an external id safe to put in a URL path segment.

    Collisions are conceivable in theory (`a/b` and `a~b` both become `a~b`) but not in
    practice: the inputs are repo paths, branch names and channel ids, where `~` doesn't
    appear. Readability matters more here — these ids show up in logs and URLs.
    """
    return _URL_UNSAFE.sub("~", value)


class PeopleDirectory(Protocol):
    """A persistent id -> name lookup a source can consult while rendering.

    It spares a source re-asking who an id belongs to on every sync: names learned once are
    remembered. The directory spans every source, so a name a source contributes can answer
    for another — no source owns a person.
    """

    async def known(self, kind: str, values: set[str]) -> dict[str, str]:
        """Names already on file for these (kind, value) handles. Misses are simply absent."""
        ...

    async def remember(self, kind: str, names: dict[str, str]) -> None:
        """Record newly discovered handle -> name pairs for next time."""
        ...


class Source(abc.ABC):
    id: ClassVar[str]
    name: ClassVar[str]
    description: ClassVar[str] = ""
    fields: ClassVar[list[ConfigField]] = []
    # Prose for the Admin panel: what this needs and where it comes from.
    setup: ClassVar[str] = ""
    setup_url: ClassVar[str] = ""
    # A config blob the user pastes into the other service to provision access.
    manifest: ClassVar[str] = ""
    manifest_hint: ClassVar[str] = ""

    def __init__(self, config: dict[str, str] | None = None) -> None:
        self._config = config or {}
        # Set by sync so a source can resolve and cache the people it mentions. None off the
        # sync path (CLI, tests), where a source resolves names itself without persisting.
        self.directory: PeopleDirectory | None = None

    @classmethod
    async def detect(cls) -> Detection:
        """Read what a local tool already knows. The default knows nothing."""
        return Detection(available=False, detail="")

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
    async def fetch(self) -> list[RawItem]: ...

    def detail(self) -> str:
        return ""

    async def check(self) -> None:
        """Raise if the source is unreachable or misconfigured. Backs /admin/sources/{id}/test."""
        if not self.is_configured():
            missing = [f.label for f in self.fields if f.required and not self.get(f.key)]
            raise SourceNotConfigured(f"Missing: {', '.join(missing)}")


class SourceNotConfigured(RuntimeError):
    pass
