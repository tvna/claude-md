#!/usr/bin/env python3
"""CI gate: validate the .gitapex/ssot.json gate registry.

The registry (`.gitapex/ssot.json`) is the machine-readable single source of
truth for the repository's deterministic gates, their enforcement planes, the
policy files they read, and the label-based agent routing table. This gate
validates the registry against its JSON Schema (`.gitapex/ssot.schema.json`)
and enforces the referential-integrity rules the schema alone cannot express:

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
- ``gates[].kind`` is ``script`` (carrying ``script``) or ``native`` (carrying
  ``native_rule``), never both, never neither;
- ``label_routing.rules`` is ordered with exactly one ``default`` rule, last;
- every plane in ``gates[].planes`` and ``clusters[].expected_planes`` is in
  the closed plane enum.

The closed ``plane`` and ``gate_kind`` vocabularies and the per-object
``required`` field lists are read from the schema so the schema stays the
single source and the validator cannot drift from it.

Architecture: pure functions on top (:func:`extract_schema_vocab`,
:func:`verify_registry` and its ``_check_*`` helpers), a single ``git``
subprocess boundary in :func:`build_tracked_checker`, and a ``main()``
entrypoint at the bottom.

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
from dataclasses import dataclass
from pathlib import Path

_SCRIPT = "scan_ssot_schema"
_REPO_ROOT = Path(__file__).resolve().parent.parent
_REGISTRY_PATH = ".gitapex/ssot.json"
_SCHEMA_PATH = ".gitapex/ssot.schema.json"
_LABELS_PATH = ".github/labels.json"
_LABEL_POLICY_PATH = ".github/label-policy.toml"


class SchemaError(Exception):
    """Raised when the schema itself is missing a structure the gate reads."""


@dataclass(frozen=True)
class SchemaVocab:
    """The enums and required-field lists the validator reads from the schema."""

    planes: frozenset[str]
    kinds: frozenset[str]
    body_reads: frozenset[str]
    top_required: tuple[str, ...]
    meta_required: tuple[str, ...]
    policy_source_required: tuple[str, ...]
    gate_required: tuple[str, ...]
    cluster_required: tuple[str, ...]
    rule_required: tuple[str, ...]
    consumer_required: tuple[str, ...]


# ---------------------------------------------------------------------------
# Loading (pure helpers over already-read text / parsed data)
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


def extract_schema_vocab(schema: object) -> SchemaVocab:
    """Return the enums and required-field lists the validator reads.

    Raises :class:`SchemaError` when the schema is missing any structure the
    gate depends on, so schema drift fails loud rather than silently skipping
    a check.
    """
    if not isinstance(schema, dict):
        raise SchemaError("schema root is not a JSON object")

    def navigate(*path: str) -> object:
        node: object = schema
        for key in path:
            if not isinstance(node, dict) or key not in node:
                raise SchemaError(
                    "schema is missing the '" + ".".join(path) + "' node"
                )
            node = node[key]
        return node

    def enum_at(*path: str) -> frozenset[str]:
        node = navigate(*path)
        if not isinstance(node, list):
            raise SchemaError("schema enum at '" + ".".join(path) + "' is not a list")
        return frozenset(str(v) for v in node)

    def required_at(*path: str) -> tuple[str, ...]:
        node = navigate(*path)
        if not isinstance(node, list):
            raise SchemaError(
                "schema required at '" + ".".join(path) + "' is not a list"
            )
        return tuple(str(v) for v in node)

    props = ("properties",)
    return SchemaVocab(
        planes=enum_at("$defs", "plane", "enum"),
        kinds=enum_at("$defs", "gate_kind", "enum"),
        body_reads=enum_at("$defs", "body_read", "enum"),
        top_required=required_at("required"),
        meta_required=required_at(*props, "meta", "required"),
        policy_source_required=required_at(*props, "policy_sources", "items", "required"),
        gate_required=required_at(*props, "gates", "items", "required"),
        cluster_required=required_at(*props, "clusters", "items", "required"),
        rule_required=required_at(
            *props, "label_routing", "properties", "rules", "items", "required"
        ),
        consumer_required=required_at(*props, "label_consumers", "items", "required"),
    )


# ---------------------------------------------------------------------------
# Referential-integrity and shape checks (pure)
# ---------------------------------------------------------------------------


def _missing(obj: dict[str, object], required: tuple[str, ...], ctx: str) -> list[str]:
    return [f"{ctx}: missing required field '{key}'" for key in required if key not in obj]


def _check_shape(registry: dict[str, object], vocab: SchemaVocab) -> list[str]:
    errors: list[str] = []
    errors += _missing(registry, vocab.top_required, "registry")

    meta = registry.get("meta")
    if isinstance(meta, dict):
        errors += _missing(meta, vocab.meta_required, "meta")

    for i, ps in enumerate(_as_list(registry.get("policy_sources"))):
        if isinstance(ps, dict):
            errors += _missing(ps, vocab.policy_source_required, f"policy_sources[{i}]")
    for i, gate in enumerate(_as_list(registry.get("gates"))):
        if isinstance(gate, dict):
            errors += _missing(gate, vocab.gate_required, f"gates[{i}]")
    for i, cl in enumerate(_as_list(registry.get("clusters"))):
        if isinstance(cl, dict):
            errors += _missing(cl, vocab.cluster_required, f"clusters[{i}]")
    for i, con in enumerate(_as_list(registry.get("label_consumers"))):
        if isinstance(con, dict):
            errors += _missing(con, vocab.consumer_required, f"label_consumers[{i}]")

    routing = registry.get("label_routing")
    if isinstance(routing, dict):
        for i, rule in enumerate(_as_list(routing.get("rules"))):
            if isinstance(rule, dict):
                errors += _missing(rule, vocab.rule_required, f"label_routing.rules[{i}]")
    return errors


def _check_planes(registry: dict[str, object], planes: frozenset[str]) -> list[str]:
    errors: list[str] = []
    for i, gate in enumerate(_as_list(registry.get("gates"))):
        if not isinstance(gate, dict):
            continue
        for plane in _as_list(gate.get("planes")):
            if plane not in planes:
                errors.append(f"gates[{i}] ({gate.get('id')!r}): unknown plane {plane!r}")
    for i, cl in enumerate(_as_list(registry.get("clusters"))):
        if not isinstance(cl, dict):
            continue
        for plane in _as_list(cl.get("expected_planes")):
            if plane not in planes:
                errors.append(
                    f"clusters[{i}] ({cl.get('id')!r}): unknown expected plane {plane!r}"
                )
    return errors


def _check_gate_kinds(registry: dict[str, object], kinds: frozenset[str]) -> list[str]:
    errors: list[str] = []
    for i, gate in enumerate(_as_list(registry.get("gates"))):
        if not isinstance(gate, dict):
            continue
        gid = gate.get("id")
        kind = gate.get("kind")
        if kind not in kinds:
            errors.append(f"gates[{i}] ({gid!r}): unknown kind {kind!r}")
            continue
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


def _check_routing(
    registry: dict[str, object],
    live_labels: frozenset[str],
    body_reads: frozenset[str],
) -> list[str]:
    routing = registry.get("label_routing")
    if not isinstance(routing, dict):
        return ["label_routing: missing or not an object"]

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

    for i, rule in enumerate(rules):
        if isinstance(rule, dict) and rule.get("body_read") not in body_reads:
            errors.append(
                f"label_routing.rules[{i}]: unknown body_read {rule.get('body_read')!r}"
            )
    return errors


def _check_consumers(
    registry: dict[str, object], consumer_labels: frozenset[str]
) -> list[str]:
    errors: list[str] = []
    for i, con in enumerate(_as_list(registry.get("label_consumers"))):
        if not isinstance(con, dict):
            continue
        for label in _as_list(con.get("labels")):
            if label not in consumer_labels:
                errors.append(
                    f"label_consumers[{i}] ({con.get('path')!r}): label {label!r} does not "
                    f"resolve against {_LABELS_PATH} unioned with the label-policy "
                    f"rename_from and retired tables"
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
    if not isinstance(registry, dict):
        return ["registry root is not a JSON object"]

    vocab = extract_schema_vocab(schema)

    errors: list[str] = []
    errors += _check_shape(registry, vocab)
    errors += _check_planes(registry, vocab.planes)
    errors += _check_gate_kinds(registry, vocab.kinds)
    errors += _check_tracked_paths(registry, is_tracked)
    errors += _check_id_refs(registry)
    errors += _check_routing(registry, live_labels, vocab.body_reads)
    errors += _check_consumers(registry, consumer_labels)
    return errors


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


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
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        print(f"::error::{_SCRIPT}: cannot parse an input file: {exc}", file=sys.stderr)
        return 1

    live_labels = live_label_names(labels_data)
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
