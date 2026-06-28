#!/usr/bin/env python3
"""Verify every workflow ``uses:`` entry is SHA-pinned with a tag comment.

Issue #310 (Phase 3 C-1 of #63 supply-chain catalog): a mutable
``uses: owner/repo@vN`` reference lets an attacker retarget the tag to
an arbitrary commit and execute arbitrary code in CI. Every external
action reference in ``.github/workflows/**/*.{yml,yaml}`` must be pinned
to a full 40-character commit SHA with a human-readable ``# <tag>``
comment so reviewers can spot drift at a glance.

Invoked from ``.github/workflows/verify-agents.yml`` (lint-scripts job)
as ``python scripts/scan_workflow_action_pins.py verify``.

The contract is:

* Scan every ``.yml`` / ``.yaml`` file under ``.github/workflows/``.
* For each line carrying ``uses:``, extract the reference and require:

  - Local references (``./path/to/workflow.yml``) are skipped; they are
    in-repo files reviewed through the same code-owner gate.
  - ``docker://`` references are skipped; digest pinning for OCI images
    is tracked separately and out of scope for this gate.
  - All other references must match ``owner/repo@<40-hex-sha>`` and the
    same line must carry a non-empty ``# <tag>`` comment.

* Comment-only lines (first non-whitespace char is ``#``) are skipped so
  the rule can be documented inside workflow YAML without self-tripping.
* Lines carrying ``ACK_MARKER`` are skipped. Mirrors the escape-hatch
  precedent set by ``scripts/scan_workflow_pip.py``.

Exit 0 when every workflow is clean; exit 1 on any violation. Each hit
emits ``::error file=<path>,line=<n>::...`` on stderr so the GitHub
Actions UI surfaces individual violations.

Tested by ``tests/test_scan_workflow_action_pins.py``. Refs #63, #310.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from pathlib import Path

WORKFLOW_SUBDIR = ".github/workflows"

# Lines carrying this marker bypass the scan. Mirrors the precedent set
# by ``scripts/scan_workflow_pip.py`` ACK_MARKER.
ACK_MARKER = "<!-- action-pin-ack -->"

# Matches the ``uses:`` key and captures the reference value (everything
# up to whitespace, ``#``, or end-of-line). Tolerates optional list dash
# and arbitrary leading whitespace.
_USES_LINE = re.compile(r"^\s*-?\s*uses:\s*(?P<ref>\S+)")

# A 40-character lowercase hex string; a full git commit SHA.
_FULL_SHA = re.compile(r"^[0-9a-f]{40}$")

# Captures the trailing ``# <tag>`` comment after the reference. The tag
# text must be non-empty after stripping whitespace.
_TAG_COMMENT = re.compile(r"#\s*(?P<tag>\S.*?)\s*$")

# Matches a pure comment line (first non-whitespace char is ``#``). Used
# to skip in-YAML documentation that may quote a forbidden pattern.
_COMMENT_LINE = re.compile(r"^\s*#")


def _is_local_ref(ref: str) -> bool:
    """Return True if *ref* points to an in-repo workflow file."""
    return ref.startswith("./") or ref.startswith("../")


def _is_docker_ref(ref: str) -> bool:
    """Return True if *ref* is a ``docker://`` OCI image reference."""
    return ref.startswith("docker://")


def scan_line(line: str) -> str | None:
    """Return a violation reason for *line*, or None if it is acceptable.

    A line is acceptable when any of:

    * It carries :data:`ACK_MARKER` or is a pure comment.
    * It is not a ``uses:`` line at all.
    * Its ``uses:`` reference is local (``./...``) or ``docker://...``.
    * Its reference is ``owner/repo@<40-hex-sha>`` AND the line carries
      a non-empty ``# <tag>`` comment.

    The returned string is a short human-readable reason for the
    annotation. Callers append it after ``::error file=...,line=...::``.
    """
    if ACK_MARKER in line:
        return None
    if _COMMENT_LINE.match(line):
        return None
    match = _USES_LINE.match(line)
    if not match:
        return None
    ref = match.group("ref")
    if _is_local_ref(ref) or _is_docker_ref(ref):
        return None
    if "@" not in ref:
        return f"uses: {ref!r} has no '@<sha>' pin"
    owner_repo, _, rev = ref.rpartition("@")
    if not owner_repo:
        return f"uses: {ref!r} is missing owner/repo before '@'"
    if not _FULL_SHA.match(rev):
        return (
            f"uses: {ref!r} must pin to a 40-char lowercase commit SHA "
            f"(got {rev!r})"
        )
    tag_match = _TAG_COMMENT.search(line)
    if not tag_match:
        return (
            f"uses: {ref!r} is SHA-pinned but missing trailing "
            f"'# <tag>' comment"
        )
    return None


def scan_text(text: str) -> list[tuple[int, str]]:
    """Return ``(line_number, reason)`` tuples for each violation."""
    out: list[tuple[int, str]] = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        reason = scan_line(line)
        if reason is not None:
            out.append((lineno, reason))
    return out


def scan_file(path: Path) -> list[tuple[int, str]]:
    """Return ``(line_number, reason)`` tuples for violations in *path*."""
    return scan_text(path.read_text(encoding="utf-8", errors="ignore"))


def find_violations(repo_root: Path) -> list[tuple[Path, int, str]]:
    """Return ``(relative_path, line_number, reason)`` for every violation.

    Scans ``.github/workflows/*.{yml,yaml}`` under *repo_root*. Returns
    an empty list when the directory is absent (a repo without any
    workflows trivially passes).
    """
    workflow_dir = repo_root / WORKFLOW_SUBDIR
    if not workflow_dir.exists():
        return []
    violations: list[tuple[Path, int, str]] = []
    for path in _iter_workflow_files(workflow_dir):
        rel = path.relative_to(repo_root)
        for lineno, reason in scan_file(path):
            violations.append((rel, lineno, reason))
    return violations


def _iter_workflow_files(workflow_dir: Path) -> Iterator[Path]:
    for path in sorted(workflow_dir.rglob("*")):
        if path.is_file() and path.suffix in (".yml", ".yaml"):
            yield path


def _cmd_verify(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    violations = find_violations(repo_root)
    for rel, lineno, reason in violations:
        print(
            f"::error file={rel},line={lineno}::"
            f"{reason}; pin as 'owner/repo@<40-hex-sha> # <tag>' "
            f"(append '{ACK_MARKER}' to this line if the bypass is "
            f"intentional and reviewed).",
            file=sys.stderr,
        )
    if violations:
        print(
            f"FAIL: {len(violations)} workflow action pin "
            f"violation(s).",
            file=sys.stderr,
        )
        return 1
    print("OK: every workflow uses: entry is SHA-pinned with a tag comment.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help=(
            "Scan workflow YAML and require every external uses: entry "
            "to be SHA-pinned with a '# <tag>' comment; exit 1 on hit."
        ),
    )
    p_verify.add_argument("--repo-root", default=".")
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
