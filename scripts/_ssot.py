"""Shared reader for the ``.gitapex/ssot.json`` gate registry.

The registry (design: ``docs/prd/gitapex-ssot-gate-registry.md``) is the
governed single source of truth for gate topology, policy-file references,
and label-based agent routing. This module is the phase-2 "consume" layer:
it loads the registry and exposes narrow lookups for consumers, so a label
rename in the registry becomes a one-file edit instead of a scripts/*.py
edit. It carries no validation of the registry's own shape; registry shape
and referential-integrity checks stay solely in
``scripts/scan_ssot_schema.py``, which is the gate that keeps this reader's
assumptions about the registry's shape honest.

The one exception is external policy files the registry merely points at:
``required_issue_axes`` resolves and parses ``.github/label-policy.toml``,
whose ``[[families]]`` shape no gate validates. That reader therefore checks
its own external input at read time and fails loud (``TypeError`` /
``RuntimeError``) rather than trusting an unchecked file; the boundary stays
narrow (only what that one reader consumes), not a general validation layer.

The load is lazy (deferred to first call, not import time) so importing
this module never touches disk, and a load failure surfaces only to the
consumer that actually needs the data rather than to every importer.

Refs #2266, #2246, #1041.
"""

from __future__ import annotations

import json
import tomllib
from pathlib import Path
from typing import Any

_REGISTRY_PATH = Path(__file__).resolve().parent.parent / ".gitapex" / "ssot.json"

# The label-policy family cardinalities that oblige every normal agent-created
# issue to carry at least one label of that family. Derived from the
# ``[[families]]`` semantics in ``.github/label-policy.toml``: "one_or_more" and
# "exactly_one_for_normal_issues" are the create-time mandatory forms, while
# "zero_or_one", the "_for_active_implementation"/"_for_universal_text_prs"
# conditional forms, and the "unbounded_but_..." ops form are NOT required at
# create. Today this set selects exactly the ``layer`` and ``type`` families.
_MANDATORY_AT_CREATE_CARDINALITIES: frozenset[str] = frozenset(
    {"one_or_more", "exactly_one_for_normal_issues"}
)

_registry: dict[str, Any] | None = None


def _load() -> dict[str, Any]:
    global _registry
    if _registry is None:
        _registry = json.loads(_REGISTRY_PATH.read_text(encoding="utf-8"))
    return _registry


def consumer_labels(path: str) -> tuple[str, ...]:
    """Return the label literals registered for the ``label_consumers`` entry at *path*.

    Raises ``KeyError`` when no entry matches *path*: a missing entry means the
    registry and its consumer have drifted apart, which must fail loud rather
    than silently fall back to an empty or guessed label set. Raises
    ``TypeError`` when the matched entry's ``labels`` is not a list: this can
    only happen if the registry reached this reader without first passing
    ``scan_ssot_schema.py`` (which requires ``labels`` to be an array), so the
    error must be loud rather than degrading into an empty tuple or, worse,
    ``tuple()`` silently splitting a stray string into one-character labels.
    """
    for entry in _load().get("label_consumers", []):
        if isinstance(entry, dict) and entry.get("path") == path:
            labels = entry.get("labels")
            if not isinstance(labels, list):
                raise TypeError(
                    f"_ssot: label_consumers entry for {path!r} has non-list "
                    f"labels {labels!r} in {_REGISTRY_PATH}"
                )
            return tuple(labels)
    raise KeyError(f"_ssot: no label_consumers entry for path {path!r} in {_REGISTRY_PATH}")


def routing_rules() -> tuple[dict[str, Any], ...]:
    """Return ``label_routing.rules`` verbatim, in registry order (first-match-wins).

    Raises ``TypeError`` when ``label_routing`` or ``label_routing.rules`` is
    missing or not the expected shape, for the same reason ``consumer_labels``
    does: a malformed value here means the schema gate has not run yet, and
    that must fail loud rather than return a silently empty rule set.
    """
    routing = _load().get("label_routing")
    if not isinstance(routing, dict):
        raise TypeError(f"_ssot: label_routing is missing or not an object in {_REGISTRY_PATH}")
    rules = routing.get("rules")
    if not isinstance(rules, list):
        raise TypeError(f"_ssot: label_routing.rules is missing or not a list in {_REGISTRY_PATH}")
    return tuple(rules)


def policy_source_path(source_id: str) -> Path:
    """Return the resolved filesystem path for the ``policy_sources`` entry *source_id*.

    Resolves the registry-relative ``path`` of the matching entry against the
    repository root, so a consumer names a policy file by its stable registry id
    (e.g. ``"label-policy"``) instead of hardcoding ``.github/label-policy.toml``.
    The repository root is derived from ``_REGISTRY_PATH`` at call time (not a
    frozen module constant), so a test that monkeypatches ``_REGISTRY_PATH``
    moves the resolution base with it consistently.

    Raises ``KeyError`` when no entry has that id: a missing pointer means the
    registry and its consumer have drifted apart, which must fail loud rather
    than silently resolve to a guessed path. Raises ``TypeError`` when the
    matched entry's ``path`` is not a string; this can only happen if the
    registry reached this reader without first passing ``scan_ssot_schema.py``
    (which requires every ``policy_sources[].path`` to be a tracked-file string),
    so the error must be loud rather than degrading into a bogus ``Path``.
    """
    for entry in _load().get("policy_sources", []):
        if isinstance(entry, dict) and entry.get("id") == source_id:
            path = entry.get("path")
            if not isinstance(path, str):
                raise TypeError(
                    f"_ssot: policy_sources entry {source_id!r} has non-string "
                    f"path {path!r} in {_REGISTRY_PATH}"
                )
            return _REGISTRY_PATH.parent.parent / path
    raise KeyError(f"_ssot: no policy_sources entry with id {source_id!r} in {_REGISTRY_PATH}")


def required_issue_axes() -> tuple[str, ...]:
    """Return the label-family axes an agent-created issue must carry, in policy order.

    Resolves the ``label-policy`` policy source, parses its ``[[families]]`` with
    ``tomllib`` (stdlib), and returns the ``name`` of each family whose
    ``cardinality`` is in :data:`_MANDATORY_AT_CREATE_CARDINALITIES`. The result
    is cardinality-driven, not a hardcoded axis list: today it yields exactly
    ``("layer", "type")`` in the file's family-declaration order, which keeps the
    classification gate's deny message deterministic.

    Fails loud, matching the reader's error style, rather than degrading into an
    empty axis set that would silently pass every under-labeled create:

    - ``KeyError`` / ``TypeError`` propagate from :func:`policy_source_path` when
      the ``label-policy`` pointer is missing or malformed.
    - ``RuntimeError`` when the policy file is unreadable, not decodable as UTF-8,
      or not valid TOML.
    - ``TypeError`` when ``[[families]]`` is missing, not an array of tables, or
      an entry lacks a string ``name`` / ``cardinality``.
    - ``RuntimeError`` when no family carries a mandatory-at-create cardinality,
      since an empty required-axis set is always a drift, never a valid policy.
    """
    policy_path = policy_source_path("label-policy")
    try:
        policy = tomllib.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"_ssot: cannot read label-policy at {policy_path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeError(f"_ssot: label-policy at {policy_path} is not valid TOML: {exc}") from exc

    families = policy.get("families")
    if not isinstance(families, list):
        raise TypeError(
            f"_ssot: label-policy at {policy_path} has missing or non-list [[families]]"
        )
    axes: list[str] = []
    for family in families:
        if not isinstance(family, dict):
            raise TypeError(
                f"_ssot: label-policy [[families]] entry is not a table: {family!r}"
            )
        name = family.get("name")
        cardinality = family.get("cardinality")
        if not isinstance(name, str) or not isinstance(cardinality, str):
            raise TypeError(
                f"_ssot: label-policy [[families]] entry has non-string name/cardinality: {family!r}"
            )
        if cardinality in _MANDATORY_AT_CREATE_CARDINALITIES:
            axes.append(name)
    if not axes:
        raise RuntimeError(
            f"_ssot: label-policy at {policy_path} declares no mandatory-at-create "
            f"family (cardinality in {sorted(_MANDATORY_AT_CREATE_CARDINALITIES)})"
        )
    return tuple(axes)


def retired_label_names() -> frozenset[str]:
    """Return the exact label names declared in label-policy's ``[[retired_labels]]``.

    Used to distinguish a registry entry's CREATE-time labels (applied to a
    newly filed issue) from its DISCOVERY-time labels (used to search for an
    already-filed issue): a retired label kept in a ``label_consumers`` entry
    during a successor migration (#1041, #2313) must still be searchable so
    pre-migration issues are found, but must never be applied to a new issue.
    Glob entries with no exact name (e.g. ``agent:*``) contribute nothing;
    only exact retired names matter here. Fails the same way
    :func:`required_issue_axes` does on a missing/malformed policy file.
    """
    policy_path = policy_source_path("label-policy")
    try:
        policy = tomllib.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError) as exc:
        raise RuntimeError(f"_ssot: cannot read label-policy at {policy_path}: {exc}") from exc
    except tomllib.TOMLDecodeError as exc:
        raise RuntimeError(f"_ssot: label-policy at {policy_path} is not valid TOML: {exc}") from exc

    retired = policy.get("retired_labels")
    if not isinstance(retired, list):
        raise TypeError(
            f"_ssot: label-policy at {policy_path} has missing or non-list [[retired_labels]]"
        )
    names: set[str] = set()
    for entry in retired:
        if not isinstance(entry, dict):
            raise TypeError(
                f"_ssot: label-policy [[retired_labels]] entry is not a table: {entry!r}"
            )
        name = entry.get("name")
        if not isinstance(name, str):
            raise TypeError(
                f"_ssot: label-policy [[retired_labels]] entry has non-string name: {entry!r}"
            )
        if "*" not in name:
            names.add(name)
    return frozenset(names)


def group_labels_by_family(labels: list[str]) -> list[str]:
    """Group *labels* by family prefix, comma-joining labels that share one.

    GitHub's search API ANDs separate ``label:`` qualifiers but ORs
    comma-separated values within a single qualifier. Two labels sharing a
    family (e.g. a retired label and its successor while a migration like
    #1041 comment 4882932274 is mid-rollout) are therefore alternatives for
    that one axis rather than an additional requirement, so an issue filed
    before or after the registry migration is discoverable either way.
    Distinct families still AND. Order-preserving by first appearance.

    This groups by textual family prefix only; it does not know whether a
    label-policy family's cardinality permits multiple simultaneous labels
    (see ``.github/label-policy.toml``). Callers that need two labels of the
    same family to be a hard AND requirement (not an either/or) must not
    route them through this helper.
    """
    order: list[str] = []
    groups: dict[str, list[str]] = {}
    for label in labels:
        family = label.split(":", 1)[0]
        if family not in groups:
            groups[family] = []
            order.append(family)
        groups[family].append(label)
    return [",".join(groups[family]) for family in order]


def _reset_for_tests() -> None:
    """Clear the cached registry so the next ``_load()`` call re-reads disk.

    Test-only: without this, a test that monkeypatches ``_REGISTRY_PATH`` after
    an earlier test already populated the module-level cache would silently
    keep getting the earlier test's data instead of re-reading the new path.
    """
    global _registry
    _registry = None
