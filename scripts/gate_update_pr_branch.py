#!/usr/bin/env python3
"""PreToolUse gate: deny mcp__github__update_pull_request_branch.

``update_pull_request_branch`` performs a server-side **merge** (not a
rebase). Merging main into the feature branch adds a merge commit, so the
branch history diverges from the clean linear pattern the harness is
designed around.

Recovery path: see ``docs/runbooks/update-pr-branch-recovery.md``.

Wiring:
  PreToolUse matcher ``mcp__github__update_pull_request_branch`` in
  ``.claude/settings.json``. Also listed in ``HOOK_COVERED_TOOLS`` in
  ``gate_mcp_github_uncovered.py`` so the catch-all passes it through
  to this dedicated gate.

Refs #893.
"""

from __future__ import annotations

import sys
from typing import Any

from _hook_runtime import emit_decision, read_event

_TARGET_TOOL = "mcp__github__update_pull_request_branch"

_DENY_REASON = (
    "`mcp__github__update_pull_request_branch` is blocked. "
    "The GitHub API performs a server-side merge (not a rebase), which "
    "adds a merge commit to the branch and diverges from the "
    "clean linear harness pattern.\n\n"
    "Recovery path:\n"
    "  1. git fetch origin main\n"
    "  2. git checkout -b <replacement-branch> origin/main\n"
    "  3. Re-apply the PR change as a single commit.\n"
    "  4. git push -u origin <replacement-branch>\n"
    "  5. Retarget or replace the open PR.\n\n"
    "Full procedure: docs/runbooks/update-pr-branch-recovery.md\n"
    "Refs #893."
)


def decide(tool_name: str) -> dict[str, Any] | None:
    """Return a deny decision when tool is ``_TARGET_TOOL``, else None."""
    if tool_name != _TARGET_TOOL:
        return None
    return {
        "permissionDecision": "deny",
        "decisionReason": _DENY_REASON,
    }


def main(argv: list[str] | None = None) -> int:
    """Read PreToolUse JSON from stdin, write deny decision to stdout if blocked."""
    del argv
    event = read_event("gate_update_pr_branch")
    if event is None:
        return 0

    tool_name = event.get("tool_name")
    if not isinstance(tool_name, str):
        print(
            "::error::gate_update_pr_branch: event missing tool_name",
            file=sys.stderr,
        )
        return 0

    emit_decision(decide(tool_name), "gate_update_pr_branch")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
