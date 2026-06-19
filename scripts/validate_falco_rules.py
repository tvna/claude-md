#!/usr/bin/env python3
"""Validate Falco rules YAML files for structural correctness.

Checks:
1. Valid YAML syntax.
2. Each entry has the required fields for its type (rule / macro / list).
3. Rule ``priority`` is a valid Falco priority string.
4. Condition and output fields do not reference known wrong field names
   (e.g. ``proc.exe`` instead of ``proc.exepath``).

Usage::

    python3 scripts/validate_falco_rules.py verify \\
        --file .devcontainer/falco/custom-rules.yaml

Exit codes:
    0  All checks passed.
    1  One or more validation errors found.
    2  Usage error (missing argument or import failure).

Contract:
- Inputs: ``--file PATH`` (repeatable via ``action="append"``); each PATH
  must be a readable UTF-8 YAML file containing a top-level sequence.
- Outputs: ``::error file=<path>::<message>`` annotations written to stderr
  for every violation found; exit 0 when all files are valid, exit 1 on
  any violation, exit 2 on a usage error or missing PyYAML dependency.
- Failure policy: fails loud per CLAUDE.md section 4; an empty ``catch`` or
  silent default is never used -- every error path surfaces a human-readable
  annotation before exiting non-zero.

Refs #1847, #1846.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:
    print("::error::PyYAML is not installed. Run: pip install pyyaml", file=sys.stderr)
    sys.exit(2)


# ---------------------------------------------------------------------------
# Schema constants
# ---------------------------------------------------------------------------

_REQUIRED_FIELDS: dict[str, frozenset[str]] = {
    "rule": frozenset({"rule", "desc", "condition", "output", "priority"}),
    "macro": frozenset({"macro", "condition"}),
    "list": frozenset({"list", "items"}),
}

_VALID_PRIORITIES: frozenset[str] = frozenset(
    {
        "DEBUG",
        "INFORMATIONAL",
        "NOTICE",
        "WARNING",
        "ERROR",
        "CRITICAL",
        "ALERT",
        "EMERGENCY",
    }
)

# Curated map of wrong field name -> correct alternative.
# Catches the proc.exe / proc.exepath class of typos identified in retro #1846.
_WRONG_FIELDS: dict[str, str] = {
    "proc.exe": "proc.exepath",
    "proc.cmdargs": "proc.cmdline",
    "container.image": "container.image.repository",
}

_WRONG_FIELD_RE = re.compile(
    r"\b(" + "|".join(re.escape(f) for f in _WRONG_FIELDS) + r")\b"
)


# ---------------------------------------------------------------------------
# Pure validation logic
# ---------------------------------------------------------------------------


def _entry_type(entry: dict[str, Any]) -> str | None:
    """Return the type key of a Falco YAML entry, or None if unrecognised."""
    for key in _REQUIRED_FIELDS:
        if key in entry:
            return key
    return None


def validate_entries(path: str, entries: list[Any]) -> list[str]:
    """Return ``::error::`` strings for every structural violation found."""
    errors: list[str] = []

    for idx, entry in enumerate(entries):
        if not isinstance(entry, dict):
            errors.append(
                f"::error file={path}::entry #{idx}: expected a mapping, "
                f"got {type(entry).__name__}"
            )
            continue

        etype = _entry_type(entry)
        if etype is None:
            errors.append(
                f"::error file={path}::entry #{idx}: unrecognised type "
                f"(expected a 'rule', 'macro', or 'list' key); "
                f"keys present: {sorted(entry.keys())}"
            )
            continue

        name = str(entry.get(etype, f"<unnamed #{idx}>"))

        # Required-field check
        for field in sorted(_REQUIRED_FIELDS[etype] - entry.keys()):
            errors.append(
                f"::error file={path}::{etype} {name!r}: "
                f"missing required field '{field}'"
            )

        # Priority validation
        if etype == "rule":
            priority = entry.get("priority")
            if priority is not None and str(priority).upper() not in _VALID_PRIORITIES:
                errors.append(
                    f"::error file={path}::rule {name!r}: "
                    f"invalid priority {priority!r}; "
                    f"valid values: {', '.join(sorted(_VALID_PRIORITIES))}"
                )

        # Wrong field-name detection in condition and output text
        for field_key in ("condition", "output"):
            text = entry.get(field_key)
            if not isinstance(text, str):
                continue
            for match in _WRONG_FIELD_RE.finditer(text):
                wrong = match.group(1)
                correct = _WRONG_FIELDS[wrong]
                errors.append(
                    f"::error file={path}::{etype} {name!r}: "
                    f"'{wrong}' is not a valid Falco field; "
                    f"use '{correct}' instead"
                )

    return errors


def validate_file(path: str) -> list[str]:
    """Parse and validate a single Falco rules YAML file.

    Returns a list of ``::error::`` annotation strings; an empty list means
    the file is valid.
    """
    try:
        raw = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        return [f"::error file={path}::cannot read file: {exc}"]

    try:
        entries = yaml.safe_load(raw)
    except yaml.YAMLError as exc:
        return [f"::error file={path}::invalid YAML syntax: {exc}"]

    if not isinstance(entries, list):
        return [
            f"::error file={path}::top-level value must be a YAML sequence, "
            f"got {type(entries).__name__}"
        ]

    return validate_entries(path, entries)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _cmd_verify(args: argparse.Namespace) -> int:
    all_errors: list[str] = []
    for path in args.file:
        all_errors.extend(validate_file(path))
    for err in all_errors:
        print(err, file=sys.stderr)
    if all_errors:
        return 1
    n = len(args.file)
    print(f"OK: {n} Falco rules file(s) validated successfully.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate Falco rules YAML files for structural correctness."
    )
    sub = parser.add_subparsers(dest="cmd", required=True)

    verify_p = sub.add_parser(
        "verify", help="Exit 1 if any file fails validation."
    )
    verify_p.add_argument(
        "--file",
        action="append",
        default=[],
        required=True,
        metavar="PATH",
        help="Falco rules YAML file to validate (repeatable).",
    )

    args = parser.parse_args(argv)
    if args.cmd == "verify":
        return _cmd_verify(args)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
