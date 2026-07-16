"""Matching on explicit ticket references.

An issue key written into a branch name or a PR body is a deliberate act by a person, not
an inference, which is why this is the only engine that proposes at high confidence.
"""

from __future__ import annotations

from app.engine.base import Engine, Proposal
from app.models import Task
from app.sources.base import RawItem


class KeyEngine(Engine):
    id = "keys"
    min_confidence = 0.5

    def propose(self, item: RawItem, tasks: list[Task]) -> list[Proposal]:
        item_keys = item.identity_keys | item.reference_keys
        if not item_keys:
            return []

        proposals = []
        for task in tasks:
            task_keys = _keys_of(task)
            shared = item_keys & task_keys
            if not shared:
                continue

            key = sorted(shared)[0]
            # Both naming the same ticket is near-certain. One merely citing it is strong
            # but not the same claim: a PR can reference a ticket in passing.
            identity_match = bool(item.identity_keys & _identity_keys_of(task))
            proposals.append(
                Proposal(
                    task_id=task.id,
                    confidence=1.0 if identity_match else 0.9,
                    reason=(
                        f"Both refer to {key}"
                        if identity_match
                        else f"This {item.source} references {key}, which is on this task"
                    ),
                )
            )
        return self._keep(proposals)


def _keys_of(task: Task) -> set[str]:
    keys: set[str] = set()
    for item in task.items:
        keys |= set(item.extra.get("identity_keys", []))
        keys |= set(item.extra.get("reference_keys", []))
    return keys


def _identity_keys_of(task: Task) -> set[str]:
    keys: set[str] = set()
    for item in task.items:
        keys |= set(item.extra.get("identity_keys", []))
    return keys
