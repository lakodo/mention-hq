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
    bucket: Mapped[str] = mapped_column(String, nullable=False, default="Uncategorized")
    # Set when the user picks a bucket by hand; sync must not clobber it.
    bucket_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="open")
    tags: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    unread: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # "auto" tasks are derived from items and vanish when their items do.
    # "manual" tasks were created by the user and outlive their items.
    origin: Mapped[str] = mapped_column(String, nullable=False, default="auto")
    title_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
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
        """Items actually on this task — a rejected link is not an attachment."""
        attached = [link for link in self.links if link.state != REJECTED]
        attached.sort(key=lambda link: link.item.occurred_at, reverse=True)
        return [link.item for link in attached]


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
