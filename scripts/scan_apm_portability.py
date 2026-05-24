#!/usr/bin/env python3
"""Verify APM agent-rule artifacts do not contain repo-local references.

Issue #230 retrospective for PR #229: repo-local script and metadata
references leaked into the compiled ``CLAUDE.md`` / ``AGENTS.md``, which
are intended to be referenced standalone from downstream projects. This
script is the deterministic gate the PR #229 repair loop identified as
missing.

Invoked from ``.github/workflows/verify-apm-portability.yml`` as
``python3 scripts/scan_apm_portability.py verify --path <file> ...``.

The contract is:

* Each ``--path`` is a file to scan. Typical inputs are
  ``.apm/instructions/master.instructions.md``, ``CLAUDE.md``, and
  ``AGENTS.md`` (defense in depth: scan source and both compiled
  outputs).
* Each line is scanned for the forbidden literal substrings in
  :data:`FORBIDDEN_TOKENS`. Matches are case-sensitive.
* Lines containing :data:`ACK_MARKER` are skipped. This mirrors the
  ``ACK_MARKER`` escape hatch in ``scripts/scan_non_ascii.py`` for the
  rare case a normative downstream rule must reference a repo-local
  artifact by name.
* Exit 0 when every scanned file is clean; exit 1 on any violation; the
  argparse layer returns 2 when no ``--path`` was supplied. Each hit
  emits ``::error file=<path>,line=<n>::...`` on stderr so the GitHub
  Actions UI surfaces individual violations.

Tested by ``tests/test_scan_apm_portability.py``. Refs #230.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterable
from pathlib import Path

# Lines containing this marker bypass the scan. Mirrors the precedent
# set by ``scripts/scan_non_ascii.py`` ACK_MARKER.
ACK_MARKER = "<!-- portability-ack -->"

# Literal substrings forbidden in scanned files. Each is chosen to avoid
# benign English words: ``scripts/`` requires the trailing slash so the
# word "scripted" does not match; ``.github/`` requires the trailing
# slash so ``github.com`` URLs do not match.
FORBIDDEN_TOKENS: tuple[str, ...] = (
    "scripts/",
    ".github/",
    "CODEOWNERS",
    "mcp__github__",
    "plan_language_context.py",
    "preflight_non_ascii.py",
    "owners.yaml",
)


def scan_line(line: str) -> list[str]:
    """Return the forbidden tokens present in *line*.

    Lines carrying :data:`ACK_MARKER` are treated as explicitly allowed
    and return an empty list.
    """
    if ACK_MARKER in line:
        return []
    return [token for token in FORBIDDEN_TOKENS if token in line]


def scan_text(text: str) -> list[tuple[int, str]]:
    """Return ``(line_number, token)`` for every violation in *text*.

    Line numbers are 1-based to match GitHub Actions ``::error file=``
    annotations.
    """
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        for token in scan_line(line):
            hits.append((lineno, token))
    return hits


def scan_file(path: Path) -> list[tuple[int, str]]:
    """Return ``(line_number, token)`` for every violation in *path*."""
    return scan_text(path.read_text(encoding="utf-8"))


def _verify(paths: Iterable[Path]) -> int:
    total = 0
    for path in paths:
        if not path.exists():
            print(
                f"::error::missing scan target: {path}",
                file=sys.stderr,
            )
            total += 1
            continue
        for lineno, token in scan_file(path):
            print(
                f"::error file={path},line={lineno}::"
                f"forbidden repo-local reference {token!r} in APM "
                f"artifact (append '{ACK_MARKER}' to this line if the "
                f"reference is intentional and downstream-safe).",
                file=sys.stderr,
            )
            total += 1
    if total:
        print(
            f"FAIL: {total} portability violation(s).",
            file=sys.stderr,
        )
        return 1
    print("OK: no repo-local references in scanned APM artifacts.")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    if not args.path:
        print(
            "error: at least one --path is required",
            file=sys.stderr,
        )
        return 2
    paths = [Path(p) for p in args.path]
    return _verify(paths)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Scan files for forbidden repo-local references.",
    )
    p_verify.add_argument(
        "--path",
        action="append",
        default=[],
        help=(
            "Path to a file to scan. Repeatable; supply once per file. "
            "Typical inputs are .apm/instructions/master.instructions.md, "
            "CLAUDE.md, AGENTS.md."
        ),
    )
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
