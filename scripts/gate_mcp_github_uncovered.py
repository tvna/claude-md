#!/usr/bin/env python3
"""Catch-all PreToolUse gate for GitHub MCP tools without dedicated hooks.

PreToolUse hook registered under the ``mcp__github__`` matcher in
``.claude/settings.json``. For every ``mcp__github__*`` call, checks
whether that specific tool has a dedicated ``PreToolUse`` hook entry. If
it does, the call is already gated and this script passes through (exit 0,
no decision). If it does not, the script denies the call and redirects the agent to
``scripts/github_api.py`` (for reads) or instructs them to add a
paired PreToolUse hook before using a new write tool.

Rationale: dedicated hooks gate and audit the write tools listed in
:data:`HOOK_COVERED_TOOLS`. Any tool NOT in that set has no preflight at
all. Read operations should use ``scripts/github_api.py`` for lower token
consumption. Write operations require a hook before they can be unblocked.
See #887 for the MCP-vs-GitHub-API design decision.

Fails open per CLAUDE.md section 4: parse errors log to stderr and exit 0
so a hook bug never wedges the session.

Refs #870, #887.
"""

from __future__ import annotations

import json
import sys
from typing import Any

# Tools that already have dedicated PreToolUse hooks in
# .claude/settings.json. Calls to these tools are allowed through;
# their own hooks handle the gating. Keep in sync with the matcher
# groups in settings.json PreToolUse -- drift is caught by
# test_gate_mcp_github_uncovered.py::test_covered_set_matches_settings.
HOOK_COVERED_TOOLS: frozenset[str] = frozenset(
    {
        "mcp__github__issue_write",
        "mcp__github__add_issue_comment",
        "mcp__github__create_pull_request",
        "mcp__github__update_pull_request",
        "mcp__github__add_reply_to_pull_request_comment",
        "mcp__github__pull_request_review_write",
        "mcp__github__add_comment_to_pending_review",
        "mcp__github__sub_issue_write",
        "mcp__github__create_branch",
        "mcp__github__merge_pull_request",
    }
)

_MCP_GITHUB_PREFIX = "mcp__github__"


def decide(tool_name: str) -> dict[str, Any] | None:
    """Return a deny decision for uncovered tools, or None to pass through.

    Returns None for:
    - tools not in the ``mcp__github__`` namespace (not our concern)
    - tools in :data:`HOOK_COVERED_TOOLS` (already gated elsewhere)

    Returns a ``permissionDecision: "deny"`` dict for any other
    ``mcp__github__*`` tool.
    """
    if not tool_name.startswith(_MCP_GITHUB_PREFIX):
        return None
    if tool_name in HOOK_COVERED_TOOLS:
        return None
    short = tool_name[len(_MCP_GITHUB_PREFIX) :]
    return {
        "permissionDecision": "deny",
        "decisionReason": (
            f"`{tool_name}` has no dedicated PreToolUse hook gate. "
            f"For read operations (list, search, get), use the approved wrapper:\n"
            f"  python3 scripts/github_api.py GET "
            f"https://api.github.com/repos/{{owner}}/{{repo}}/{short.replace('_', '/')} "
            f"[--fields f1,f2]\n"
            f"For write operations, a paired PreToolUse hook must be added to "
            f".claude/settings.json before this tool can be used. "
            f"See #887 for the MCP-vs-GitHub-API design decision."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    """Read PreToolUse JSON from stdin, write deny decision to stdout if needed."""
    del argv
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(
            f"::error::gate_mcp_github_uncovered: malformed stdin JSON: {exc}",
            file=sys.stderr,
        )
        return 0

    tool_name = event.get("tool_name")
    if not isinstance(tool_name, str):
        print(
            "::error::gate_mcp_github_uncovered: event missing tool_name",
            file=sys.stderr,
        )
        return 0

    decision = decide(tool_name)
    if decision is not None:
        sys.stdout.write(json.dumps(decision))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
