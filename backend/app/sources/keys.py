"""Extraction of the keys that let grouping link mentions across sources.

Two kinds of key matter in practice:
  - Linear-style issue refs ("PAY-88"), which show up in branch names, PR titles and Slack.
  - GitHub PR/issue refs, both as URLs and as "#1201" shorthand.
"""

from __future__ import annotations

import re

# Deliberately requires 2+ letters: avoids matching "A-1" or a bare "-88" in prose.
LINEAR_KEY_RE = re.compile(r"\b([A-Z]{2,}-\d+)\b")
GITHUB_URL_RE = re.compile(r"github\.com/([\w.-]+/[\w.-]+)/(?:pull|issues)/(\d+)")
GITHUB_SHORT_RE = re.compile(r"(?:^|\s)#(\d{1,6})\b")


def linear_keys(*texts: str | None) -> set[str]:
    return {m.group(1) for text in texts if text for m in LINEAR_KEY_RE.finditer(text)}


def github_keys(*texts: str | None, default_repo: str | None = None) -> set[str]:
    keys: set[str] = set()
    for text in texts:
        if not text:
            continue
        for match in GITHUB_URL_RE.finditer(text):
            keys.add(f"gh:{match.group(1)}#{match.group(2)}")
        if default_repo:
            for match in GITHUB_SHORT_RE.finditer(text):
                keys.add(f"gh:{default_repo}#{match.group(1)}")
    return keys


def github_key(repo: str, number: int | str) -> str:
    return f"gh:{repo}#{number}"


def all_reference_keys(*texts: str | None, default_repo: str | None = None) -> set[str]:
    return linear_keys(*texts) | github_keys(*texts, default_repo=default_repo)
