"""SQLAlchemy ORM models.

The vocabulary, used consistently across the codebase:

  Item   — one thing from one source: a PR, a Slack thread, a todo line, a branch.
  Task   — a subject you handle. Items attach to it.
  Bucket — a topic column on the board, grouping tasks.

An item can attach to several tasks: a chat thread that argues about two subjects is
about both, and making it pick one loses information.

`app/engine/` proposes links; it never decides. A proposal is a Link in the `proposed`
state, which the user confirms or rejects in catch-up.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    TypeDecorator,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class UTCDateTime(TypeDecorator):
    """A datetime column that is always timezone-aware UTC in Python.

    SQLite has no timezone type: it stores what it is given and returns a naive datetime.
    Sync compares stored timestamps against freshly-fetched aware ones, and comparing
    naive to aware raises TypeError. Normalising in both directions here keeps that
    impossible, rather than relying on every call site to remember.
    """

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value.astimezone(UTC)

    def process_result_value(self, value: datetime | None, dialect) -> datetime | None:
        if value is None:
            return None
        return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class Base(DeclarativeBase):
    pass


PROPOSED = "proposed"
CONFIRMED = "confirmed"
REJECTED = "rejected"


class Link(Base):
    """An item attached to a task, and how much we believe in it.

    The state records who decided:

      proposed  — an engine's guess. Rebuilt from scratch on every sync, so an engine is
                  free to change its mind. Shows on the board and lands in catch-up.
      confirmed — the user said yes. Sync never touches it.
      rejected  — the user said no.

    Rejections are kept as rows so an engine cannot re-propose a dismissed link: without
    them "no" would only hold until the next sync.
    """

    __tablename__ = "links"

    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    item_id: Mapped[str] = mapped_column(ForeignKey("items.id", ondelete="CASCADE"), primary_key=True)
    state: Mapped[str] = mapped_column(String, nullable=False, default=PROPOSED, index=True)
    # Which engine proposed it, and why — shown in catch-up so a proposal is arguable
    # rather than magic.
    engine: Mapped[str | None] = mapped_column(String)
    confidence: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    decided_at: Mapped[datetime | None] = mapped_column(UTCDateTime)

    task: Mapped[Task] = relationship(lazy="selectin", overlaps="links")
    item: Mapped[Item] = relationship(lazy="selectin", back_populates="links", overlaps="links")

    @property
    def is_user_decision(self) -> bool:
        return self.state in (CONFIRMED, REJECTED)


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    bucket: Mapped[str] = mapped_column(String, nullable=False, default="Uncategorized")
    # Set when the user picks a bucket by hand; sync must not clobber it.
    bucket_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    # 0 to 100, higher is more urgent; 50 is the neutral default so a new task doesn't jump
    # ahead of what you've already ranked.
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=50, server_default="50")
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    unread: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # "auto" tasks are derived from items and vanish when their items do.
    # "manual" tasks were created by the user and outlive their items.
    origin: Mapped[str] = mapped_column(String, nullable=False, default="auto")
    title_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Set to hide a task from the board and lists while keeping it and its items intact —
    # the alternative to deleting, which releases the items back to catch-up.
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime, nullable=True)
    # The brain's predicted next action, precomputed so the task screen shows it on open.
    # Recomputed when the task's items change; None until first computed.
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())

    links: Mapped[list[Link]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        primaryjoin="Task.id == Link.task_id",
    )

    __table_args__ = (Index("ix_tasks_bucket", "bucket"),)

    @property
    def items(self) -> list[Item]:
        """Items confirmed onto this task — a rejected or merely proposed link is not an attachment."""
        confirmed = [link for link in self.links if link.state == CONFIRMED]
        confirmed.sort(key=lambda link: link.item.occurred_at, reverse=True)
        return [link.item for link in confirmed]

    @property
    def candidates(self) -> list[Link]:
        """Proposed links the engine guessed but the user hasn't ruled on yet."""
        proposed = [link for link in self.links if link.state == PROPOSED]
        proposed.sort(key=lambda link: link.confidence, reverse=True)
        return proposed

    @property
    def archived(self) -> bool:
        return self.archived_at is not None


class SourceInstance(Base):
    """One connected source: a GitHub account, a Slack workspace, a folder of todos.

    A kind ("github") can be connected more than once, because people have a work account
    and a personal one. Config and credentials are keyed by this row's id, not by kind, so
    two connections of the same kind never see each other's settings.
    """

    __tablename__ = "source_instances"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())


class Item(Base):
    """One thing from one source."""

    __tablename__ = "items"

    # Stable across syncs: "{source}:{external_id}".
    id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Which connection fetched it. Nullable because a connection can be deleted while its
    # items are still attached to tasks.
    instance_id: Mapped[str | None] = mapped_column(String, index=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    context: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    # False until you've ruled on this item in catch-up. Drives that inbox.
    triaged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    # How it left the inbox: "Skipped", "Rule: <name>", or None (still in the inbox, or filed
    # onto a task rather than skipped). Read by the skipped view.
    triage_reason: Mapped[str | None] = mapped_column(String)
    triaged_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # Set when the auto-matcher has attempted a brain match for this item. None means it
    # has never been tried; once set, the auto-matcher skips it so the brain isn't called
    # again on every sync. Cleared by "Match all" to force a fresh attempt.
    matched_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    links: Mapped[list[Link]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        primaryjoin="Item.id == Link.item_id",
        back_populates="item",
    )

    __table_args__ = (Index("ix_items_occurred_at", "occurred_at"),)

    @property
    def tasks(self) -> list[Task]:
        return [link.task for link in self.links if link.state != REJECTED]

    @property
    def pr_status(self) -> str | None:
        return (self.extra or {}).get("pr_status")

    @property
    def pr_review_requested(self) -> bool:
        return bool((self.extra or {}).get("pr_review_requested"))

    @property
    def emoji(self) -> dict[str, str]:
        """Custom emoji shortcodes used in the label, mapped to their image URL."""
        return (self.extra or {}).get("emoji") or {}


class Bucket(Base):
    """A topic column on the board, grouping tasks.

    Buckets are user-defined: HQ cannot know what someone works on, and a wrong guess fills
    the board with a taxonomy that isn't theirs. A task matching no bucket falls to
    "Uncategorized", which is implicit and has no row here.
    """

    __tablename__ = "buckets"

    name: Mapped[str] = mapped_column(String, primary_key=True)
    # Matched case-insensitively against a task's title and tags. First bucket wins.
    keywords: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    archived_at: Mapped[datetime | None] = mapped_column(UTCDateTime)


class AppConfig(Base):
    """Non-secret, user-editable configuration. Secrets go to the OS keychain, never here."""

    __tablename__ = "app_config"

    namespace: Mapped[str] = mapped_column(String, primary_key=True)
    key: Mapped[str] = mapped_column(String, primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)


class SyncLog(Base):
    """One row per sync run, not per source.

    Grouping is global — a task can be built from a GitHub PR *and* a Slack thread — so
    "how many tasks did Slack add" has no answer. Task counts belong to the run; only
    the item count and the error are per-source, and those live in `sources`.
    """

    __tablename__ = "sync_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    # [{"source": "github", "items_fetched": 3, "error": null}, ...]
    sources: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)
    items_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_added: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    proposals: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tasks_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    duration_seconds: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_sync_log_started_at", "started_at"),)


class Person(Base):
    """A human, and the handles they go by across sources.

    One colleague may be a Slack id, a GitHub login and an email at once. HQ keeps them as
    one Person so a name learned from one source answers for all, and no source is treated
    as the owner — they only contribute identities. Merging folds duplicates together.
    """

    __tablename__ = "people"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    email: Mapped[str | None] = mapped_column(String)
    note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())

    identities: Mapped[list[PersonIdentity]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        back_populates="person",
        order_by="PersonIdentity.kind",
    )


class PersonIdentity(Base):
    """One handle a person has on one source: a Slack user id, a GitHub login, an email.

    (kind, value) is unique — a given Slack id names exactly one person — which is also what
    lets a source ask "who is this id?" and get a stable answer without asking the source
    again.
    """

    __tablename__ = "person_identities"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    person_id: Mapped[str] = mapped_column(
        ForeignKey("people.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # "slack" | "github" | "linear" | "email" | ... — the source kind, or a plain contact kind.
    kind: Mapped[str] = mapped_column(String, nullable=False)
    # The id/handle/address on that source.
    value: Mapped[str] = mapped_column(String, nullable=False)
    # What the source called them when captured, kept for display even before a name is set.
    label: Mapped[str | None] = mapped_column(String)

    person: Mapped[Person] = relationship(back_populates="identities")

    __table_args__ = (UniqueConstraint("kind", "value", name="uq_person_identity_kind_value"),)


class TriageRule(Base):
    """A standing "skip this" rule, so noise never reaches the catch-up inbox.

    An incoming item that matches an enabled rule is auto-skipped (triaged, with the rule
    named as its reason) before it can pile up — the app-shipped equivalent of a mail filter.
    Rules only skip; they never attach an item to a task.
    """

    __tablename__ = "triage_rules"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    # Source kinds this fires on ("slack", "pr", …). Empty = every source.
    sources: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    # "starts_with" | "contains" — how `value` is tested against an item's label.
    condition: Mapped[str] = mapped_column(String, nullable=False)
    value: Mapped[str] = mapped_column(String, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
