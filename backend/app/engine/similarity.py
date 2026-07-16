"""Fuzzy title matching, for when nothing names a ticket.

Titles for the same subject rarely match character-for-character: they use different
words in a different order, and carry prefixes that say nothing about the subject. Plain
Levenshtein scores such pairs poorly, because the edit distance is dominated by the
prefix and the reordering rather than the words that carry the meaning.

So scoring runs over the words that survive normalisation, using token_set_ratio: a
Levenshtein ratio over sorted token sets, which is order-insensitive by construction.
"""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from app.engine.base import Engine, Proposal, TaskView
from app.sources.base import RawItem

_TYPES = "feat|fix|chore|docs|refactor|test|perf|ci|build|style"
# The commit type says nothing about the subject, and leaving it in makes unrelated PRs
# look alike ("feat(x)" vs "feat(y)"). The scope does name the subject, so it stays.
_PREFIX_SCOPED = re.compile(rf"^(?:{_TYPES})\(([^)]*)\):\s*", re.I)
_PREFIX_BARE = re.compile(rf"^(?:{_TYPES}):\s*", re.I)
# A leading owner segment in a branch name identifies a person, not a subject.
_BRANCH_OWNER = re.compile(r"^[\w.-]+/")
_NOISE = re.compile(r"[^\w\s]")

# Words so common in this domain they create false matches on their own.
_STOPWORDS = frozenset({"the", "a", "an", "to", "for", "of", "on", "in", "and", "or", "fix", "add", "update"})

# A title lookalike is a decent guess, never a certainty, and it must score below the key
# engine so an explicit ticket reference always wins.
MAX_CONFIDENCE = 0.8

# On real titles the two populations separate cleanly: genuine pairs score 0.79-0.86,
# unrelated ones 0.37-0.56. 0.75 sits in that gap with margin on both sides.
SIMILARITY_THRESHOLD = 0.75


class TitleSimilarityEngine(Engine):
    id = "title-similarity"
    min_confidence = SIMILARITY_THRESHOLD * MAX_CONFIDENCE

    def propose(self, item: RawItem, tasks: list[TaskView]) -> list[Proposal]:
        subject = normalise(item.task_title())
        if len(subject.split()) < 2:
            # One word is not enough to argue from.
            return []

        proposals = []
        for task in tasks:
            score = fuzz.token_set_ratio(subject, normalise(task.title)) / 100
            if score < SIMILARITY_THRESHOLD:
                continue
            proposals.append(
                Proposal(
                    task_id=task.id,
                    confidence=round(score * MAX_CONFIDENCE, 3),
                    reason=f'Title looks like "{task.title}" ({round(score * 100)}% similar)',
                )
            )
        return self._keep(proposals)


def normalise(text: str) -> str:
    text = _PREFIX_SCOPED.sub(r"\1 ", text.strip())
    text = _PREFIX_BARE.sub("", text)
    text = _BRANCH_OWNER.sub("", text)
    text = _NOISE.sub(" ", text.lower())
    return " ".join(w for w in text.split() if w not in _STOPWORDS)
