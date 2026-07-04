#!/usr/bin/env python3
"""PreToolUse gate: require classification labels on agent-created issues.

Bound in ``.claude/settings.json`` (and mirrored in ``.codex/hooks.json``)
to ``mcp__github__issue_write``. When the call is a ``create`` it must carry
at least one label for each required classification axis (today ``layer:*``
and ``type:*``, derived as described below), validated by name against
``.github/labels.json``. A create that is missing an axis is denied with a
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

The required axes are not hardcoded: they are cardinality-driven, resolved from
the ``.github/label-policy.toml`` ``[[families]]`` via
``_ssot.required_issue_axes`` (the ``label-policy`` registry pointer in
``.gitapex/ssot.json``), so a future family/cardinality change adds or drops a
required axis through the registry, not an edit here. Today this yields exactly
the ``layer`` and ``type`` axes. A ``tests/`` pin-test asserts that derivation so
any silent drift fails deterministically.

Failure modes (fail-open per CLAUDE.md section 4): off-target tool name, a
non-``create`` method, malformed stdin JSON, an unreadable or malformed
``.github/labels.json``, a missing or malformed ``label-policy`` registry pointer
or families, or an axis with no valid labels defined; all exit 0 with no decision
so a hook bug or a missing SoT never wedges the session. The pin-test, the
server-side triage workflow, and review remain as backstops.

Refs #1246, #2292.
"""

from __future__ import annotations

import json
import sys
from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import _ssot
from _hook_runtime import build_deny, run_tool_hook

_TARGET_TOOL = "mcp__github__issue_write"
_CREATE_METHOD = "create"

_DEFAULT_LABELS_PATH = Path(__file__).resolve().parent.parent / ".github" / "labels.json"


def axis_prefixes() -> tuple[tuple[str, str], ...]:
    """Return the ``(axis, prefix)`` pairs a create must satisfy, in policy order.

    The required axes are cardinality-driven, resolved from the label-policy
    ``[[families]]`` via :func:`_ssot.required_issue_axes` rather than hardcoded,
    so a future family/cardinality change flows through the registry instead of
    an edit here. Each axis is satisfied by a label whose name carries the derived
    ``"<axis>:"`` prefix AND is a registered name in ``.github/labels.json``.
    Order follows the policy's family declaration order, so the deny message names
    axes deterministically (today: ``layer`` before ``type``).

    Propagates ``_ssot``'s loud drift errors (``KeyError`` / ``TypeError`` /
    ``RuntimeError``); the caller in :func:`decide` turns those into fail-open.
    """
    return tuple((axis, f"{axis}:") for axis in _ssot.required_issue_axes())


def load_axis_labels(path: Path) -> dict[str, frozenset[str]]:
    """Return the valid label names for each axis, keyed by axis name.

    Reads the labels source of truth (a JSON array of ``{"name": ...}`` objects)
    and groups the names by the axis prefixes from :func:`axis_prefixes`. Names
    that match no axis prefix are ignored. Raises ``OSError`` /
    ``json.JSONDecodeError`` / ``ValueError`` on a missing or malformed labels
    file, or the reader's drift errors from :func:`axis_prefixes`; the caller
    turns those into fail-open.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("labels SoT must be a JSON array")
    names = [entry["name"] for entry in raw if isinstance(entry, dict) and isinstance(entry.get("name"), str)]
    axes: dict[str, frozenset[str]] = {}
    for axis, prefix in axis_prefixes():
        axes[axis] = frozenset(name for name in names if name.startswith(prefix))
    return axes


def missing_axes(labels: Iterable[str], axes: Mapping[str, frozenset[str]]) -> list[str]:
    """Return the axes (in *axes* insertion / policy order) not covered by *labels*.

    An axis whose valid-label set is empty is skipped (never reported missing):
    a malformed or stripped SoT must not block every create. Only labels that
    are registered names in the SoT count toward an axis, so ``layer:bogus``
    does not satisfy the ``layer`` axis.
    """
    present = {label for label in labels if isinstance(label, str)}
    missing: list[str] = []
    for axis, valid in axes.items():
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
        "label for each required classification axis (the axes listed above, "
        "derived from the label-policy families and validated against "
        ".github/labels.json) so classification is a deterministic harness gate, "
        "not a remembered step. Pass the labels in the `labels` argument and "
        "retry. Refs #1246, #2292."
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
    except (OSError, ValueError, LookupError, TypeError, RuntimeError) as exc:
        # Deliberately broad fail-open (CLAUDE.md section 4): this is a PreToolUse
        # gate, so any failure to derive the axes; a missing/malformed labels SoT,
        # a drifted label-policy pointer or families, even an unexpected bug in the
        # derivation; must not wedge issue creation. Letting the exception escape
        # would block the tool call on a hook problem, which is worse than not
        # enforcing. Drift that this masks at runtime is caught loudly in CI by the
        # tests/ pin-tests (required axes, order, and per-axis live labels), so a
        # real regression fails there rather than silently disabling the gate.
        print(
            f"::warning::gate_issue_classification_labels: cannot derive axis labels: {exc}",
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
