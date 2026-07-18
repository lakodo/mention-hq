"""Which engines run for which source, and how their proposals combine.

Engines are mapped per source because sources differ in what they can honestly claim. A
tracker issue names a subject; chat text only ever points at one, and is chatty enough
that fuzzy-matching it against titles yields confident nonsense.

A source absent from the map proposes nothing.
"""

from __future__ import annotations

from app.engine.base import Engine, NullEngine, Proposal, TaskView
from app.engine.keys import KeyEngine
from app.engine.similarity import TitleSimilarityEngine
from app.sources.base import RawItem

_KEYS = KeyEngine()
_TITLE = TitleSimilarityEngine()
_NULL = NullEngine()

ENGINES_BY_SOURCE: dict[str, list[Engine]] = {
    "pr": [_KEYS, _TITLE],
    "issue": [_KEYS, _TITLE],
    "linear": [_KEYS, _TITLE],
    "branch": [_KEYS, _TITLE],
    "markdown": [_KEYS, _TITLE],
    "notion": [_KEYS, _TITLE],
    "notion_mcp": [_KEYS, _TITLE],
    "todo": [_TITLE],
    "slack": [_KEYS],
    "dust": [_KEYS],
}


def engines_for(source: str) -> list[Engine]:
    return ENGINES_BY_SOURCE.get(source, [_NULL])


def propose(item: RawItem, tasks: list[TaskView]) -> list[tuple[Proposal, Engine]]:
    """Run every engine for this item's source and keep the best proposal per task.

    Two engines proposing the same task isn't disagreement, it's corroboration — but
    confidence isn't additive, so the strongest claim simply wins rather than compounding
    into false certainty.
    """
    best: dict[str, tuple[Proposal, Engine]] = {}
    for engine in engines_for(item.source):
        for proposal in engine.propose(item, tasks):
            current = best.get(proposal.task_id)
            if current is None or proposal.confidence > current[0].confidence:
                best[proposal.task_id] = (proposal, engine)
    return sorted(best.values(), key=lambda pair: pair[0].confidence, reverse=True)
