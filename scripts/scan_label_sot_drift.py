#!/usr/bin/env python3
"""Deterministic gate: labels.json stays in parity with label-policy.toml.

Refs #2442 (Phase A). Label identity (name/description/color) is authored in
two places today: ``.github/label-policy.toml`` ``[[labels]]`` (the adopted
taxonomy design, a superset that also carries family/status/rename_from) and
``.github/labels.json`` (the live catalog ``apply-labels.yml`` reconciles to
GitHub). Nothing checked that the two agree, and they had already drifted: 15
shared labels carried a different ``description`` while colors matched.

Phase A stops that drift by making ``label-policy.toml`` the single authored SoT
for label identity and reconciling ``labels.json`` to it. This gate keeps them
from drifting again: every ``labels.json`` entry must match a ``[[labels]]``
entry in ``label-policy.toml`` by name, description, and color.

Five ``labels.json`` entries are sourced from ``scripts/_retro_labels.py``
instead of the policy file: the four ``retro:*`` feedback-loop constants
(``ALL_RETRO_LABELS``) plus ``type:retrospective``. That coupling is enforced by
``tests/test_retro_labels_in_sot.py``; those labels have no ``[[labels]]``
counterpart yet (their SoT home is decided later with #843/#972), so this gate
reads the exception set from ``_retro_labels`` rather than hardcoding it and
skips those entries. The 11 ``area:*`` labels declared only in ``[[labels]]``
(not yet in the live catalog) are out of scope here: the gate validates
``labels.json`` against the policy, not the reverse, so a policy-only label is
not a drift.

Invariant, for every ``labels.json`` entry that is not retro-sourced:
- a ``[[labels]]`` entry with the same ``name`` exists in ``label-policy.toml``,
  and its ``description`` and ``color`` match. A missing counterpart, or a
  description/color mismatch, fails the run.

Contract:
- Inputs: the ``verify`` subcommand; ``--repo-root`` (defaults to the repo root
  containing this script's parent).
- Outputs: ``::error file=<file>::`` annotations on stderr scoped to the file at
  fault; exit 0 when clean (prints ``OK``), exit 1 on any drift. A missing or
  malformed input file yields one such annotation, never a raw traceback.
- Failure policy: fails loud per CLAUDE.md section 4 (CI gate).

Tested by ``tests/test_scan_label_sot_drift.py``. Refs #2442, #972, #1121.
"""

from __future__ import annotations

import argparse
import json
import sys
import tomllib
from pathlib import Path
from typing import Any

import _retro_labels

REPO_ROOT = Path(__file__).resolve().parent.parent
LABELS_JSON_PATH = Path(".github/labels.json")
LABEL_POLICY_PATH = Path(".github/label-policy.toml")

# labels.json entries sourced from scripts/_retro_labels.py, not
# label-policy.toml. Mirrors tests/test_retro_labels_in_sot.py: the four
# retro:* feedback-loop constants plus type:retrospective (which is not a
# retro:* label so it is not in ALL_RETRO_LABELS, but shares the same
# prune-safety coupling to the JSON SoT). Both are read from the constant
# module so the exception set cannot drift from the retro registry, and no
# label literal is frozen in this scanned file.
RETRO_SOURCED_LABELS = frozenset(
    _retro_labels.ALL_RETRO_LABELS | {_retro_labels.TYPE_RETROSPECTIVE}
)


def load_json(path: Path) -> Any:
    """Parse a JSON file."""
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_toml(path: Path) -> dict[str, Any]:
    """Parse a TOML file into a dictionary."""
    with path.open("rb") as handle:
        return tomllib.load(handle)


def _err(message: str, file: Path = LABELS_JSON_PATH) -> str:
    """Format a GitHub annotation scoped to the file at fault."""
    return f"::error file={file.as_posix()}::{message}"


def index_policy_labels(policy: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], str | None]:
    """Return ``({name: entry}, diagnostic)`` for ``label-policy.toml`` ``[[labels]]``.

    The diagnostic is non-None only when the ``[[labels]]`` array is
    structurally malformed (not a list); the map is empty in that case. Entries
    without a string ``name`` are skipped rather than indexed: their structural
    validity is owned by other gates (``scan_commit_type_label_drift``,
    ``scan_ssot_schema``), and a ``labels.json`` entry expecting one will still
    surface here as a missing counterpart.
    """
    labels_raw = policy.get("labels", [])
    if not isinstance(labels_raw, list):
        return {}, _err("label-policy.toml [[labels]] must be an array of tables", LABEL_POLICY_PATH)
    index: dict[str, dict[str, Any]] = {}
    for entry in labels_raw:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        if isinstance(name, str) and name:
            index[name] = entry
    return index, None


def verify_parity(catalog: Any, policy: dict[str, Any]) -> list[str]:
    """Return drift diagnostics between ``labels.json`` and policy ``[[labels]]``."""
    if not isinstance(catalog, list):
        return [_err("labels.json must be a JSON array of label objects")]

    policy_index, diagnostic = index_policy_labels(policy)
    if diagnostic is not None:
        return [diagnostic]

    errors: list[str] = []
    for entry in catalog:
        if not isinstance(entry, dict):
            errors.append(_err(f"labels.json entry is not an object: {entry!r}"))
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            errors.append(_err(f"labels.json entry is missing a string 'name' (got {name!r})"))
            continue

        # Sourced from scripts/_retro_labels.py, not label-policy.toml.
        if name in RETRO_SOURCED_LABELS:
            continue

        policy_entry = policy_index.get(name)
        if policy_entry is None:
            errors.append(
                _err(
                    f"label {name!r} is in labels.json but has no [[labels]] entry in "
                    "label-policy.toml; add it to the policy (the single label SoT), or, "
                    "if it is a retrospective label, to scripts/_retro_labels.py"
                )
            )
            continue

        if entry.get("description") != policy_entry.get("description"):
            errors.append(
                _err(
                    f"label {name!r} description drifts from label-policy.toml: "
                    f"labels.json={entry.get('description')!r} "
                    f"policy={policy_entry.get('description')!r}; label-policy.toml is the "
                    "SoT, so update labels.json to match."
                )
            )
        if entry.get("color") != policy_entry.get("color"):
            errors.append(
                _err(
                    f"label {name!r} color drifts from label-policy.toml: "
                    f"labels.json={entry.get('color')!r} policy={policy_entry.get('color')!r}; "
                    "label-policy.toml is the SoT, so update labels.json to match."
                )
            )

    return errors


def verify(root: Path = REPO_ROOT) -> list[str]:
    """Return every drift diagnostic for the repository at *root*.

    A missing, structurally malformed, or syntactically invalid input file
    yields a single ``::error`` annotation scoped to that file rather than an
    unhandled traceback, honoring the output contract for a CI gate.
    """
    root = root.resolve()
    catalog_file = root / LABELS_JSON_PATH
    policy_file = root / LABEL_POLICY_PATH
    if not catalog_file.exists():
        return [_err(f"catalog file {LABELS_JSON_PATH.as_posix()} not found")]
    if not policy_file.exists():
        return [_err(f"policy file {LABEL_POLICY_PATH.as_posix()} not found", LABEL_POLICY_PATH)]
    try:
        catalog = load_json(catalog_file)
    except json.JSONDecodeError as exc:
        return [_err(f"labels.json is not valid JSON: {exc}")]
    try:
        policy = load_toml(policy_file)
    except tomllib.TOMLDecodeError as exc:
        return [_err(f"label-policy.toml is not valid TOML: {exc}", LABEL_POLICY_PATH)]
    return verify_parity(catalog, policy)


def main(argv: list[str] | None = None) -> int:
    """CLI entrypoint.

    ``verify`` is the only subcommand and is ``required``; argparse rejects any
    other token with exit code 2 before this body runs, so there is no manual
    unknown-command branch to maintain.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    p_verify = sub.add_parser("verify", help="verify labels.json matches label-policy.toml")
    p_verify.add_argument("--repo-root", default=str(REPO_ROOT))
    args = parser.parse_args(argv)

    errors = verify(Path(args.repo_root))
    for error in errors:
        print(error, file=sys.stderr)
    if errors:
        return 1
    print("OK: labels.json is in parity with label-policy.toml [[labels]].")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
