"""SQLAlchemy ORM models.

The core idea: a **task** is a subject you need to handle. It is mentioned across many
**sources** — a PR, a Slack thread, a Linear issue, a local todo.

A mention can belong to **several** tasks, not one. A Slack thread arguing about both the
refund bug and the webhook retry is genuinely about both, and forcing it to pick loses
information. So tasks and mentions are many-to-many through `task_mentions`.

Links come from two places, and they must not fight:
  - sync recomputes automatic links every run (see services/grouping.py);
  - the user attaches and detaches by hand in the catch-up screen.

`link_overrides` records the user's *intent* permanently, and every sync replays it over
the freshly computed automatic links. That is why a manual attach survives a resync, and
why a detached mention doesn't silently come back.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
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

    SQLite has no timezone type: it stores what you give it and hands back a *naive*
    datetime. Sync compares stored timestamps against freshly-fetched aware ones, and
    naive-vs-aware comparison raises TypeError — so without this every second sync
    would crash. Normalising on the way in and out keeps that bug impossible rather
    than relying on every call site to remember.
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


class TaskMention(Base):
    """Materialised link. Rebuilt every sync from grouping + link_overrides."""

    __tablename__ = "task_mentions"

    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), primary_key=True)
    mention_id: Mapped[str] = mapped_column(ForeignKey("mentions.id", ondelete="CASCADE"), primary_key=True)
    # "auto" — inferred by grouping; "manual" — the user said so.
    linked_by: Mapped[str] = mapped_column(String, nullable=False, default="auto")
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())


class LinkOverride(Base):
    """A user decision about one mention/task pair, replayed over every future sync."""

    __tablename__ = "link_overrides"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    mention_id: Mapped[str] = mapped_column(String, nullable=False)
    task_id: Mapped[str] = mapped_column(String, nullable=False)
    # "attach" — force the link on; "detach" — force it off even if grouping infers it.
    action: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())

    __table_args__ = (UniqueConstraint("mention_id", "task_id", name="uq_link_override_pair"),)


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
    # "auto" tasks are derived from mentions and vanish when their mentions do.
    # "manual" tasks were created by the user and outlive their mentions.
    origin: Mapped[str] = mapped_column(String, nullable=False, default="auto")
    title_override: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    synced_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())

    mentions: Mapped[list[Mention]] = relationship(
        secondary="task_mentions",
        back_populates="tasks",
        lazy="selectin",
        order_by="Mention.occurred_at.desc()",
    )

    __table_args__ = (Index("ix_tasks_bucket", "bucket"),)


class Mention(Base):
    __tablename__ = "mentions"

    # Stable across syncs: "{source}:{external_id}", e.g. "pr:alan-eu/alan-apps#1201".
    id: Mapped[str] = mapped_column(String, primary_key=True)
    source: Mapped[str] = mapped_column(String, nullable=False, index=True)
    label: Mapped[str] = mapped_column(Text, nullable=False)
    url: Mapped[str | None] = mapped_column(Text)
    context: Mapped[str | None] = mapped_column(Text)
    occurred_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    # False until the user has dealt with it in the catch-up screen. Drives that inbox.
    triaged: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    first_seen_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False, server_default=func.now())
    extra: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    tasks: Mapped[list[Task]] = relationship(
        secondary="task_mentions", back_populates="mentions", lazy="selectin"
    )

    __table_args__ = (Index("ix_mentions_occurred_at", "occurred_at"),)


class Bucket(Base):
    """A topic column on the board.

    There are no built-in buckets: HQ cannot know what you work on, and guessing would fill
    the board with someone else's taxonomy. You create them in Admin; until then everything
    lands in the implicit "Uncategorized" bucket, which is not a row here.
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
    __tablename__ = "sync_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source: Mapped[str] = mapped_column(String, nullable=False)
    started_at: Mapped[datetime] = mapped_column(UTCDateTime, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(UTCDateTime)
    mentions_fetched: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tasks_added: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tasks_updated: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text)

    __table_args__ = (Index("ix_sync_log_started_at", "started_at"),)
