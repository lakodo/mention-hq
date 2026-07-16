#!/usr/bin/env python3
"""Flag comments that narrate the project's history instead of describing the code.

This is the mechanically checkable half of the comment rules in CLAUDE.md. The other half
— whether a comment earns its place at all — is judgement, and every proxy for it flags
the wrong things: length lets a four-line essay on a one-line property through, and
"docstring longer than its function" flags precisely the docstrings that are pulling their
weight, since a short function with a subtle constraint is when you most need one.

So passing here means nothing was obviously wrong. It does not mean the comment is good.
"""

from __future__ import annotations

import ast
import re
import sys
import tokenize
from pathlib import Path

# Only phrases with no innocent reading. "no longer" and "for now" describe runtime state
# as often as they narrate a change ("a row that no longer exists"), and a check people
# argue with is a check people switch off.
HISTORY = re.compile(
    r"\b("
    r"previously|originally|formerly|"
    r"used to (be|do|call|live|have|return)|"
    r"now (does|uses|returns|lives|handles) .* instead|"
    r"as (discussed|requested|agreed)|"
    r"(changed|switched|renamed|moved) (this |it )?(to|from) (fix|address|make)|"
    r"instead of (the )?(old|previous|original)|"
    r"per (the )?review|review comment|addresses? feedback"
    r")\b",
    re.IGNORECASE,
)

DOCSTRING_OWNERS = (ast.AsyncFunctionDef, ast.ClassDef, ast.FunctionDef, ast.Module)


def check(path: Path) -> list[str]:
    problems: list[str] = []
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        return []  # ruff reports this properly

    for node in ast.walk(tree):
        if not isinstance(node, DOCSTRING_OWNERS):
            continue
        doc = ast.get_docstring(node)
        if doc and (match := HISTORY.search(doc)):
            problems.append(_report(path, getattr(node, "lineno", 1), "docstring", match.group(0)))

    with path.open("rb") as handle:
        for token in tokenize.tokenize(handle.readline):
            if token.type == tokenize.COMMENT and (match := HISTORY.search(token.string)):
                problems.append(_report(path, token.start[0], "comment", match.group(0)))

    return problems


def _report(path: Path, line: int, kind: str, phrase: str) -> str:
    return f"{path}:{line}: {kind} narrates history ({phrase!r}) — that belongs in the commit message"


def main(argv: list[str]) -> int:
    problems = [problem for arg in argv for problem in check(Path(arg))]
    for problem in problems:
        print(problem)
    if problems:
        print(f"\n{len(problems)} problem(s). A comment describes the code as it is; see CLAUDE.md.")
    return 1 if problems else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
