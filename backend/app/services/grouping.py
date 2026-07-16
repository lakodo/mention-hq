"""Merge raw mentions into tasks.

Two mentions belong to the same task when they share a key: either both name the same
thing (a Linear issue and a branch both carrying "PAY-88"), or one references the other
(a Slack message linking a PR URL). Merging is transitive — PR->issue and issue->slack
puts all three on one task — so this is a union-find over the key space.

A mention that shares no key with anything becomes a task of its own. That is the common
case for standalone todos, and it is the right default: over-merging unrelated subjects is
far more confusing than leaving them apart.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.sources.base import STATUS_PRIORITY, TITLE_PRIORITY, RawMention


class _UnionFind:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def add(self, key: str) -> None:
        self._parent.setdefault(key, key)

    def find(self, key: str) -> str:
        self.add(key)
        root = key
        while self._parent[root] != root:
            root = self._parent[root]
        while self._parent[key] != root:
            self._parent[key], key = root, self._parent[key]
        return root

    def union(self, a: str, b: str) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self._parent[root_b] = root_a


@dataclass
class GroupedTask:
    id: str
    title: str
    status: str
    tags: list[str]
    mentions: list[RawMention]

    @property
    def updated_at(self):
        return max(m.occurred_at for m in self.mentions)


def group_mentions(mentions: list[RawMention]) -> list[GroupedTask]:
    uf = _UnionFind()

    owner_of_key: dict[str, str] = {}
    for mention in mentions:
        uf.add(mention.id)
        for key in mention.identity_keys:
            # Two mentions claiming the same identity key are the same subject.
            if key in owner_of_key:
                uf.union(owner_of_key[key], mention.id)
            else:
                owner_of_key[key] = mention.id

    for mention in mentions:
        for key in mention.reference_keys:
            owner = owner_of_key.get(key)
            if owner is not None:
                uf.union(owner, mention.id)

    clusters: dict[str, list[RawMention]] = {}
    for mention in mentions:
        clusters.setdefault(uf.find(mention.id), []).append(mention)

    return [_build_task(members) for members in clusters.values()]


def _build_task(members: list[RawMention]) -> GroupedTask:
    members.sort(key=lambda m: m.occurred_at, reverse=True)
    lead = min(members, key=lambda m: _rank(TITLE_PRIORITY, m.source))

    statuses = [m.status for m in members if m.status]
    status = min(statuses, key=lambda s: _rank(STATUS_PRIORITY, s)) if statuses else "open"

    tags = sorted({tag for m in members for tag in m.tags})

    return GroupedTask(id=lead.id, title=lead.task_title(), status=status, tags=tags, mentions=members)


def _rank(order: list[str], value: str) -> int:
    try:
        return order.index(value)
    except ValueError:
        return len(order)
