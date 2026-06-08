#!/usr/bin/env python3
"""Fail when a tool is compiled from source on the CI hot path.

The #1150 slowdown (~138s) came from ``install_waza.sh`` compiling waza via
``go install`` instead of downloading the pinned prebuilt. Caching cannot
defend against that (branch-scoped caches do not restore cross-PR), and CI
wall time is not statically decidable. But "a tool is built from source" IS
decidable, and it is the actual failure class -- so this gate makes it a
deterministic check (retro #1152, #1153, #1154).

``scan_workflow_pip.py`` already bans ``pip install`` in workflows; this gate
covers the ``go install`` / ``cargo install`` idiom (compile + install a tool
from source) under both ``scripts/`` and ``.github/workflows/``.

The rule:

* Flag a command-position ``go install`` / ``cargo install`` (line start or
  after a shell separator ``&&``, ``||``, ``;``, ``|``), so a log line that
  merely mentions the phrase inside a string is not a false positive.
* Comment lines (first non-whitespace char ``#``) are skipped, so the rule can
  be documented without self-tripping.
* A line carrying ``# compile-source-ack`` is allowed -- the escape hatch for a
  deliberate, reviewed source build (e.g. the install_waza.sh backstop reached
  only on a platform with no pinned prebuilt). Mirrors the
  ``scan_workflow_pip.py`` ACK precedent.

Because every prebuilt-shipping tool should be fetched, not compiled, a new
``go install``/``cargo install`` on the hot path fails CI until the author
either switches to a pinned prebuilt or acks a justified backstop.

CLI::

    python3 scripts/scan_compile_from_source.py verify  # exit 1 on a hit
    python3 scripts/scan_compile_from_source.py list     # print all hits

Fails loud per CLAUDE.md section 4. Tested by
``tests/test_scan_compile_from_source.py``. Refs #1150, #1153, #1154.

Contract:
    Inputs: the ``verify`` or ``list`` subcommand; the files under
        ``scripts/`` and ``.github/workflows/``. No stdin, no env input.
    Outputs: ``verify`` prints ``::error file=...::`` per un-acked source build
        and a one-line summary, exit 0 when clean and exit 1 on any hit;
        ``list`` prints every matching ``path:line`` on stdout.
    Failure policy: fails loud per CLAUDE.md section 4 (gate: an un-acked
        source build exits non-zero).
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Directories whose files must not compile a tool from source unacked.
SCANNED_SUBDIRS: tuple[str, ...] = ("scripts", ".github/workflows")

# Lines carrying this marker bypass the scan. Mirrors scan_workflow_pip.py.
ACK_MARKER = "# compile-source-ack"

# ``go install`` / ``cargo install`` in command position: at the start of the
# line (optional leading whitespace / ``run:`` / ``-`` / ``sudo``) or right
# after a shell separator. Keeps a log string that merely names the phrase
# (e.g. ``echo "... via go install ..."``) from matching.
_COMPILE_RE = re.compile(
    r"(?:^|&&|\|\||;|\|)\s*(?:sudo\s+)?(?:run:\s*)?(?:go|cargo)\s+install\b"
)

# A pure comment line (first non-whitespace char is ``#``).
_COMMENT_LINE = re.compile(r"^\s*#")


def scan_line(line: str) -> bool:
    """Return True if *line* is an un-acked source-build command."""
    if _COMMENT_LINE.match(line):
        return False
    if ACK_MARKER in line:
        return False
    return _COMPILE_RE.search(line) is not None


def _iter_files(repo_root: Path) -> Iterator[Path]:
    for subdir in SCANNED_SUBDIRS:
        base = repo_root / subdir
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*")):
            if path.is_file():
                yield path


def find_hits(repo_root: Path) -> list[str]:
    """Return ``path:line`` strings for every un-acked source build."""
    hits: list[str] = []
    for path in _iter_files(repo_root):
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if scan_line(line):
                hits.append(f"{path.relative_to(repo_root)}:{lineno}")
    return hits


def _cmd_verify(_args: argparse.Namespace) -> int:
    hits = find_hits(REPO_ROOT)
    if hits:
        for hit in hits:
            path, lineno = hit.rsplit(":", 1)
            print(
                f"::error file={path},line={lineno}::source build "
                f"(go/cargo install) on the CI surface -- prefer a pinned "
                f"prebuilt download. If a deliberate backstop, append "
                f"'{ACK_MARKER}' with a rationale (#1154).",
                file=sys.stderr,
            )
        print(
            f"FAIL: {len(hits)} un-acked source build(s) under "
            f"{', '.join(SCANNED_SUBDIRS)}.",
            file=sys.stderr,
        )
        return 1
    print(
        f"OK: no un-acked source build under {', '.join(SCANNED_SUBDIRS)}."
    )
    return 0


def _cmd_list(_args: argparse.Namespace) -> int:
    for hit in find_hits(REPO_ROOT):
        print(hit)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("verify", help="fail on any un-acked source build").set_defaults(
        func=_cmd_verify
    )
    sub.add_parser("list", help="print every matching path:line").set_defaults(
        func=_cmd_list
    )
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
