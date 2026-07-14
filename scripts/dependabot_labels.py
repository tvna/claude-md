#!/usr/bin/env python3
"""Verify every label string in ``.github/dependabot.yml`` is defined in the
label catalog derived from ``.github/label-policy.toml`` (the single label SoT).

Closes the deterministic gate gap that produced #138: Dependabot's
``The following labels could not be found: 'dependencies'`` comment on
every PR (reproducer: PR #119) stemmed from a label referenced in
``dependabot.yml`` but missing from the label catalog.

The label identity SoT is ``.github/label-policy.toml`` ``[[labels]]``
(Refs #2499, #2442); the defined names are derived via
``labels_apply.load_sot_from_policy`` (``status in {keep, rename}``). The
old ``.github/labels.json`` reader was retired once every consumer read the
policy directly.

Avoids a PyYAML dependency by parsing the narrow subset of YAML used
by Dependabot's ``labels:`` list: a key named exactly ``labels`` at
any indent, followed by a contiguous run of ``- value`` items at a
deeper indent. Inline comments and ``#`` characters inside label
values are NOT supported; the repo's label names contain no
``#``, and Dependabot's schema has no inline-comment idiom here.

Exit codes:
* 0; every label reference resolves in the SoT.
* 1; at least one drift found, or a file is missing/malformed.

Tested by ``tests/test_dependabot_labels.py``. CLAUDE.md section 3
(deterministic harness in CI).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import labels_apply


def parse_dependabot_labels(yaml_text: str) -> list[str]:
    """Return every label string under any ``labels:`` block in *yaml_text*.

    The parser is intentionally narrow: it recognises a line whose
    stripped content is exactly ``labels:`` and collects subsequent
    list items (``- value``) that are indented deeper than the
    ``labels:`` line itself. The block ends at the first non-blank
    line whose indent is less than or equal to the ``labels:`` line.

    Order is preserved across blocks and duplicates are kept; callers
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


def load_sot_label_names_from_policy(policy_path: Path) -> set[str]:
    """Return the live label name set, derived from label-policy.toml.

    Delegates to :func:`labels_apply.load_sot_from_policy` (the ``status in
    {keep, rename}`` catalog) so this gate reads the single authored label SoT
    rather than a second copy.
    """
    catalog = labels_apply.load_sot_from_policy(policy_path)
    return {str(entry["name"]) for entry in catalog}


def find_drift(referenced: list[str], defined: set[str]) -> list[str]:
    """Return sorted-unique labels in *referenced* but not in *defined*."""
    return sorted({label for label in referenced if label not in defined})


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def _cmd_verify(args: argparse.Namespace) -> int:
    dependabot_path = Path(args.dependabot)
    label_policy_path = Path(args.label_policy)

    if not dependabot_path.is_file():
        print(f"::error::dependabot file not found: {dependabot_path}")
        return 1
    if not label_policy_path.is_file():
        print(f"::error::label policy not found: {label_policy_path}")
        return 1

    try:
        referenced = parse_dependabot_labels(
            dependabot_path.read_text(encoding="utf-8")
        )
        defined = load_sot_label_names_from_policy(label_policy_path)
    except (OSError, ValueError) as error:
        print(f"::error::{error}")
        return 1

    drift = find_drift(referenced, defined)
    if drift:
        for name in drift:
            print(
                f"::error file={dependabot_path}::"
                f"Label '{name}' referenced in {dependabot_path} "
                f"is not defined in {label_policy_path}."
            )
        print(
            f"::error::Dependabot label drift: {len(drift)} label(s) "
            f"missing from {label_policy_path}. Add them to the policy (then run "
            f"apply-labels.yml workflow_dispatch) or remove them from "
            f"{dependabot_path}. See #138."
        )
        return 1

    print(
        f"OK: {len(set(referenced))} unique label(s) from "
        f"{dependabot_path} all resolve in {label_policy_path}."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Verify every label in dependabot.yml is defined in label-policy.toml.",
    )
    p_verify.add_argument(
        "--dependabot",
        default=".github/dependabot.yml",
        help="Path to dependabot.yml (default: .github/dependabot.yml).",
    )
    p_verify.add_argument(
        "--label-policy",
        default=".github/label-policy.toml",
        help="Path to label-policy.toml (default: .github/label-policy.toml).",
    )
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
