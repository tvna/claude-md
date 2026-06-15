#!/usr/bin/env python3
"""Gate: every public scripts/*.py and .github/workflows/*.yml has specific area coverage.

Reads ``.github/label-policy.toml``. A file is *specifically covered* when it
matches at least one ``[[area_paths]]`` entry that does NOT carry ``broad =
true``. Files that only match broad catch-all entries (``scripts/**``,
``.github/**``) or match no entry at all are *uncovered* and cause exit 1.

Private/internal helper scripts (names starting with ``_``) are exempt by
design: they are never CLI entry points and are not directly invoked by
workflows or hooks.

A minimal ``COVERAGE_ALLOWLIST`` captures files that cannot yet be classified;
each entry names the file (relative to repo root) and a rationale string.
Allowlist entries are validated: a stale entry (file removed or now
specifically covered) causes exit 1 so the allowlist remains a ratchet that
can only shrink.

Contract:
- Inputs: the ``verify`` subcommand; optional ``--scripts-dir``,
  ``--workflows-dir``, ``--policy`` arguments for test injection.
- Outputs: ``::error file=<path>::scan_harness_doc_coverage: <path> has no
  specific area_paths coverage`` annotations on stderr for uncovered files;
  ``OK:`` line on success; exit 0 when all files are covered or allowlisted.
- Failure policy: fails loud (exit 1) per CLAUDE.md section 4 for any
  uncovered file absent from COVERAGE_ALLOWLIST; fails open (exit 0) when the
  policy file is absent so the gate skips rather than blocks on a missing file.

Tested by ``tests/test_scan_harness_doc_coverage.py``. Refs #1761.
"""

from __future__ import annotations

import argparse
import fnmatch
import sys
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
POLICY_PATH = Path(".github/label-policy.toml")
SCRIPTS_DIR = Path("scripts")
WORKFLOWS_DIR = Path(".github/workflows")
_SCRIPT = "scan_harness_doc_coverage"

# Files that cannot yet be classified in a specific area_paths entry.
# Key: path relative to repo root (forward slashes). Value: rationale + issue.
# This allowlist is a ratchet: a stale entry (file removed or now covered)
# causes exit 1 so the set can only shrink over time.
COVERAGE_ALLOWLIST: dict[str, str] = {}


def load_entries(policy_path: Path) -> list[dict[str, Any]]:
    """Return all [[area_paths]] entries from *policy_path*."""
    with policy_path.open("rb") as fh:
        data = tomllib.load(fh)
    return [e for e in data.get("area_paths", []) if isinstance(e, dict)]


def is_specifically_covered(rel_path: str, entries: list[dict[str, Any]]) -> bool:
    """Return True if *rel_path* matches at least one non-broad area_paths entry."""
    for entry in entries:
        if entry.get("broad"):
            continue
        for pattern in entry.get("paths", []):
            if isinstance(pattern, str) and fnmatch.fnmatch(rel_path, pattern):
                return True
    return False


def collect_scripts(scripts_dir: Path) -> list[Path]:
    """Return sorted public (non-private) .py scripts under *scripts_dir*."""
    return sorted(p for p in scripts_dir.glob("*.py") if not p.name.startswith("_"))


def collect_workflows(workflows_dir: Path) -> list[Path]:
    """Return sorted .yml/.yaml workflow files under *workflows_dir*."""
    return sorted(workflows_dir.glob("*.yml")) + sorted(workflows_dir.glob("*.yaml"))


def _err(rel_path: str, message: str) -> str:
    return f"::error file={rel_path}::{_SCRIPT}: {message}"


def verify(
    root: Path = REPO_ROOT,
    policy_path: Path | None = None,
    scripts_dir: Path | None = None,
    workflows_dir: Path | None = None,
) -> list[str]:
    """Return diagnostic messages for uncovered files and stale allowlist entries."""
    root = root.resolve()
    if policy_path is None:
        policy_path = root / POLICY_PATH
    if scripts_dir is None:
        scripts_dir = root / SCRIPTS_DIR
    if workflows_dir is None:
        workflows_dir = root / WORKFLOWS_DIR

    if not policy_path.exists():
        print(
            f"::warning::{_SCRIPT}: policy file {policy_path} not found; "
            "skipping coverage check.",
            file=sys.stderr,
        )
        return []

    entries = load_entries(policy_path)
    errors: list[str] = []

    files_to_check: list[Path] = []
    if scripts_dir.exists():
        files_to_check.extend(collect_scripts(scripts_dir))
    if workflows_dir.exists():
        files_to_check.extend(collect_workflows(workflows_dir))

    covered_allowlisted: set[str] = set()

    for fpath in files_to_check:
        rel = fpath.relative_to(root).as_posix()
        specifically_covered = is_specifically_covered(rel, entries)

        if specifically_covered:
            if rel in COVERAGE_ALLOWLIST:
                covered_allowlisted.add(rel)
        else:
            if rel in COVERAGE_ALLOWLIST:
                pass  # allowlisted: skip without error
            else:
                errors.append(
                    _err(
                        rel,
                        f"{rel!r} has no specific area_paths coverage in "
                        f"{POLICY_PATH}; add a non-broad [[area_paths]] entry "
                        f"or add to COVERAGE_ALLOWLIST with a rationale. "
                        "Refs #1761.",
                    )
                )

    # Detect stale allowlist entries: files that are now specifically covered
    # or no longer exist in the tree.
    all_rel: set[str] = {f.relative_to(root).as_posix() for f in files_to_check}
    for allowlisted_path in COVERAGE_ALLOWLIST:
        if allowlisted_path in covered_allowlisted:
            errors.append(
                _err(
                    allowlisted_path,
                    f"{allowlisted_path!r} is in COVERAGE_ALLOWLIST but now has "
                    "specific coverage; remove it from the allowlist.",
                )
            )
        elif allowlisted_path not in all_rel:
            errors.append(
                _err(
                    allowlisted_path,
                    f"{allowlisted_path!r} is in COVERAGE_ALLOWLIST but no "
                    "longer exists; remove the stale entry.",
                )
            )

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gate: every harness file has specific area_paths coverage."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    sub = subparsers.add_parser(
        "verify", help="check coverage for all harness files"
    )
    sub.add_argument(
        "--policy",
        default=None,
        metavar="PATH",
        help=f"path to label-policy.toml (default: {POLICY_PATH})",
    )
    sub.add_argument(
        "--scripts-dir",
        default=None,
        metavar="DIR",
        help=f"directory to scan for *.py scripts (default: {SCRIPTS_DIR})",
    )
    sub.add_argument(
        "--workflows-dir",
        default=None,
        metavar="DIR",
        help=f"directory to scan for *.yml workflows (default: {WORKFLOWS_DIR})",
    )
    args = parser.parse_args(argv)

    if args.command == "verify":
        policy = Path(args.policy) if args.policy else None
        scripts = Path(args.scripts_dir) if args.scripts_dir else None
        workflows = Path(args.workflows_dir) if args.workflows_dir else None

        errors = verify(
            policy_path=policy,
            scripts_dir=scripts,
            workflows_dir=workflows,
        )
        for error in errors:
            print(error, file=sys.stderr)
        if errors:
            return 1
        print(f"OK: {_SCRIPT}: all harness files have specific area_paths coverage.", file=sys.stderr)
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
