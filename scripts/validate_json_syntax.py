#!/usr/bin/env python3
"""Validate that the given files contain syntactically valid JSON.

Replaces the inline ``for f in ...; do jq empty < "$f"; done`` loops in
``.github/workflows/apply-rulesets.yml`` and
``.github/workflows/weekly-maintenance.yml``. Emits a GitHub Actions
``::error file=...`` annotation for each file that is missing or malformed.

Usage::

    python3 scripts/validate_json_syntax.py verify \\
        --file .github/rulesets/main.json \\
        --file .github/rulesets/all-branches.json

Exit codes:
    0  Every file parsed as JSON.
    1  One or more files were missing or contained invalid JSON.
    2  Usage error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def validate_files(paths: list[str]) -> list[tuple[str, str]]:
    """Return ``(path, reason)`` for each file that is missing or not valid JSON.

    An empty result means every file parsed successfully.
    """
    errors: list[tuple[str, str]] = []
    for path in paths:
        try:
            raw = Path(path).read_text(encoding="utf-8")
        except OSError as exc:
            errors.append((path, f"unreadable: {exc}"))
            continue
        try:
            json.loads(raw)
        except json.JSONDecodeError as exc:
            errors.append((path, f"invalid JSON syntax: {exc}"))
    return errors


def _cmd_verify(args: argparse.Namespace) -> int:
    errors = validate_files(args.file)
    for path, reason in errors:
        print(f"::error file={path}::{reason}", file=sys.stderr)
    return 1 if errors else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate JSON syntax of one or more files.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    verify_p = sub.add_parser("verify", help="Exit 1 if any file is missing or invalid JSON")
    verify_p.add_argument("--file", action="append", default=[], required=True, help="File to validate (repeatable)")

    args = parser.parse_args(argv)

    if args.cmd == "verify":
        return _cmd_verify(args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
