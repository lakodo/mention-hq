#!/usr/bin/env python3
"""Reject assistant-attribution trailers in a commit message.

The message is the author's own. A "Co-Authored-By: Claude" or "Generated with Claude"
line is noise nobody wants in the history, and CLAUDE.md already forbids it — this makes
the rule mechanical instead of a matter of anyone remembering.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

BANNED = re.compile(
    r"co-authored-by:\s*(claude|anthropic)|generated with \[?claude|🤖 generated",
    re.IGNORECASE,
)


def main() -> int:
    message = Path(sys.argv[1]).read_text(encoding="utf-8")
    offending = [line for line in message.splitlines() if BANNED.search(line)]
    if not offending:
        return 0

    print("commit message carries an assistant-attribution trailer — remove it:")
    for line in offending:
        print(f"    {line.strip()}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
