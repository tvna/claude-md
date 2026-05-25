#!/usr/bin/env python3
"""Ban direct ``pip install`` invocations in workflow YAML.

Issue #289 retrospective for PR #277: the repair loop replaced direct
``pip install`` and bare ``pytest`` calls in ``verify-agents.yml`` with
pinned ``uv`` installation, ``uv sync --locked``, and ``uv run``. This
script is the deterministic gate the retrospective identified as
missing: it rejects any reintroduction of repository Python package
installation that bypasses uv.

Invoked from ``.github/workflows/verify-agents.yml`` (lint-scripts job)
as ``python scripts/scan_workflow_pip.py verify``.

The contract is:

* Scan every ``.yml`` / ``.yaml`` file under ``.github/workflows/``.
* Flag any line that executes one of: ``pip install``, ``pip3 install``,
  ``python -m pip install``, ``python3 -m pip install``.
* The ``uv`` prefix is allowed: ``uv pip install`` is the supported
  uv-managed channel for ad-hoc installs.
* Comment lines (first non-whitespace char is ``#``) are skipped so the
  rule can be documented inside workflow YAML without self-tripping.
* Lines carrying ``ACK_MARKER`` are skipped. Mirrors the escape-hatch
  precedent set by ``scripts/scan_apm_portability.py`` for the rare
  legitimate exception.

Exit 0 when every workflow is clean; exit 1 on any violation. Each hit
emits ``::error file=<path>,line=<n>::...`` on stderr so the GitHub
Actions UI surfaces individual violations.

Tested by ``tests/test_scan_workflow_pip.py``. Refs #289.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from pathlib import Path

WORKFLOW_SUBDIR = ".github/workflows"

# Lines carrying this marker bypass the scan. Mirrors the precedent set
# by ``scripts/scan_apm_portability.py`` ACK_MARKER.
ACK_MARKER = "<!-- pip-install-ack -->"

# Matches direct Python package installation that bypasses uv:
#
#   pip install ...
#   pip3 install ...
#   python -m pip install ...
#   python3 -m pip install ...
#
# The ``(?<!uv )`` negative lookbehind exempts ``uv pip install`` -- the
# supported uv-managed channel. ``\b`` anchors avoid false positives on
# tokens like ``pipeline``, ``zipinstall``, or ``Pipfile``.
_PIP_INSTALL = re.compile(
    r"(?<!uv )\b(?:pip3?|python3?\s+-m\s+pip)\s+install\b"
)

# Matches a pure comment line (first non-whitespace char is ``#``). Used
# to skip in-YAML documentation that may quote the forbidden pattern.
_COMMENT_LINE = re.compile(r"^\s*#")


def scan_line(line: str) -> bool:
    """Return True if *line* contains a forbidden direct pip install.

    Lines that are pure comments or carry :data:`ACK_MARKER` are treated
    as explicitly allowed and return False.
    """
    if ACK_MARKER in line:
        return False
    if _COMMENT_LINE.match(line):
        return False
    return _PIP_INSTALL.search(line) is not None


def scan_text(text: str) -> list[int]:
    """Return 1-based line numbers containing a violation in *text*."""
    return [
        lineno
        for lineno, line in enumerate(text.splitlines(), start=1)
        if scan_line(line)
    ]


def scan_file(path: Path) -> list[int]:
    """Return 1-based line numbers containing a violation in *path*."""
    return scan_text(path.read_text(encoding="utf-8", errors="ignore"))


def find_violations(repo_root: Path) -> list[tuple[Path, int]]:
    """Return ``(relative_path, line_number)`` tuples for every violation.

    Scans ``.github/workflows/*.{yml,yaml}`` under *repo_root*. Returns
    an empty list when the directory is absent (a repo without any
    workflows trivially passes).
    """
    workflow_dir = repo_root / WORKFLOW_SUBDIR
    if not workflow_dir.exists():
        return []
    violations: list[tuple[Path, int]] = []
    for path in _iter_workflow_files(workflow_dir):
        rel = path.relative_to(repo_root)
        for lineno in scan_file(path):
            violations.append((rel, lineno))
    return violations


def _iter_workflow_files(workflow_dir: Path) -> Iterator[Path]:
    for path in sorted(workflow_dir.rglob("*")):
        if path.is_file() and path.suffix in (".yml", ".yaml"):
            yield path


def _cmd_verify(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    violations = find_violations(repo_root)
    for rel, lineno in violations:
        print(
            f"::error file={rel},line={lineno}::"
            f"direct Python package installation in workflow YAML; "
            f"use 'uv pip install', 'uv sync --locked', or "
            f"'uv run --with ...' instead (append '{ACK_MARKER}' to "
            f"this line if the bypass is intentional and reviewed).",
            file=sys.stderr,
        )
    if violations:
        print(
            f"FAIL: {len(violations)} direct pip install "
            f"violation(s) in workflow YAML.",
            file=sys.stderr,
        )
        return 1
    print("OK: no direct pip install in workflow YAML.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Scan workflow YAML for direct pip install; exit 1 on hit.",
    )
    p_verify.add_argument("--repo-root", default=".")
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
