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
all. Read-only operations (list, get, search) are safe to pass through
directly; they carry no write risk; and are enumerated in
:data:`READ_ONLY_TOOLS`. Write operations require a hook before they can
be unblocked.
See #887 for the MCP-vs-GitHub-API design decision.

Fails open per CLAUDE.md section 4: parse errors log to stderr and exit 0
so a hook bug never wedges the session.

Refs #870, #887, #1869.
"""

from __future__ import annotations

import sys
from typing import Any

from _hook_runtime import emit_decision, read_event

# Tools that already have dedicated PreToolUse hooks in
# .claude/settings.json. Calls to these tools are allowed through;
# their own hooks handle the gating. Keep in sync with the matcher
# groups in settings.json PreToolUse; drift is caught by
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
        "mcp__github__update_pull_request_branch",
    }
)

# Known read-only MCP tools. These carry no write risk and are allowed
# through without a dedicated hook. Not added to HOOK_COVERED_TOOLS --
# that set is reserved for write tools that have their own paired hooks.
#
# Includes both the consolidated names used by the current deployment
# (issue_read, pull_request_read) and the pre-consolidation names used
# by the Nix-pinned github-mcp-server v0.3.0 in the devcontainer
# (get_issue, get_pull_request, etc.; see pkg/github/tools.go@v0.3.0).
# Refs #1869.
READ_ONLY_TOOLS: frozenset[str] = frozenset(
    {
        "mcp__github__actions_get",
        "mcp__github__actions_list",
        "mcp__github__get_code_scanning_alert",
        "mcp__github__get_commit",
        "mcp__github__get_file_contents",
        "mcp__github__get_issue",
        "mcp__github__get_issue_comments",
        "mcp__github__get_job_logs",
        "mcp__github__get_label",
        "mcp__github__get_latest_release",
        "mcp__github__get_me",
        "mcp__github__get_pull_request",
        "mcp__github__get_pull_request_comments",
        "mcp__github__get_pull_request_files",
        "mcp__github__get_pull_request_reviews",
        "mcp__github__get_pull_request_status",
        "mcp__github__get_release_by_tag",
        "mcp__github__get_secret_scanning_alert",
        "mcp__github__get_tag",
        "mcp__github__get_team_members",
        "mcp__github__get_teams",
        "mcp__github__issue_read",
        "mcp__github__list_branches",
        "mcp__github__list_code_scanning_alerts",
        "mcp__github__list_commits",
        "mcp__github__list_issue_fields",
        "mcp__github__list_issue_types",
        "mcp__github__list_issues",
        "mcp__github__list_pull_requests",
        "mcp__github__list_releases",
        "mcp__github__list_repository_collaborators",
        "mcp__github__list_secret_scanning_alerts",
        "mcp__github__list_tags",
        "mcp__github__pull_request_read",
        "mcp__github__search_code",
        "mcp__github__search_commits",
        "mcp__github__search_issues",
        "mcp__github__search_pull_requests",
        "mcp__github__search_repositories",
        "mcp__github__search_users",
    }
)

_MCP_GITHUB_PREFIX = "mcp__github__"


def decide(tool_name: str) -> dict[str, Any] | None:
    """Return a deny decision for uncovered tools, or None to pass through.

    Returns None for:
    - tools not in the ``mcp__github__`` namespace (not our concern)
    - tools in :data:`HOOK_COVERED_TOOLS` (already gated elsewhere)
    - tools in :data:`READ_ONLY_TOOLS` (no write risk; early pass)

    Returns a ``permissionDecision: "deny"`` dict for any other
    ``mcp__github__*`` tool.
    """
    if not tool_name.startswith(_MCP_GITHUB_PREFIX):
        return None
    if tool_name in HOOK_COVERED_TOOLS:
        return None
    if tool_name in READ_ONLY_TOOLS:
        return None
    return {
        "permissionDecision": "deny",
        "decisionReason": (
            f"`{tool_name}` has no dedicated PreToolUse hook gate. "
            f"For write operations, a paired PreToolUse hook must be added to "
            f".claude/settings.json before this tool can be used. "
            f"See #887 for the MCP-vs-GitHub-API design decision."
        ),
    }


def main(argv: list[str] | None = None) -> int:
    """Read PreToolUse JSON from stdin, write deny decision to stdout if needed."""
    del argv
    event = read_event("gate_mcp_github_uncovered")
    if event is None:
        return 0

    tool_name = event.get("tool_name")
    if not isinstance(tool_name, str):
        print(
            "::error::gate_mcp_github_uncovered: event missing tool_name",
            file=sys.stderr,
        )
        return 0

    emit_decision(decide(tool_name), "gate_mcp_github_uncovered")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
