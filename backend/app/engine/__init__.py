"""Attachment engines: they propose where an item belongs, they never decide.

See `base.py` for the contract and `registry.py` for which engines run per source.
"""

from __future__ import annotations

from app.engine.base import Engine, NullEngine, Proposal
from app.engine.keys import KeyEngine
from app.engine.registry import ENGINES_BY_SOURCE, engines_for, propose
from app.engine.similarity import TitleSimilarityEngine

__all__ = [
    "ENGINES_BY_SOURCE",
    "Engine",
    "KeyEngine",
    "NullEngine",
    "Proposal",
    "TitleSimilarityEngine",
    "engines_for",
    "propose",
]
