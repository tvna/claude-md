#!/usr/bin/env python3
"""CI gate: validate the .gitapex/ssot.json gate registry.

The registry (`.gitapex/ssot.json`) is the machine-readable single source of
truth for the repository's deterministic gates, their enforcement planes, the
policy files they read, and the label-based agent routing table. This gate
validates the registry against its JSON Schema (`.gitapex/ssot.schema.json`)
and enforces the referential-integrity rules the schema alone cannot express.

Shape validation walks the schema (a draft-2020-12 subset: ``type``, ``enum``,
``required``, ``properties``, ``additionalProperties``, ``items``, ``minItems``,
and ``$ref`` into ``$defs``), so the schema is the single source for every
shape constraint and the validator cannot drift from it. An extra property, a
wrong scalar type, a non-object array element, or an empty required array is
therefore rejected.

Referential-integrity checks (which JSON Schema cannot express) then enforce:

- every ``policy_sources[].path``, ``gates[].script``, and
  ``label_consumers[].path`` resolves to a tracked file;
- every ``gates[].policy_refs[]`` names an existing ``policy_sources[].id``;
- every non-null ``gates[].cluster`` names an existing ``clusters[].id``;
- every label in ``label_routing`` resolves against the live catalog
  ``.github/labels.json`` ONLY (a renamed-away or retired name would validate
  but never match, silently falling through to the default route);
- every label in ``label_consumers`` resolves against ``.github/labels.json``
  unioned with the ``rename_from`` and ``retired_labels`` tables of
  ``.github/label-policy.toml`` (a legacy name may legitimately be recorded
  mid-migration);
- ``gates[].kind`` ``script`` carries ``script`` (and no ``native_rule``),
  ``native`` carries ``native_rule`` (and no ``script``);
- ``label_routing.rules`` has exactly one ``default`` rule, last.

Architecture: pure functions on top (:func:`verify_registry` and its
``_check_*`` helpers), a single ``git`` subprocess boundary in
:func:`build_tracked_checker`, and a ``main()`` entrypoint at the bottom. The
draft-2020-12 subset engine (schema-shape validation) lives in the shared
``scripts/_json_schema_subset.py`` (#2342), reused by ``scan_gitapex_schema.py``.

Contract:
- Inputs: the ``verify`` subcommand; ``--registry`` (default
  ``.gitapex/ssot.json``); ``--schema`` (default ``.gitapex/ssot.schema.json``);
  ``--labels`` (default ``.github/labels.json``); ``--label-policy`` (default
  ``.github/label-policy.toml``).
- Outputs: ``::error::`` annotations on stderr, one per violation; an ``OK:``
  line on success; exit 0 when the registry validates, exit 1 on any
  violation, exit 64 on an unrecognised subcommand.
- Failure policy: fails loud (exit 1) per CLAUDE.md section 4; it is a CI gate,
  so any unexpected input, missing file, or schema drift exits non-zero.

Tested by ``tests/test_scan_ssot_schema.py``. Refs #2252, #2246.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tomllib
from collections.abc import Callable
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import labels_apply
from _json_schema_subset import SchemaError, validate_shape

_SCRIPT = "scan_ssot_schema"
_REPO_ROOT = Path(__file__).resolve().parent.parent
_REGISTRY_PATH = ".gitapex/ssot.json"
_SCHEMA_PATH = ".gitapex/ssot.schema.json"
_LABELS_PATH = ".github/labels.json"
_LABEL_POLICY_PATH = ".github/label-policy.toml"


# ---------------------------------------------------------------------------
# Loading helpers (pure, over already-parsed data)
# ---------------------------------------------------------------------------


def live_label_names(labels_data: object) -> frozenset[str]:
    """Return the set of label names in the live catalog (``labels.json``)."""
    if not isinstance(labels_data, list):
        return frozenset()
    return frozenset(
        entry["name"]
        for entry in labels_data
        if isinstance(entry, dict) and isinstance(entry.get("name"), str)
    )


def live_label_names_from_policy(policy_path: Path) -> frozenset[str]:
    """Return the live catalog's label names, derived from label-policy.toml.

    Delegates to :func:`labels_apply.load_sot_from_policy` (added in #2442
    Phase B batch 1) instead of re-deriving the keep/rename logic here a
    second time. Not wired into the production CLI path by default; see the
    ``--source`` flag on :func:`main`.
    """
    catalog = labels_apply.load_sot_from_policy(policy_path)
    return frozenset(str(entry["name"]) for entry in catalog)


def consumer_label_universe(
    live: frozenset[str], label_policy: object
) -> frozenset[str]:
    """Return live labels unioned with the rename_from and retired names.

    ``label_consumers`` may legitimately record a legacy label name while a
    rename or retirement migration is in flight, so the union is what keeps a
    stale consumer reference detectable instead of silently accepted.
    """
    extra: set[str] = set()
    if isinstance(label_policy, dict):
        for entry in label_policy.get("labels", []) or []:
            if isinstance(entry, dict) and isinstance(entry.get("rename_from"), str):
                extra.add(entry["rename_from"])
        for entry in label_policy.get("retired_labels", []) or []:
            if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                extra.add(entry["name"])
    return live | frozenset(extra)


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


# ---------------------------------------------------------------------------
# Schema-shape precondition (registry-specific; the subset engine itself is
# shared, see scripts/_json_schema_subset.py)
# ---------------------------------------------------------------------------


def _assert_schema_shape(schema: object) -> None:
    """Raise :class:`SchemaError` if the schema lacks structures the gate needs.

    Guards against silently accepting a truncated or empty schema (which would
    impose no constraints and let malformed registry data pass).
    """
    if not isinstance(schema, dict):
        raise SchemaError("schema root is not a JSON object")
    defs = schema.get("$defs")
    props = schema.get("properties")
    if not isinstance(defs, dict) or not isinstance(props, dict):
        raise SchemaError("schema is missing '$defs' or 'properties'")
    for name in ("plane", "gate_kind", "body_read"):
        node = defs.get(name)
        if not isinstance(node, dict) or not isinstance(node.get("enum"), list):
            raise SchemaError(f"schema is missing the '$defs.{name}.enum' list")
    if not isinstance(schema.get("required"), list):
        raise SchemaError("schema is missing the top-level 'required' list")


# ---------------------------------------------------------------------------
# Referential-integrity checks (pure; JSON Schema cannot express these)
# ---------------------------------------------------------------------------


def _check_gate_kinds(registry: dict[str, object]) -> list[str]:
    errors: list[str] = []
    for i, gate in enumerate(_as_list(registry.get("gates"))):
        if not isinstance(gate, dict):
            continue
        gid = gate.get("id")
        kind = gate.get("kind")
        if kind == "script":
            if not gate.get("script"):
                errors.append(f"gates[{i}] ({gid!r}): kind 'script' requires a 'script' path")
            if gate.get("native_rule"):
                errors.append(f"gates[{i}] ({gid!r}): kind 'script' must not carry 'native_rule'")
        elif kind == "native":
            if not gate.get("native_rule"):
                errors.append(f"gates[{i}] ({gid!r}): kind 'native' requires a 'native_rule'")
            if gate.get("script"):
                errors.append(f"gates[{i}] ({gid!r}): kind 'native' must not carry 'script'")
    return errors


def _check_tracked_paths(
    registry: dict[str, object], is_tracked: Callable[[str], bool]
) -> list[str]:
    errors: list[str] = []
    for i, ps in enumerate(_as_list(registry.get("policy_sources"))):
        if isinstance(ps, dict) and isinstance(ps.get("path"), str) and not is_tracked(ps["path"]):
            errors.append(f"policy_sources[{i}] ({ps.get('id')!r}): path {ps['path']!r} is not a tracked file")
    for i, gate in enumerate(_as_list(registry.get("gates"))):
        if not isinstance(gate, dict):
            continue
        script = gate.get("script")
        if isinstance(script, str) and not is_tracked(script):
            errors.append(f"gates[{i}] ({gate.get('id')!r}): script {script!r} is not a tracked file")
    for i, con in enumerate(_as_list(registry.get("label_consumers"))):
        if isinstance(con, dict) and isinstance(con.get("path"), str) and not is_tracked(con["path"]):
            errors.append(f"label_consumers[{i}]: path {con['path']!r} is not a tracked file")
    return errors


def _check_id_refs(registry: dict[str, object]) -> list[str]:
    errors: list[str] = []
    source_ids = {
        ps["id"]
        for ps in _as_list(registry.get("policy_sources"))
        if isinstance(ps, dict) and isinstance(ps.get("id"), str)
    }
    cluster_ids = {
        cl["id"]
        for cl in _as_list(registry.get("clusters"))
        if isinstance(cl, dict) and isinstance(cl.get("id"), str)
    }
    for i, gate in enumerate(_as_list(registry.get("gates"))):
        if not isinstance(gate, dict):
            continue
        gid = gate.get("id")
        for ref in _as_list(gate.get("policy_refs")):
            if ref not in source_ids:
                errors.append(f"gates[{i}] ({gid!r}): policy_ref {ref!r} names no policy_sources[].id")
        cluster = gate.get("cluster")
        if cluster is not None and cluster not in cluster_ids:
            errors.append(f"gates[{i}] ({gid!r}): cluster {cluster!r} names no clusters[].id")
    return errors


def _routing_labels(routing: dict[str, object]) -> list[str]:
    labels: list[str] = []
    for rule in _as_list(routing.get("rules")):
        if not isinstance(rule, dict):
            continue
        for key in ("if_any", "if_all", "if_none"):
            labels.extend(v for v in _as_list(rule.get(key)) if isinstance(v, str))
    return labels


def _check_routing(registry: dict[str, object], live_labels: frozenset[str]) -> list[str]:
    routing = registry.get("label_routing")
    if not isinstance(routing, dict):
        return []  # shape validation already reported the type mismatch

    errors: list[str] = []
    for label in _routing_labels(routing):
        if label not in live_labels:
            errors.append(
                f"label_routing: label {label!r} does not resolve against the live "
                f"catalog {_LABELS_PATH}"
            )

    rules = _as_list(routing.get("rules"))
    default_indexes = [
        i for i, rule in enumerate(rules) if isinstance(rule, dict) and rule.get("default") is True
    ]
    if len(default_indexes) != 1:
        errors.append(
            f"label_routing.rules: expected exactly one default rule, found {len(default_indexes)}"
        )
    elif default_indexes[0] != len(rules) - 1:
        errors.append("label_routing.rules: the default rule must be last")
    return errors


def _check_consumers(
    registry: dict[str, object], consumer_labels: frozenset[str]
) -> list[str]:
    errors: list[str] = []
    for i, con in enumerate(_as_list(registry.get("label_consumers"))):
        if not isinstance(con, dict):
            continue
        for field in ("labels", "discovery_only_labels"):
            for label in _as_list(con.get(field)):
                if label not in consumer_labels:
                    errors.append(
                        f"label_consumers[{i}] ({con.get('path')!r}): {field} label "
                        f"{label!r} does not resolve against {_LABELS_PATH} unioned "
                        f"with the label-policy rename_from and retired tables"
                    )
    return errors


def verify_registry(
    registry: object,
    schema: object,
    is_tracked: Callable[[str], bool],
    live_labels: frozenset[str],
    consumer_labels: frozenset[str],
) -> list[str]:
    """Return the list of violation messages; empty means the registry is valid."""
    _assert_schema_shape(schema)
    assert isinstance(schema, dict)  # noqa: S101 -- narrowed by _assert_schema_shape

    errors = validate_shape(registry, schema, root_path="registry")
    if not isinstance(registry, dict):
        return errors  # shape validation reported the root type mismatch

    errors += _check_gate_kinds(registry)
    errors += _check_tracked_paths(registry, is_tracked)
    errors += _check_id_refs(registry)
    errors += _check_routing(registry, live_labels)
    errors += _check_consumers(registry, consumer_labels)
    return errors


# ---------------------------------------------------------------------------
# IO boundary
# ---------------------------------------------------------------------------


def build_tracked_checker(repo_root: Path) -> Callable[[str], bool]:
    """Return a predicate reporting whether a repo-relative path is tracked.

    Uses a single ``git ls-files`` call; if git is unavailable the predicate
    degrades to an on-disk file check so the gate still runs (a governed file
    must exist in the working tree to be committed).
    """
    tracked: frozenset[str] | None = None
    try:
        completed = subprocess.run(  # noqa: S603 -- fixed argv, shell=False
            ["git", "-C", str(repo_root), "ls-files"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=30,
        )
        if completed.returncode == 0:
            tracked = frozenset(
                line.strip() for line in completed.stdout.splitlines() if line.strip()
            )
    except (OSError, subprocess.SubprocessError):
        tracked = None

    def is_tracked(path: str) -> bool:
        if tracked is not None:
            return path in tracked
        return (repo_root / path).is_file()

    return is_tracked


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    command = argv[0] if argv else None
    if command != "verify":
        print(
            f"::error::{_SCRIPT}: unknown subcommand {command!r}; expected 'verify'.",
            file=sys.stderr,
        )
        return 64

    parser = argparse.ArgumentParser(
        description="Validate .gitapex/ssot.json against its schema and referential rules."
    )
    parser.add_argument("command", help="Must be 'verify'.")
    parser.add_argument("--registry", default=_REGISTRY_PATH)
    parser.add_argument("--schema", default=_SCHEMA_PATH)
    parser.add_argument("--labels", default=_LABELS_PATH)
    parser.add_argument("--label-policy", default=_LABEL_POLICY_PATH)
    parser.add_argument(
        "--source",
        choices=["labels-json", "label-policy"],
        default="labels-json",
        help=(
            "Which file supplies the live label names for the label_routing/"
            "label_consumers checks. Default labels-json preserves current "
            "behavior; label-policy derives names from label-policy.toml "
            "[[labels]] instead (Refs #2442 Phase B batch 2; not the "
            "production default yet)."
        ),
    )
    args = parser.parse_args(argv)

    registry_path = _REPO_ROOT / args.registry
    schema_path = _REPO_ROOT / args.schema
    labels_path = _REPO_ROOT / args.labels
    label_policy_path = _REPO_ROOT / args.label_policy

    for label, path in (
        ("registry", registry_path),
        ("schema", schema_path),
        ("labels", labels_path),
        ("label-policy", label_policy_path),
    ):
        if not path.exists():
            print(f"::error::{_SCRIPT}: {label} file not found at {path}.", file=sys.stderr)
            return 1

    try:
        registry = _load_json(registry_path)
        schema = _load_json(schema_path)
        labels_data = _load_json(labels_path)
        label_policy = tomllib.loads(label_policy_path.read_text(encoding="utf-8"))
        if args.source == "label-policy":
            live_labels = live_label_names_from_policy(label_policy_path)
        else:
            live_labels = live_label_names(labels_data)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        print(f"::error::{_SCRIPT}: cannot parse an input file: {exc}", file=sys.stderr)
        return 1

    consumer_labels = consumer_label_universe(live_labels, label_policy)
    is_tracked = build_tracked_checker(_REPO_ROOT)

    try:
        errors = verify_registry(registry, schema, is_tracked, live_labels, consumer_labels)
    except SchemaError as exc:
        print(f"::error::{_SCRIPT}: {exc}", file=sys.stderr)
        return 1

    if errors:
        for message in errors:
            print(f"::error::{_SCRIPT}: {message}", file=sys.stderr)
        return 1

    print(f"OK: {_SCRIPT}: {args.registry} validates against {args.schema}.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
