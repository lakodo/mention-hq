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


class MentionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    source: Source
    label: str
    url: str | None
    context: str | None
    occurred_at: datetime
    triaged: bool


class MentionWithTasks(MentionOut):
    tasks: list[TaskRef] = []


class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    title: str
    bucket: str
    status: Status
    tags: list[str]
    unread: bool
    origin: str
    updated_at: datetime
    mentions: list[MentionOut]


class TaskPatch(BaseModel):
    bucket: str | None = None
    unread: bool | None = None
    status: Status | None = None
    title: str | None = None
    tags: list[str] | None = None


class TaskCreate(BaseModel):
    title: str
    bucket: str | None = None
    tags: list[str] = []


class AttachRequest(BaseModel):
    task_ids: list[str] = Field(min_length=1)


class CreateTaskFromMentionRequest(BaseModel):
    title: str
    bucket: str | None = None


class TriageRequest(BaseModel):
    triaged: bool = True


class BucketOut(BaseModel):
    name: str
    keywords: list[str]
    position: int
    count: int


class BucketCreate(BaseModel):
    name: str
    keywords: list[str] = []
    position: int | None = None


class BucketPatch(BaseModel):
    keywords: list[str] | None = None
    position: int | None = None


class ConfigFieldOut(BaseModel):
    key: str
    label: str
    kind: str
    required: bool
    placeholder: str
    help: str
    # For secrets this is a mask like "••••••••1234", never the value itself.
    value: str | None = None
    is_set: bool = False


class SourceStatusOut(BaseModel):
    id: str
    name: str
    description: str
    status: str  # "connected" | "error" | "unconfigured"
    detail: str
    last_checked_at: datetime | None
    error: str | None = None
    fields: list[ConfigFieldOut] = []


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


class AppSettingsOut(BaseModel):
    app_name: str
    secret_backend: str
    secret_backend_is_keychain: bool


class AppSettingsPatch(BaseModel):
    app_name: str | None = None


class SyncSourceResult(BaseModel):
    source: str
    mentions_fetched: int = 0
    tasks_added: int = 0
    tasks_updated: int = 0
    error: str | None = None


class SyncResult(BaseModel):
    sources_synced: list[str]
    tasks_added: int
    tasks_updated: int
    duration_seconds: float
    errors: list[str] = []
    results: list[SyncSourceResult] = []


class SyncRequest(BaseModel):
    source: str | None = None


class SyncLogSourceOut(BaseModel):
    source: str
    mentions_fetched: int = 0
    configured: bool = True
    error: str | None = None


class SyncLogOut(BaseModel):
    """One entry per sync run — task counts belong to the run, not to any one source."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    started_at: datetime
    finished_at: datetime | None
    sources: list[SyncLogSourceOut]
    mentions_fetched: int
    tasks_added: int
    tasks_updated: int
    duration_seconds: float
    error: str | None
