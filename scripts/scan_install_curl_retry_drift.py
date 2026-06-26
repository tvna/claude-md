#!/usr/bin/env python3
"""Drift gate: SessionStart installers must download via ``retry_download`` (#2038).

Every ``scripts/install-*.sh`` fetches its pinned release through the shared
``retry_download`` helper in ``scripts/_retry.sh``, which provides the
retry-with-backoff loop and the fail-loud-but-fail-open surfacing. A bare
``curl`` invocation in an installer bypasses that helper and silently
reintroduces the no-retry behavior #2038 removed. This gate fails when any
installer contains a ``curl`` command outside a comment line, so the invariant
cannot regress by reviewer memory alone (CLAUDE.md section 3).

Whole-line comments are ignored so prose mentioning curl does not
false-positive. The ``curl`` living in ``scripts/_retry.sh`` is intentionally
out of scope: it is the single sanctioned download site and is not an
``install-*.sh``.

Contract: ``scripts/scan_install_curl_retry_drift.py verify`` prints one
``::error::`` line per offending file/line and exits 1; a clean tree exits 0.

Fail-open: an unreadable file exits 0 for that file with no violation, and an
empty installer set exits 0 with a warning, so a gate bug never wedges
commit/CI (CLAUDE.md section 4).
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

_SCRIPT = "scan_install_curl_retry_drift"
_REPO_ROOT = Path(__file__).resolve().parent.parent
_INSTALLER_GLOB = "install-*.sh"
_CURL = re.compile(r"\bcurl\b")


def _is_comment_line(line: str) -> bool:
    """Return True for a whole-line shell comment (optional leading whitespace)."""
    return line.lstrip().startswith("#")


def find_violations(paths: Iterable[Path]) -> list[tuple[Path, int, str]]:
    """Return ``(path, line_number, line_text)`` for each bare ``curl`` found.

    Whole-line comments are skipped. Unreadable files are skipped (fail-open).
    """
    violations: list[tuple[Path, int, str]] = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), start=1):
            if _is_comment_line(line):
                continue
            if _CURL.search(line):
                violations.append((path, line_no, line.strip()))
    return violations


def installer_paths(root: Path) -> list[Path]:
    """Return the sorted set of ``scripts/install-*.sh`` under ``root``."""
    return sorted((root / "scripts").glob(_INSTALLER_GLOB))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "command",
        nargs="?",
        default="verify",
        choices=["verify"],
        help="verify (default): fail if any installer downloads with bare curl.",
    )
    parser.parse_args(argv)

    paths = installer_paths(_REPO_ROOT)
    if not paths:
        print(
            f"::warning::{_SCRIPT}: no install-*.sh found under "
            f"{_REPO_ROOT / 'scripts'}; skipping.",
            file=sys.stderr,
        )
        return 0

    violations = find_violations(paths)
    for path, line_no, text in violations:
        rel = path.relative_to(_REPO_ROOT) if path.is_relative_to(_REPO_ROOT) else path
        print(
            f"::error file={rel},line={line_no}::{_SCRIPT}: bare 'curl' download "
            f"in {rel}; route the download through retry_download "
            f"(scripts/_retry.sh) instead. Offending line: {text}",
            file=sys.stderr,
        )
    return 1 if violations else 0


if __name__ == "__main__":
    raise SystemExit(main())
