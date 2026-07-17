"""Pydantic request/response schemas — the contract the frontend codes against."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

Status = str  # "open" | "in_progress" | "merged" | "done"
Source = str  # "pr" | "issue" | "linear" | "slack" | "branch" | "todo" | "markdown" | "dust"


class TaskRef(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    bucket: str


class ItemPersonOut(BaseModel):
    kind: str
    value: str
    name: str
    role: str


class ItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: Source
    label: str
    url: str | None
    context: str | None
    occurred_at: datetime
    triaged: bool
    triage_reason: str | None = None
    triaged_at: datetime | None = None
    pr_status: str | None = None
    pr_review_requested: bool = False
    emoji: dict[str, str] = {}
    people: list[ItemPersonOut] = []


class LinkOut(BaseModel):
    """One item's attachment to one task, and who decided it."""

    model_config = ConfigDict(from_attributes=True)

    task: TaskRef
    # "proposed" (an engine's guess) | "confirmed" (you said yes) | "rejected" (you said no)
    state: str
    engine: str | None
    confidence: float
    reason: str | None


class ItemWithLinks(ItemOut):
    links: list[LinkOut] = []


class TaskMatchOut(BaseModel):
    """A brain-proposed match between an item and an existing task."""

    task: TaskRef
    confidence: float
    reason: str


class TriageRuleOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    sources: list[str]
    condition: str  # "starts_with" | "contains"
    value: str
    enabled: bool


class TriageRuleCreate(BaseModel):
    name: str = ""
    sources: list[str] = []  # source kinds, or empty for all
    condition: str
    value: str


class TriageRulePatch(BaseModel):
    enabled: bool | None = None


class TaskCandidateOut(BaseModel):
    """An item the engine proposed for this task but the user hasn't ruled on yet."""

    model_config = ConfigDict(from_attributes=True)

    item: ItemOut
    engine: str | None
    confidence: float
    reason: str | None


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    description: str | None = None
    bucket: str
    status: Status
    priority: int
    tags: list[str]
    unread: bool
    origin: str
    archived: bool
    next_action: str | None = None
    updated_at: datetime
    items: list[ItemOut]
    candidates: list[TaskCandidateOut] = []


class TaskPatch(BaseModel):
    bucket: str | None = None
    unread: bool | None = None
    status: Status | None = None
    priority: int | None = Field(default=None, ge=0, le=100)
    title: str | None = None
    description: str | None = None
    tags: list[str] | None = None
    archived: bool | None = None


class TaskCreate(BaseModel):
    title: str
    description: str | None = None
    bucket: str | None = None
    priority: int = Field(default=50, ge=0, le=100)
    tags: list[str] = []


class ConfirmRequest(BaseModel):
    task_ids: list[str] = Field(min_length=1)


class CreateTaskFromItemRequest(BaseModel):
    title: str
    bucket: str | None = None
    priority: int = Field(default=50, ge=0, le=100)


class BrainDumpRequest(BaseModel):
    text: str = Field(min_length=1)
    task_ids: list[str] = []


class TriageRequest(BaseModel):
    triaged: bool = True


class BucketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    name: str
    keywords: list[str]
    position: int
    count: int
    archived: bool = False


class BucketCreate(BaseModel):
    name: str
    keywords: list[str] = []
    position: int | None = None


class BucketPatch(BaseModel):
    keywords: list[str] | None = None
    position: int | None = None


class BucketArchive(BaseModel):
    cascade_tasks: bool = False


class ConfigFieldOut(BaseModel):
    key: str
    label: str
    kind: str
    required: bool
    placeholder: str
    help: str
    help_url: str = ""
    # For secrets this is a mask like "••••••••1234", never the value itself.
    value: str | None = None
    is_set: bool = False


class SourceKindOut(BaseModel):
    """A source you can add. Drives the Add-a-source picker."""

    kind: str
    name: str
    description: str
    setup: str = ""
    setup_url: str = ""
    # Paste-into-the-other-service config, when that service takes one.
    manifest: str = ""
    manifest_hint: str = ""
    detectable: bool = False
    needs_credentials: bool = False


class SourceCreate(BaseModel):
    kind: str
    name: str = ""


class SourcePatch(BaseModel):
    name: str | None = None
    position: int | None = None


class SourceStatusOut(BaseModel):
    """A source the user has added, and how it is doing."""

    id: str
    kind: str
    name: str
    position: int = 0
    description: str
    status: str  # "connected" | "error" | "unconfigured"
    detail: str
    last_checked_at: datetime | None
    error: str | None = None
    fields: list[ConfigFieldOut] = []
    setup: str = ""
    setup_url: str = ""
    manifest: str = ""
    manifest_hint: str = ""
    # Whether this source can read its own settings out of a local CLI.
    detectable: bool = False


class DetectionOut(BaseModel):
    """The result of reading a local CLI. Secrets are saved, never returned."""

    available: bool
    detail: str
    # Non-secret values that were filled in, and options for fields the tool can't decide.
    applied: dict[str, str] = {}
    choices: dict[str, list[str]] = {}
    source: SourceStatusOut | None = None


class SourceConfigUpdate(BaseModel):
    """Only the keys present are written. Send "" to clear one."""

    values: dict[str, str]


class AIStatusOut(BaseModel):
    available: bool
    # "keychain" | "environment" | "cli-login" | "none"
    source: str
    detail: str
    model: str


class AIKeyUpdate(BaseModel):
    """Send "" to clear the key and fall back to `ant auth login` / the environment."""

    api_key: str


class BucketSuggestionOut(BaseModel):
    bucket: str
    is_new: bool
    keywords: list[str]
    confidence: float
    reasoning: str


class NextActionOut(BaseModel):
    action: str
    confidence: float


class PersonIdentityOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    value: str
    label: str | None = None


class PersonIdentityIn(BaseModel):
    kind: str
    value: str
    label: str | None = None


class PersonOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    display_name: str
    email: str | None = None
    note: str | None = None
    identities: list[PersonIdentityOut] = []


class PersonCreate(BaseModel):
    display_name: str
    email: str | None = None
    note: str | None = None
    identities: list[PersonIdentityIn] = []


class PersonPatch(BaseModel):
    display_name: str | None = None
    email: str | None = None
    note: str | None = None


class PersonMerge(BaseModel):
    # The surviving person this one folds into.
    into: str


class AppSettingsOut(BaseModel):
    app_name: str
    auto_sync: bool
    secret_backend: str
    secret_backend_is_keychain: bool


class AppSettingsPatch(BaseModel):
    app_name: str | None = None
    auto_sync: bool | None = None


class BackupOut(BaseModel):
    filename: str
    path: str
    size_bytes: int
    created_at: datetime


class MatchStatusOut(BaseModel):
    running: bool
    total: int
    done: int
    remaining: int


class SyncSourceResult(BaseModel):
    source: str
    items_fetched: int = 0
    error: str | None = None


class SyncResult(BaseModel):
    sources_synced: list[str]
    items_added: int
    items_updated: int
    proposals: int
    tasks_updated: int
    duration_seconds: float
    errors: list[str] = []
    results: list[SyncSourceResult] = []


class SyncRequest(BaseModel):
    source: str | None = None


class SyncLogSourceOut(BaseModel):
    source: str
    kind: str = ""
    items_fetched: int = 0
    configured: bool = True
    error: str | None = None


class SyncLogOut(BaseModel):
    """One entry per sync run — task counts belong to the run, not to any one source."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: datetime
    finished_at: datetime | None
    sources: list[SyncLogSourceOut]
    items_fetched: int
    items_added: int
    items_updated: int
    proposals: int
    tasks_updated: int
    duration_seconds: float
    error: str | None
