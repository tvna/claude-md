#!/usr/bin/env python3
"""Verify every label string in ``.github/dependabot.yml`` is defined in
``.github/labels.json`` (the labels source of truth).

Closes the deterministic gate gap that produced #138: Dependabot's
``The following labels could not be found: 'dependencies'`` comment on
every PR (reproducer: PR #119) stemmed from a label referenced in
``dependabot.yml`` but missing from ``labels.json``.

Avoids a PyYAML dependency by parsing the narrow subset of YAML used
by Dependabot's ``labels:`` list: a key named exactly ``labels`` at
any indent, followed by a contiguous run of ``- value`` items at a
deeper indent. Inline comments and ``#`` characters inside label
values are NOT supported -- the repo's labels.json names contain no
``#``, and Dependabot's schema has no inline-comment idiom here.

Exit codes:
* 0 -- every label reference resolves in the SoT.
* 1 -- at least one drift found, or a file is missing/malformed.

Tested by ``tests/test_dependabot_labels.py``. CLAUDE.md section 3
(deterministic harness in CI).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def parse_dependabot_labels(yaml_text: str) -> list[str]:
    """Return every label string under any ``labels:`` block in *yaml_text*.

    The parser is intentionally narrow: it recognises a line whose
    stripped content is exactly ``labels:`` and collects subsequent
    list items (``- value``) that are indented deeper than the
    ``labels:`` line itself. The block ends at the first non-blank
    line whose indent is less than or equal to the ``labels:`` line.

    Order is preserved across blocks and duplicates are kept -- callers
    that want unique references should deduplicate.
    """
    labels: list[str] = []
    in_block = False
    block_indent = -1

    for raw_line in yaml_text.splitlines():
        stripped = raw_line.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw_line) - len(stripped)

        if in_block:
            if indent > block_indent and stripped.startswith("- "):
                labels.append(_unquote(stripped[2:].strip()))
                continue
            if indent <= block_indent:
                in_block = False
                # Fall through: this line may itself open a new block.

        if not in_block and stripped == "labels:":
            in_block = True
            block_indent = indent

    return labels


def load_sot_label_names(json_text: str) -> set[str]:
    """Return the set of ``name`` fields from a labels.json document."""
    data = json.loads(json_text)
    if not isinstance(data, list):
        raise ValueError("labels.json must be a JSON array")
    names: set[str] = set()
    for entry in data:
        if not isinstance(entry, dict):
            raise ValueError("labels.json entries must be objects")
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            raise ValueError("labels.json entry missing non-empty 'name'")
        names.add(name)
    return names


def find_drift(referenced: list[str], defined: set[str]) -> list[str]:
    """Return sorted-unique labels in *referenced* but not in *defined*."""
    return sorted({label for label in referenced if label not in defined})


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def _cmd_verify(args: argparse.Namespace) -> int:
    dependabot_path = Path(args.dependabot)
    labels_path = Path(args.labels)

    if not dependabot_path.is_file():
        print(f"::error::dependabot file not found: {dependabot_path}")
        return 1
    if not labels_path.is_file():
        print(f"::error::labels SoT not found: {labels_path}")
        return 1

    try:
        referenced = parse_dependabot_labels(
            dependabot_path.read_text(encoding="utf-8")
        )
        defined = load_sot_label_names(labels_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"::error::{error}")
        return 1

    drift = find_drift(referenced, defined)
    if drift:
        for name in drift:
            print(
                f"::error file={dependabot_path}::"
                f"Label '{name}' referenced in {dependabot_path} "
                f"is not defined in {labels_path}."
            )
        print(
            f"::error::Dependabot label drift: {len(drift)} label(s) "
            f"missing from {labels_path}. Add them to the SoT (then run "
            f"apply-labels.yml workflow_dispatch) or remove them from "
            f"{dependabot_path}. See #138."
        )
        return 1

    print(
        f"OK: {len(set(referenced))} unique label(s) from "
        f"{dependabot_path} all resolve in {labels_path}."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Verify every label in dependabot.yml is defined in labels.json.",
    )
    p_verify.add_argument(
        "--dependabot",
        default=".github/dependabot.yml",
        help="Path to dependabot.yml (default: .github/dependabot.yml).",
    )
    p_verify.add_argument(
        "--labels",
        default=".github/labels.json",
        help="Path to labels SoT JSON (default: .github/labels.json).",
    )
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
