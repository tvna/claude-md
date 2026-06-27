#!/usr/bin/env python3
"""Deterministic gate: type:* labels stay aligned with title-policy commit types.

Refs #2081. The canonical commit-type list lives once in
``.github/title-policy.toml`` ``[title_policy].types``. ``.github/label-policy.toml``
declares a ``type:*`` label family that is an intentional partial projection of
that list (not every commit type gets a label). Nothing checked that a ``type:*``
label whose stem is not a real commit type (a typo, or a label kept after a
commit type was removed or renamed) could not ship.

This gate fails loudly when the two disagree. The one intentional exception,
``type:tracking`` (a tracking-issue label with no commit-type counterpart), is
declared in the policy file itself with ``commit_type = false`` so the allowlist
is single-sourced and cannot drift from a hardcoded script constant.

Invariants, for every label:
- (a) Subset: a ``family == "type"`` label with ``commit_type != false`` must
  have its stem (after ``type:``) present in ``title-policy.toml`` ``types``.
- (b) Marker integrity: ``commit_type = false`` must NOT be set on a stem that
  IS a commit type (guards against wrongly exempting a real type).
- (c) Key placement: the ``commit_type`` key is only valid on ``type`` labels.
- (d) Type check: when present, ``commit_type`` must be a boolean.
- (e) Prefix: a ``family == "type"`` label name must start with ``type:`` so a
  prefix-less name cannot pose as its own stem and slip past (a).
- (f) Name shape: a ``family == "type"`` label must carry a string ``name`` so a
  malformed entry cannot skip every check above unobserved.

Contract:
- Inputs: the ``verify`` subcommand; ``--repo-root`` (defaults to the repo root
  containing this script's parent).
- Outputs: ``::error file=<policy file>::`` annotations on stderr scoped to the
  file actually at fault; exit 0 when clean (prints ``OK``), exit 1 on any
  violation. A structurally or syntactically malformed policy file yields one
  such annotation, never a raw traceback.
- Failure policy: fails loud per CLAUDE.md section 4 (CI gate).

Tested by ``tests/test_scan_commit_type_label_drift.py``. Refs #2081, #1984.
"""

from __future__ import annotations

import argparse
import sys
import tomllib
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
LABEL_POLICY_PATH = Path(".github/label-policy.toml")
TITLE_POLICY_PATH = Path(".github/title-policy.toml")
_TYPE_PREFIX = "type:"


def load_toml(path: Path) -> dict[str, Any]:
    """Parse a TOML file into a dictionary."""
    with path.open("rb") as handle:
        return tomllib.load(handle)


def parse_commit_types(title_policy: dict[str, Any]) -> tuple[set[str], str | None]:
    """Return ``(commit-type set, diagnostic)`` from a title-policy dict.

    The diagnostic is a non-None message when the ``[title_policy]`` table is
    structurally malformed (the set is empty in that case); otherwise it is
    ``None`` and the set holds every non-empty string commit type. Pairing the
    two in one traversal keeps the structural contract single-sourced here.
    """
    policy = title_policy.get("title_policy")
    if not isinstance(policy, dict):
        return set(), "title-policy.toml is missing the [title_policy] table or it is not a table"
    types = policy.get("types", [])
    if not isinstance(types, list):
        return set(), "title-policy.toml [title_policy].types is not a list"
    return {item for item in types if isinstance(item, str) and item}, None


def _err(message: str, file: Path = LABEL_POLICY_PATH) -> str:
    """Format a GitHub annotation scoped to the policy *file* at fault."""
    return f"::error file={file.as_posix()}::{message}"


def verify_policy(label_policy: dict[str, Any], title_policy: dict[str, Any]) -> list[str]:
    """Return drift diagnostics between type:* labels and commit types."""
    types, malformed = parse_commit_types(title_policy)
    if malformed is not None:
        return [_err(malformed, TITLE_POLICY_PATH)]

    labels_raw = label_policy.get("labels", [])
    if not isinstance(labels_raw, list):
        return [_err("label-policy.toml [[labels]] must be an array of tables")]

    errors: list[str] = []
    for label in (entry for entry in labels_raw if isinstance(entry, dict)):
        name = label.get("name")
        family = label.get("family")
        has_marker = "commit_type" in label
        marker = label.get("commit_type")

        # (c) the commit_type key is only valid on type:* labels.
        if has_marker and family != "type":
            label_id = name if isinstance(name, str) else "<unnamed>"
            errors.append(
                _err(
                    f"label {label_id} sets commit_type but family is {family!r}; the "
                    "commit_type marker is only valid on type:* labels"
                )
            )
            continue

        if family != "type":
            continue

        # (f) a type-family label must carry a string name; without this a
        # malformed entry would skip (d), (e), (a), and (b) unobserved.
        if not isinstance(name, str):
            errors.append(_err(f"type-family label is missing a string 'name' (got {name!r})"))
            continue

        # (d) when present, commit_type must be a boolean.
        if has_marker and not isinstance(marker, bool):
            errors.append(_err(f"type label {name} commit_type must be a boolean, got {marker!r}"))
            continue

        # (e) a type-family label must carry the type: prefix. Without this the
        # else-branch below would treat a prefix-less name (e.g. "feat") as its
        # own stem and silently pass, missing the taxonomy drift the gate exists
        # to catch; issue triage and tracking helpers identify type labels by
        # the prefix.
        if not name.startswith(_TYPE_PREFIX):
            errors.append(
                _err(
                    f"type-family label {name!r} must start with {_TYPE_PREFIX!r}; issue "
                    "triage and tracking helpers identify type labels by that prefix"
                )
            )
            continue

        stem = name[len(_TYPE_PREFIX):]

        if marker is False:
            # (b) a declared non-commit type:* label must not name a real type.
            if stem in types:
                errors.append(
                    _err(
                        f"type label {name} sets commit_type = false but {stem!r} IS a commit "
                        "type in .github/title-policy.toml; remove the commit_type marker"
                    )
                )
        else:
            # (a) a commit-type label's stem must be a real commit type.
            if stem not in types:
                errors.append(
                    _err(
                        f"type label {name} has stem {stem!r} that is not a commit type in "
                        ".github/title-policy.toml; add it to [title_policy].types or set "
                        "commit_type = false"
                    )
                )

    return errors


def verify(root: Path = REPO_ROOT) -> list[str]:
    """Return every drift diagnostic for the repository at *root*.

    A missing, structurally malformed, or syntactically invalid policy file
    yields a single ``::error`` annotation scoped to that file rather than an
    unhandled traceback, honoring the output contract for a CI gate.
    """
    root = root.resolve()
    label_file = root / LABEL_POLICY_PATH
    title_file = root / TITLE_POLICY_PATH
    if not label_file.exists():
        return [_err(f"policy file {LABEL_POLICY_PATH.as_posix()} not found")]
    if not title_file.exists():
        return [_err(f"policy file {TITLE_POLICY_PATH.as_posix()} not found", TITLE_POLICY_PATH)]
    try:
        label_policy = load_toml(label_file)
    except tomllib.TOMLDecodeError as exc:
        return [_err(f"label-policy.toml is not valid TOML: {exc}")]
    try:
        title_policy = load_toml(title_file)
    except tomllib.TOMLDecodeError as exc:
        return [_err(f"title-policy.toml is not valid TOML: {exc}", TITLE_POLICY_PATH)]
    return verify_policy(label_policy, title_policy)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint.

    ``verify`` is the only subcommand and is ``required``; argparse rejects any
    other token with exit code 2 before this body runs, so there is no manual
    unknown-command branch to maintain.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_verify = sub.add_parser("verify", help="verify type:* labels match commit types")
    p_verify.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)

    errors = verify(Path(args.repo_root))
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print("OK: every type:* label maps to a commit type or a declared exception.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
