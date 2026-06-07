#!/usr/bin/env python3
"""PreToolUse gate: require classification labels on agent-created issues.

Bound in ``.claude/settings.json`` (and mirrored in ``.codex/hooks.json``)
to ``mcp__github__issue_write``. When the call is a ``create`` it must carry
at least one ``layer:*`` and one ``type:*`` label, validated by name against
``.github/labels.json``. A create that is missing either axis is denied with a
``permissionDecision: "deny"`` message naming the missing axis, so the
label-classification step is a deterministic harness gate (CLAUDE.md section 3)
instead of an agent-remembered step. This closes the omission that required a
manual label repair after #1239, #1241, #1242, and #1243.

Scope note: ``mcp__github__create_pull_request`` is intentionally NOT gated.
The MCP tool schema exposes no ``labels`` argument, so a label gate on it would
deny every PR creation unconditionally. PR-side classification is tracked as a
separate backstop (issue #1246, "Optional backstop"). Only ``create`` is gated;
an ``update`` may legitimately omit or only partially touch labels.

Architecture mirrors :mod:`preflight_pr_template_shape` and
:mod:`issue_closure_fast_path`: pure functions on top, a single stdin/stdout
boundary at the bottom (:func:`main` via :func:`_hook_runtime.run_tool_hook`).

Failure modes (fail-open per CLAUDE.md section 4): off-target tool name, a
non-``create`` method, malformed stdin JSON, an unreadable or malformed
``.github/labels.json``, or an axis with no valid labels defined -- all exit 0
with no decision so a hook bug or a missing SoT never wedges the session. The
server-side triage workflow and review remain as backstops.

Refs #1246.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

from _hook_runtime import build_deny, run_tool_hook

_TARGET_TOOL = "mcp__github__issue_write"
_CREATE_METHOD = "create"

# Ordered so the deny message names axes deterministically (layer before type).
# Each axis is satisfied by a label whose name carries the given prefix AND is a
# registered name in .github/labels.json.
_AXIS_PREFIXES: tuple[tuple[str, str], ...] = (
    ("layer", "layer:"),
    ("type", "type:"),
)

_DEFAULT_LABELS_PATH = Path(__file__).resolve().parent.parent / ".github" / "labels.json"


def load_axis_labels(path: Path) -> dict[str, frozenset[str]]:
    """Return the valid label names for each axis, keyed by axis name.

    Reads the labels source of truth (a JSON array of ``{"name": ...}`` objects)
    and groups the names by axis prefix. Names that match no axis prefix are
    ignored. Raises ``OSError`` / ``json.JSONDecodeError`` / ``ValueError`` on a
    missing or malformed file; the caller turns those into fail-open.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("labels SoT must be a JSON array")
    names = [entry["name"] for entry in raw if isinstance(entry, dict) and isinstance(entry.get("name"), str)]
    axes: dict[str, frozenset[str]] = {}
    for axis, prefix in _AXIS_PREFIXES:
        axes[axis] = frozenset(name for name in names if name.startswith(prefix))
    return axes


def missing_axes(labels: Iterable[str], axes: Mapping[str, frozenset[str]]) -> list[str]:
    """Return the axes (in :data:`_AXIS_PREFIXES` order) not covered by *labels*.

    An axis whose valid-label set is empty is skipped (never reported missing):
    a malformed or stripped SoT must not block every create. Only labels that
    are registered names in the SoT count toward an axis, so ``layer:bogus``
    does not satisfy the ``layer`` axis.
    """
    present = {label for label in labels if isinstance(label, str)}
    missing: list[str] = []
    for axis, _prefix in _AXIS_PREFIXES:
        valid = axes.get(axis) or frozenset()
        if not valid:
            continue
        if not (present & valid):
            missing.append(axis)
    return missing


def build_reason(missing: list[str], axes: Mapping[str, frozenset[str]]) -> str:
    """Return the deny reason naming each missing axis and its valid labels."""
    parts = []
    for axis in missing:
        valid = sorted(axes.get(axis) or frozenset())
        parts.append(f"`{axis}:*` (one of: {', '.join(valid)})")
    needed = "; ".join(parts)
    return (
        "Blocked by scripts/gate_issue_classification_labels.py: this "
        f"`{_TARGET_TOOL}` create is missing a required classification label.\n\n"
        f"Add at least one label for each missing axis: {needed}.\n\n"
        "Per CLAUDE.md section 3, agent-created issues must carry at least one "
        "`layer:*` and one `type:*` label (validated against .github/labels.json) "
        "so classification is a deterministic harness gate, not a remembered "
        "step. Pass the labels in the `labels` argument and retry. Refs #1246."
    )


def decide(
    tool_name: str,
    tool_input: dict[str, Any],
    *,
    labels_path: Path = _DEFAULT_LABELS_PATH,
) -> dict[str, Any] | None:
    """Return a deny decision for an under-labeled create, else ``None``."""
    if tool_name != _TARGET_TOOL:
        return None
    if tool_input.get("method") != _CREATE_METHOD:
        return None

    try:
        axes = load_axis_labels(labels_path)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(
            f"::warning::gate_issue_classification_labels: cannot read labels SoT: {exc}",
            file=sys.stderr,
        )
        return None

    raw_labels = tool_input.get("labels")
    labels = raw_labels if isinstance(raw_labels, list) else []
    missing = missing_axes(labels, axes)
    if not missing:
        return None
    return build_deny(build_reason(missing, axes))


def main(argv: list[str] | None = None) -> int:
    del argv
    return run_tool_hook("gate_issue_classification_labels", decide)


if __name__ == "__main__":
    raise SystemExit(main())
