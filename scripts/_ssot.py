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
    than silently fall back to an empty or guessed label set.
    """
    for entry in _load().get("label_consumers", []):
        if isinstance(entry, dict) and entry.get("path") == path:
            return tuple(entry.get("labels", []))
    raise KeyError(f"_ssot: no label_consumers entry for path {path!r} in {_REGISTRY_PATH}")


def routing_rules() -> tuple[dict[str, Any], ...]:
    """Return ``label_routing.rules`` verbatim, in registry order (first-match-wins)."""
    return tuple(_load().get("label_routing", {}).get("rules", []))
