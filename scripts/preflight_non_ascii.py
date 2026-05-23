#!/usr/bin/env python3
"""Client-side preflight for GitHub MCP write tools (Layer 2.5).

PreToolUse hook invoked by Claude Code on the matchers configured in
``.claude/settings.json``. Reads a PreToolUse event JSON from stdin and,
when the tool input contains non-ASCII text without the operator opt-out
marker, emits a ``permissionDecision: "deny"`` JSON on stdout that asks
Claude to either translate to English or append ``<!-- non-ascii-ack -->``
to the body before retrying.

Complements the server-side Layer 2 workflow (``scan-non-ascii.yml`` /
``scripts/scan_non_ascii.py``); see ``docs/non-ascii-defense.md`` Layer
2.5. Refs #146, umbrella #102.

Architecture mirrors :mod:`scan_non_ascii`: pure functions on top, one
thin stdin/stdout boundary at the bottom (:func:`main`). The detection
regex, ack-marker semantics, and escape format are imported from
``scan_non_ascii`` so the two layers cannot drift.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from scan_non_ascii import (
    ACK_MARKER,
    detect_non_ascii,
    escape_for_comment,
    has_ack_marker,
)

# Tools whose inputs carry user-authored prose that Layer 2 would later
# scan. Kept in sync with the matcher regex in ``.claude/settings.json``;
# the matcher is the primary gate, this set is defense in depth.
_TARGET_TOOLS: frozenset[str] = frozenset({
    "mcp__github__issue_write",
    "mcp__github__add_issue_comment",
    "mcp__github__create_pull_request",
    "mcp__github__update_pull_request",
    "mcp__github__add_reply_to_pull_request_comment",
    "mcp__github__pull_request_review_write",
    "mcp__github__add_comment_to_pending_review",
    "mcp__github__sub_issue_write",
})


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def extract_text_fields(tool_input: dict[str, Any]) -> tuple[str, str]:
    """Return ``(title, body)`` from a tool input payload.

    Missing or non-string fields collapse to ``""`` so downstream
    detection sees a uniform shape regardless of which write tool fired.
    """
    title = tool_input.get("title") or ""
    body = tool_input.get("body") or ""
    if not isinstance(title, str):
        title = ""
    if not isinstance(body, str):
        body = ""
    return title, body


def offending_fields(title: str, body: str) -> list[str]:
    """Return the subset of ``["title", "body"]`` containing non-ASCII."""
    out: list[str] = []
    if title and detect_non_ascii(title):
        out.append("title")
    if body and detect_non_ascii(body):
        out.append("body")
    return out


def build_deny_reason(
    tool_name: str,
    fields: list[str],
    escaped: str,
    ack_marker: str = ACK_MARKER,
) -> str:
    """Return the human-readable reason text for the deny decision.

    Lists which fields contained non-ASCII, shows the escaped form so the
    model treats it as data, and offers the two remediation options in
    the order documented in ``docs/non-ascii-defense.md`` Layer 2.5.
    """
    where = " and ".join(fields) if fields else "input"
    return (
        f"Blocked by scripts/preflight_non_ascii.py (Layer 2.5): "
        f"`{tool_name}` {where} contains non-ASCII characters that would "
        f"trigger the server-side scan-non-ascii.yml workflow on every "
        f"post. Pick one and retry:\n"
        f"  1. Translate the {where} to English.\n"
        f"  2. Append `\\n\\n{ack_marker}` to the body (OWNER opt-out -- "
        f"keeps non-ASCII intact, suppresses the Layer 2 advisory by "
        f"making classify_action return `skip`).\n"
        f"\n"
        f"Escaped form of the offending content (data view, agent-safe):\n"
        f"```\n{escaped}\n```"
    )


def decide(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:
    """Return the hook output dict, or ``None`` if the call should proceed.

    Order:
      1. Off-target tool -> allow (None).
      2. ACK marker already present -> allow (operator pre-authorized).
      3. No non-ASCII detected -> allow.
      4. Otherwise -> deny dict.
    """
    if tool_name not in _TARGET_TOOLS:
        return None
    title, body = extract_text_fields(tool_input)
    if has_ack_marker(body):
        return None
    fields = offending_fields(title, body)
    if not fields:
        return None
    escaped = escape_for_comment(f"{title}\n{body}" if title else body)
    reason = build_deny_reason(tool_name, fields, escaped)
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


# ---------------------------------------------------------------------------
# Side-effecting boundary -- the only impure surface, monkeypatched in tests
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    """Read PreToolUse JSON from stdin, write decision JSON to stdout.

    Fails open per CLAUDE.md §4: any parse error or unexpected payload
    shape emits ``::error::...`` to stderr and exits 0 with no decision,
    so a hook bug never wedges the session. The Layer 2 server-side
    workflow remains as backstop.
    """
    del argv  # not used; the harness pipes the event on stdin
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(
            f"::error::preflight_non_ascii: malformed stdin JSON: {exc}",
            file=sys.stderr,
        )
        return 0

    tool_name = event.get("tool_name")
    tool_input = event.get("tool_input") or {}
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        print(
            "::error::preflight_non_ascii: event missing tool_name/tool_input",
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
