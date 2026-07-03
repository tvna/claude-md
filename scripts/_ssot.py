"""Shared reader for the ``.gitapex/ssot.json`` gate registry.

The registry (design: ``docs/prd/gitapex-ssot-gate-registry.md``) is the
governed single source of truth for gate topology, policy-file references,
and label-based agent routing. This module is the phase-2 "consume" layer:
it loads the registry and exposes narrow lookups for consumers, so a label
rename in the registry becomes a one-file edit instead of a scripts/*.py
edit. It carries no validation logic; shape and referential-integrity
checks stay solely in ``scripts/scan_ssot_schema.py``, which is the gate
that keeps this reader's assumptions about the registry's shape honest.

The load is lazy (deferred to first call, not import time) so importing
this module never touches disk, and a load failure surfaces only to the
consumer that actually needs the data rather than to every importer.

Refs #2266, #2246, #1041.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_REGISTRY_PATH = Path(__file__).resolve().parent.parent / ".gitapex" / "ssot.json"

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


def _reset_for_tests() -> None:
    """Clear the cached registry so the next ``_load()`` call re-reads disk.

    Test-only: without this, a test that monkeypatches ``_REGISTRY_PATH`` after
    an earlier test already populated the module-level cache would silently
    keep getting the earlier test's data instead of re-reading the new path.
    """
    global _registry
    _registry = None
