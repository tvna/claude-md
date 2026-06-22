#!/usr/bin/env python3
"""Verify no em-dash (U+2014) character appears in tracked repository files.

Issue #1889 (follow-up to #1688 and #1682): ``scan_apm_ascii.py`` guards only
the three APM artifacts (``.apm/instructions/master.instructions.md``,
``CLAUDE.md``, ``AGENTS.md``). The remaining ~77 tracked files carry em-dashes
with no gate; an agent editing any of those files can reintroduce U+2014
without a CI failure. This script is the repo-wide gate that was missing.

Invoked from ``verify-pr.yml`` (portable-pr-policy job) and registered in
``preflight_steps.py`` as::

    python3 scripts/scan_repo_em_dash.py verify --git-tracked

The contract is:

* ``--git-tracked`` enumerates all files known to git (``git ls-files``) and
  scans each one, excluding paths listed in ``_SKIP_PREFIXES`` (see below).
  Files whose UTF-8 decoding fails are skipped with a notice (never a failure;
  the scan is about the character, not about encoding).
* ``--path`` adds one explicit path; repeatable. May be combined with
  ``--git-tracked`` (paths are unioned and de-duplicated). Explicit ``--path``
  targets are not filtered by ``_SKIP_PREFIXES``.
* Every occurrence of U+2014 EM DASH is a violation. There is no allowlist:
  the ASCII separator ``--`` is the approved substitute for every context this
  repository uses (comments, docstrings, Markdown prose, table cells).
* Exit 0 when every scanned file is clean; exit 1 on any violation; exit 2
  when neither ``--git-tracked`` nor ``--path`` is supplied. Each hit emits
  ``::error file=<path>,line=<n>,col=<c>::...`` on stderr so the GitHub
  Actions UI surfaces individual violations.

Excluded path prefixes (``_SKIP_PREFIXES``):
    ``.agents/skills/``: files expanded from the APM upstream dependency
    (``obra/superpowers`` pinned in ``apm.yml``). These files must not be
    edited directly; any em-dash content there originates upstream and is
    outside this repo's fix scope.

Contract:
    Inputs: the ``verify`` subcommand plus ``--git-tracked`` and/or one or
        more ``--path`` arguments. No stdin, no environment variables.
    Outputs: ``::error file=<path>,line=<n>,col=<c>::`` annotation on stderr
        for each U+2014 hit, plus an ``OK:`` / ``FAIL:`` summary line; exit
        0 when every scanned file is clean, 1 on any violation, 2 when no
        scan targets are supplied.
    Failure policy: fails loud per CLAUDE.md section 4; a U+2014 character
        or a ``git ls-files`` failure exits non-zero rather than passing
        silently.

Tested by ``tests/test_scan_repo_em_dash.py``. Refs #1889, #1688, #1682.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

_EM_DASH = "\u2014"  # U+2014 EM DASH; use escape to keep this file ASCII-clean

# Files under these path prefixes are excluded from --git-tracked scans.
# .agents/skills/ is expanded from the upstream APM dependency (obra/superpowers
# pinned in apm.yml); editing it directly is prohibited, so em-dashes there are
# outside this repo's fix scope.
_SKIP_PREFIXES = (".agents/skills/",)


def scan_text(text: str) -> list[tuple[int, int]]:
    """Return ``(line, column)`` for every U+2014 in *text*.

    Line and column numbers are 1-based to match GitHub Actions
    ``::error file=`` annotations and an editor's cursor. Only ``"\\n"``
    advances the line counter.

    The function is pure (it never touches the filesystem); so the
    detection is unit-tested directly on string fixtures.
    """
    hits: list[tuple[int, int]] = []
    lineno = 1
    column = 0
    for char in text:
        if char == "\n":
            lineno += 1
            column = 0
            continue
        column += 1
        if char == _EM_DASH:
            hits.append((lineno, column))
    return hits


def scan_file(path: Path) -> list[tuple[int, int]]:
    """Return ``(line, column)`` for every U+2014 in *path*.

    Returns an empty list and prints a notice when the file cannot be decoded
    as UTF-8 (binary files) or when the path is a directory.
    """
    try:
        return scan_text(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, IsADirectoryError, OSError):
        print(f"notice: skipping {path} (unreadable as UTF-8)")
        return []


def _git_tracked_files() -> list[Path] | None:
    """Return git-tracked files, excluding paths in ``_SKIP_PREFIXES``.

    Returns ``None`` (and emits an ``::error::`` annotation) when
    ``git ls-files`` fails; the caller must treat ``None`` as a hard
    error rather than an empty file list, so the gate never silently
    passes when it cannot enumerate the repository.
    """
    result = subprocess.run(  # noqa: S603 -- fixed argv, shell=False
        ["git", "ls-files"],  # noqa: S607 -- git resolved via PATH
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print(
            f"::error::git ls-files failed: {result.stderr.strip()}",
            file=sys.stderr,
        )
        return None
    return [
        Path(p)
        for p in result.stdout.splitlines()
        if p and not any(p.startswith(prefix) for prefix in _SKIP_PREFIXES)
    ]


def _verify(paths: list[Path]) -> int:
    total = 0
    for path in sorted({p for p in paths if p.is_file()}):
        for lineno, column in scan_file(path):
            print(
                f"::error file={path},line={lineno},col={column}::"
                "em-dash (U+2014) found. Replace with the ASCII separator"
                " ' -- '. Refs #1889.",
                file=sys.stderr,
            )
            total += 1
    if total:
        print(
            f"FAIL: {total} em-dash violation(s).",
            file=sys.stderr,
        )
        return 1
    print("OK: no em-dash (U+2014) found in scanned files.")
    return 0


def _cmd_verify(args: argparse.Namespace) -> int:
    if not args.git_tracked and not args.path:
        print(
            "error: supply --git-tracked or at least one --path",
            file=sys.stderr,
        )
        return 2
    paths: list[Path] = [Path(p) for p in args.path]
    if args.git_tracked:
        tracked = _git_tracked_files()
        if tracked is None:
            return 1  # git ls-files failed; error already printed
        paths.extend(tracked)
    return _verify(paths)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Scan for em-dash (U+2014) in tracked repository files.",
    )
    p_verify.add_argument(
        "--git-tracked",
        action="store_true",
        default=False,
        help="Scan all files enumerated by `git ls-files`.",
    )
    p_verify.add_argument(
        "--path",
        action="append",
        default=[],
        help="Explicit path to scan. Repeatable; may be combined with "
        "--git-tracked.",
    )
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
