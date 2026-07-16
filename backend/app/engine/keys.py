"""Matching on explicit ticket references.

An issue key written into a branch name or a PR body is a deliberate act by a person, not
an inference, which is why this is the only engine that proposes at high confidence.
"""

from __future__ import annotations

from app.engine.base import Engine, Proposal, TaskView
from app.sources.base import RawItem


class KeyEngine(Engine):
    id = "keys"
    min_confidence = 0.5

    def propose(self, item: RawItem, tasks: list[TaskView]) -> list[Proposal]:
        item_keys = item.identity_keys | item.reference_keys
        if not item_keys:
            return []

        proposals = []
        for task in tasks:
            shared = item_keys & task.keys
            if not shared:
                continue

            key = sorted(shared)[0]
            # Both naming the same ticket is near-certain. One merely citing it is strong
            # but not the same claim: a PR can reference a ticket in passing.
            names_the_same_thing = bool(item.identity_keys & task.identity_keys)
            proposals.append(
                Proposal(
                    task_id=task.id,
                    confidence=1.0 if names_the_same_thing else 0.9,
                    reason=(
                        f"Both refer to {key}"
                        if names_the_same_thing
                        else f"This {item.source} references {key}, which is on this task"
                    ),
                )
            )
        return self._keep(proposals)
