#!/usr/bin/env python3
"""Claude Code PreToolUse hook: block PR bodies that would fail the shape gate.

Bound in ``.claude/settings.json`` to
``mcp__github__(create_pull_request|update_pull_request)``. Reads the
PreToolUse event JSON from stdin and, when the PR body would fail the
post-2026-05-26 Verification + Checklist shape check enforced by
``scripts/body_policy.py``, emits a ``permissionDecision: "deny"`` JSON
on stdout so the operator can fix the body BEFORE the API call instead
of round-tripping through ``verify-body-policy.yml``.

Architecture mirrors :mod:`pr_body_close_keyword_gate` and
:mod:`preflight_non_ascii`: pure decision function on top, a single
stdin/stdout boundary at the bottom (:func:`main`). The shape regexes
and required-subsection list are imported from :mod:`body_policy` so
the hook and the server gate cannot drift.

Failure modes (fail-open):

* off-target tool name, body absent or non-string, malformed stdin
  JSON, ``tool_input`` shape invalid -- exit 0 with no output. A hook
  bug must never wedge unrelated tool calls; the server gate
  (``verify-body-policy.yml``) remains as backstop.

The hook deliberately ignores the cutoff env var (``BODY_POLICY_SHAPE_CUTOFF``):
any new PR opened through MCP is expected to follow the new shape,
since the cutoff exists only to exempt the back-catalog at the server.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from body_policy import (
    verify_pr_checklist_subsections,
    verify_pr_verification_pairs,
)

_TARGET_TOOLS: frozenset[str] = frozenset(
    {
        "mcp__github__create_pull_request",
        "mcp__github__update_pull_request",
    }
)


def evaluate(body: str) -> list[str]:
    """Return list of ``::error::`` strings; empty list means OK."""
    return verify_pr_verification_pairs(body) + verify_pr_checklist_subsections(
        body
    )


def decide(
    tool_name: str, tool_input: dict[str, Any]
) -> dict[str, Any] | None:
    """Return the hook output dict, or ``None`` if the call should proceed."""
    if tool_name not in _TARGET_TOOLS:
        return None
    body = tool_input.get("body")
    if not isinstance(body, str):
        return None
    errors = evaluate(body)
    if not errors:
        return None
    joined = "\n".join(errors)
    reason = (
        f"Blocked by scripts/preflight_pr_template_shape.py (client-side "
        f"mirror of verify-body-policy.yml shape gate): `{tool_name}` "
        f"would fail server-side.\n\n{joined}\n\nFix the PR body to use "
        "the post-2026-05-26 shape: see "
        "docs/issue-pr-body-standard.md and "
        ".github/PULL_REQUEST_TEMPLATE.md."
    )
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def main(argv: list[str] | None = None) -> int:
    del argv
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(
            f"::error::preflight_pr_template_shape: malformed stdin JSON: {exc}",
            file=sys.stderr,
        )
        return 0

    tool_name = event.get("tool_name")
    tool_input = event.get("tool_input") or {}
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        print(
            "::error::preflight_pr_template_shape: event missing tool_name/tool_input",
            file=sys.stderr,
        )
        return 0

    decision = decide(tool_name, tool_input)
    if decision is None:
        return 0

    sys.stdout.write(json.dumps(decision))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
