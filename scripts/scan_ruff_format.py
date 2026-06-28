#!/usr/bin/env python3
"""Keep ``ruff format`` out of the repository's gate surfaces.

Issue #2143 retrospective for PR #2141, repair (a). After resolving a
cherry-pick conflict an agent ran ``uv run ruff format`` on a test file, which
reflowed 708 unrelated lines and ballooned an otherwise 35-line diff. CI never
runs ``ruff format`` / ``ruff format --check``; the only ruff gate is
``uv run ruff check scripts tests`` (``.github/workflows/verify-agents.yml``),
and ``main`` itself is intentionally not ``ruff format`` clean. Reformatting
files the gate set does not format-check buys no CI benefit and only widens the
change surface (CLAUDE.md section 5).

The lesson is encoded as a durable invariant rather than agent memory
(CLAUDE.md section 3): no gate surface may invoke ``ruff format``. This keeps
the documented contract ("CI enforces ``ruff check`` only; ``ruff format`` is
not a gate") inspectable, so a future change cannot silently add a
``ruff format`` gate (which would change that contract) without this gate
firing and forcing the decision to be made deliberately.

Two complementary surfaces are scanned:

* Text surfaces (workflow YAML, the ``.githooks`` hooks, and
  ``.pre-commit-config.yaml``): a regex over non-comment lines flags any
  ``ruff format`` invocation. A line carrying :data:`ACK_MARKER` is exempt for
  a deliberate, reviewed future adoption (mirrors ``scan_workflow_pip.py``).
* The preflight manifest (``scripts/preflight_steps.STEPS``): each step's
  ``argv`` is a tuple, so a text regex cannot see ``ruff format`` split across
  ``("ruff", "format")``; the argv tuples are inspected directly for that
  consecutive subsequence.

Contract:
- Inputs: the ``verify`` subcommand and an optional ``--repo-root`` (default:
  the repository root inferred from this file). No environment input.
- Outputs: ``::error file=<path>[,line=<n>]::`` annotations on stderr for each
  hit; an ``OK:`` line on success.
- Exit codes: 0 when no gate surface invokes ``ruff format``; 1 on any hit.
- Failure policy: fails loud (exit 1) on any violation per CLAUDE.md section 4;
  a missing scanned file is simply skipped (a surface that does not exist
  cannot carry a violation).

Invoked from ``.github/workflows/verify-agents.yml`` (lint-scripts-static) and
mirrored as a ``scripts/preflight_all.py`` step. Tested by
``tests/test_scan_ruff_format.py``. Refs #2143, #2141, #2065.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Lines carrying this marker bypass the scan, for a deliberate and reviewed
# future adoption of a ruff-format gate. Mirrors scan_workflow_pip.ACK_MARKER.
ACK_MARKER = "<!-- ruff-format-ack -->"

# Gate-surface text files scanned for a ``ruff format`` invocation, relative to
# the repository root. Workflow YAML is globbed; the rest are named explicitly.
_HOOK_AND_CONFIG_FILES = (
    ".githooks/pre-commit",
    ".githooks/pre-push",
    ".pre-commit-config.yaml",
)
_WORKFLOW_SUBDIR = ".github/workflows"

# Matches a ``ruff format`` invocation in shell / YAML text. ``\bruff\s+format\b``
# tolerates ``uv run ruff format`` and extra spacing; ``ruff check`` and tokens
# like ``reformat`` do not match.
_RUFF_FORMAT = re.compile(r"\bruff\s+format\b")

# Matches a pure comment line (first non-whitespace char is ``#``), skipped so
# in-file documentation may quote the forbidden pattern without self-tripping.
_COMMENT_LINE = re.compile(r"^\s*#")

# Matches a YAML ``name:`` label line (a step / hook description, optionally a
# list item). A label never executes, so a step *described* as e.g. "Assert no
# ruff format ..." is not an invocation and must not trip the gate.
_LABEL_LINE = re.compile(r"^\s*(?:-\s+)?name:\s")


def scan_line(line: str) -> bool:
    """Return True if *line* invokes ``ruff format`` and is not exempt.

    Pure-comment lines, YAML ``name:`` label lines, and lines carrying
    :data:`ACK_MARKER` are treated as explicitly allowed and return False.
    """
    if ACK_MARKER in line:
        return False
    if _COMMENT_LINE.match(line) or _LABEL_LINE.match(line):
        return False
    return _RUFF_FORMAT.search(line) is not None


def _logical_lines(text: str) -> list[tuple[int, str]]:
    """Join shell backslash-continued physical lines into logical lines.

    Returns ``(start_lineno, joined_text)`` pairs, where *start_lineno* is the
    1-based number of the first physical line of the logical line. A physical
    line whose trailing token is a single backslash continues onto the next
    line (POSIX shell line continuation), so ``uv run ruff \\`` then
    ``format scripts`` joins to ``uv run ruff format scripts`` and the
    ``ruff format`` invocation is seen as one token run rather than slipping
    through the per-physical-line scan (Codex review on #2143).
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


def scan_text(text: str) -> list[int]:
    """Return 1-based start line numbers of logical lines invoking ``ruff format``.

    Shell line continuations are flattened first (see :func:`_logical_lines`)
    so a ``ruff format`` split across a ``\\`` continuation is still caught.
    """
    return [lineno for lineno, logical in _logical_lines(text) if scan_line(logical)]


def _iter_text_surfaces(repo_root: Path) -> list[Path]:
    """Return existing gate-surface text files under *repo_root*, sorted.

    Workflow YAML under ``.github/workflows`` plus the named hook and
    pre-commit config files. Absent files are skipped.
    """
    paths: list[Path] = []
    workflow_dir = repo_root / _WORKFLOW_SUBDIR
    if workflow_dir.exists():
        paths.extend(p for p in sorted(workflow_dir.rglob("*")) if p.is_file() and p.suffix in (".yml", ".yaml"))
    for rel in _HOOK_AND_CONFIG_FILES:
        candidate = repo_root / rel
        if candidate.is_file():
            paths.append(candidate)
    return paths


def find_text_violations(repo_root: Path) -> list[tuple[Path, int]]:
    """Return ``(relative_path, line_number)`` for every text-surface hit."""
    violations: list[tuple[Path, int]] = []
    for path in _iter_text_surfaces(repo_root):
        rel = path.relative_to(repo_root)
        for lineno in scan_text(path.read_text(encoding="utf-8", errors="ignore")):
            violations.append((rel, lineno))
    return violations


def find_manifest_violations() -> list[str]:
    """Return preflight step names whose argv invokes ``ruff format``.

    The argv is a tuple, so a text regex cannot see ``ruff format`` split as
    ``("ruff", "format")``; the consecutive subsequence is checked directly.
    Returns an empty list when the manifest cannot be imported (the text
    surfaces remain covered; a missing manifest is not a violation).
    """
    try:
        from preflight_steps import STEPS
    except ImportError:
        return []
    return [
        step.name
        for step in STEPS
        if any(a == "ruff" and b == "format" for a, b in zip(step.argv, step.argv[1:], strict=False))
    ]


def _cmd_verify(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    text_violations = find_text_violations(repo_root)
    manifest_violations = find_manifest_violations()

    for rel, lineno in text_violations:
        print(
            f"::error file={rel},line={lineno}::"
            f"'ruff format' invoked on a gate surface; CI enforces 'ruff check' "
            f"only and 'ruff format' is intentionally not a gate (running it just "
            f"widens the diff, CLAUDE.md section 5). Append '{ACK_MARKER}' to this "
            f"line if a ruff-format gate is being adopted deliberately. Refs #2143.",
            file=sys.stderr,
        )
    for name in manifest_violations:
        print(
            f"::error::preflight step '{name}' invokes 'ruff format'; the gate set "
            f"enforces 'ruff check' only (CLAUDE.md section 5). Refs #2143.",
            file=sys.stderr,
        )

    total = len(text_violations) + len(manifest_violations)
    if total:
        print(f"FAIL: {total} 'ruff format' invocation(s) on gate surfaces.", file=sys.stderr)
        return 1
    print("OK: no 'ruff format' on gate surfaces; CI enforces 'ruff check' only.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_verify = sub.add_parser("verify", help="Fail if any gate surface invokes 'ruff format'.")
    p_verify.add_argument("--repo-root", default=str(REPO_ROOT))
    p_verify.set_defaults(func=_cmd_verify)
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
