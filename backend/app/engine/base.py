"""What an engine is.

An engine proposes where an incoming item might belong; it never decides. A proposal
becomes a Link in the `proposed` state, which the user confirms or rejects in catch-up.

Proposing nothing is the default because a bad guess costs more than a missing one: a
wrong attachment hides work on a task nobody is looking at, and only gets undone if
someone notices it.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.models import Task
from app.sources.base import RawItem


@dataclass(frozen=True)
class Proposal:
    task_id: str
    confidence: float  # 0..1
    reason: str  # shown to the user — must read as an argument, not a score

    def __post_init__(self) -> None:
        if not 0 <= self.confidence <= 1:
            raise ValueError(f"confidence must be in 0..1, got {self.confidence}")


class Engine:
    id: str = "null"
    # Below this, a proposal isn't worth the user's attention.
    min_confidence: float = 0.5

    def propose(self, item: RawItem, tasks: list[Task]) -> list[Proposal]:
        return []

    def _keep(self, proposals: list[Proposal]) -> list[Proposal]:
        return sorted(
            (p for p in proposals if p.confidence >= self.min_confidence),
            key=lambda p: p.confidence,
            reverse=True,
        )


class NullEngine(Engine):
    """What a source gets when the registry has no entry for it."""

    id = "null"
