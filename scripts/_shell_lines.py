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


def _continues(line: str) -> bool:
    """Return True if *line* ends with a POSIX shell line continuation.

    A line continues onto the next one iff its final character is a backslash
    that escapes the newline. Three rules, matching real ``sh``/``bash``:

    * The backslash must be the actual last character. Trailing whitespace after
      it (``cmd \\`` then a space) escapes the *space*, not the newline, so the
      line does not continue. Hence the raw line is inspected, not an rstripped
      copy.
    * The run of trailing backslashes must be *odd*: an even run is escaped
      literal backslashes with nothing left to escape the newline (``echo \\\\``
      ends the line), while an odd run leaves one backslash escaping the newline.
    * A ``#`` comment never continues: the shell ends the comment at the newline
      and a trailing backslash inside it is a literal character (verified: ``#
      x \\`` then ``cmd`` runs ``cmd``). Joining the next line into the comment
      would let a gate's comment-skip swallow a real command (issue #2164).
    """
    if line.lstrip().startswith("#"):
        return False
    trailing = 0
    for char in reversed(line):
        if char == "\\":
            trailing += 1
        else:
            break
    return trailing % 2 == 1


def flatten_shell_continuations(text: str) -> list[tuple[int, str]]:
    """Join shell backslash-continued physical lines into logical lines.

    Returns ``(start_lineno, joined_text)`` pairs, where *start_lineno* is the
    1-based number of the first physical line of the logical line. A physical
    line that ends in a POSIX shell line continuation (see :func:`_continues`)
    is joined onto the next, so ``uv run ruff \\`` then ``format scripts`` joins
    to ``uv run ruff format scripts`` and a two-token command split across the
    continuation is seen as one token run rather than slipping through a
    per-physical-line scan (Codex review on #2143). Each joined part is stripped,
    so the logical text is whitespace-normalised to single spaces at the joins.
    """
    out: list[tuple[int, str]] = []
    pending: list[str] = []
    start = 0
    for lineno, line in enumerate(text.splitlines(), start=1):
        if _continues(line):
            if not pending:
                start = lineno
            # Drop the single backslash that escapes the newline; any preceding
            # backslashes in an odd run are literal and kept.
            pending.append(line[:-1])
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
