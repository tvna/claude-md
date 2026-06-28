#!/usr/bin/env python3
"""Shared shell line-continuation flattener for the shell/YAML-scanning gates.

Issue #2164 retrospective for PR #2163, repair (a). The first version of
``scripts/scan_ruff_format.py`` scanned physical lines, so a POSIX shell
backslash continuation (``uv run ruff \\`` then ``format scripts``) split
``ruff`` and ``format`` across two physical lines and slipped through the
single-line regex, leaving the documented "no gate surface may invoke ruff
format" invariant bypassable. Codex review on PR #2163 caught it; the fix added
a private ``_logical_lines`` flattener to that one gate.

The same bypass was latent in every sibling gate that matches a two-token shell
command on a single physical line: ``scan_workflow_pip`` (``pip install``),
``scan_workflow_gh_calls`` (``gh api``), and ``scan_workflow_unsigned_commit``
(``git push``) each split identically across a ``\\`` continuation. Rather than
re-implement (or re-miss) line handling per gate, the flattener lives here once
and every shell-scanning gate routes through it. This is the single source of
truth (CLAUDE.md section 3): a continuation bypass cannot recur in one gate
while another stays correct, and ``tests/test_shell_scan_continuation_contract.py``
asserts every importer of this module catches a continuation form, so a new
shell-scanning gate that forgets continuation handling fails loudly at author
test time.

Tested by ``tests/test_shell_lines.py``. Refs #2164, #2163, #2143, #2141.
"""

from __future__ import annotations


def flatten_shell_continuations(text: str) -> list[tuple[int, str]]:
    """Join shell backslash-continued physical lines into logical lines.

    Returns ``(start_lineno, joined_text)`` pairs, where *start_lineno* is the
    1-based number of the first physical line of the logical line. A physical
    line whose trailing token is a single backslash continues onto the next line
    (POSIX shell line continuation), so ``uv run ruff \\`` then ``format scripts``
    joins to ``uv run ruff format scripts`` and a two-token command split across
    the continuation is seen as one token run rather than slipping through a
    per-physical-line scan (Codex review on #2143).

    A trailing *doubled* ``\\\\`` is an escaped backslash, not a continuation, and
    ends the logical line. Each joined part is stripped, so the logical text is
    whitespace-normalised to single spaces at the join points.
    """
    out: list[tuple[int, str]] = []
    pending: list[str] = []
    start = 0
    for lineno, line in enumerate(text.splitlines(), start=1):
        stripped = line.rstrip()
        # A trailing odd backslash is a continuation; a doubled ``\\`` is an
        # escaped backslash and ends the logical line.
        if stripped.endswith("\\") and not stripped.endswith("\\\\"):
            if not pending:
                start = lineno
            pending.append(stripped[:-1])
            continue
        if pending:
            pending.append(line)
            out.append((start, " ".join(part.strip() for part in pending)))
            pending = []
        else:
            out.append((lineno, line))
    if pending:
        out.append((start, " ".join(part.strip() for part in pending)))
    return out
