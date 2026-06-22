#!/usr/bin/env python3
"""PostToolUse hook: dedup guard for the post-merge auto-retro.

When the agent calls mcp__github__merge_pull_request this hook emits
additionalContext instructing the agent to:

  1. NOT open a second retrospective issue.  CI post-merge.yml already
     triggers scripts/auto_retro.py which opens the canonical auto-retro
     (title prefix ``chore(auto-retro)``) with the repair-history table
     pre-filled from check_runs + commit subjects.
  2. NOT post a separate repair-analysis comment on that retro.  The retro
     body is already pre-filled and the triage-report dashboard
     (docs/generated/scripts/auto-retro-triage-report.md) is the review
     surface, so an appended comment is redundant notification noise
     (Phase 1 of #1386).
  3. Fallback only: create a new retro if no auto-retro exists after the
     CI workflow has had time to run (workflow was skipped or failed), so
     the audit ledger is never lost.

This hook used to direct the agent to append its repair analysis as a
comment via mcp__github__add_issue_comment; that directive was removed in
Phase 1 of #1386 to cut per-merge comment noise. The dedup guard (do not
open a duplicate retro) is retained.

Fail-open: malformed input, missing fields, or off-target tools exit 0
with no output so a hook bug cannot wedge unrelated tool calls.

Refs: issue #916, #1386.
"""

from __future__ import annotations

import re
from typing import Any

from _hook_runtime import emit_decision, read_event

TARGET_TOOL = "mcp__github__merge_pull_request"

_PR_URL_RE = re.compile(
    r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/pull/(\d+)"
)
# Auto-retro issues are titled ``chore(auto-retro): review PR #N repair
# loops`` (Refs #1069). Closed historical retros use the legacy
# ``fix(auto-retro)`` prefix; ``scripts/auto_retro.py:is_retro_issue_title``
# recognizes both, but the open auto-retro the agent searches for here
# carries the current prefix.
RETRO_TITLE_PREFIX = "chore(auto-retro)"


def _walk(value: Any) -> list[Any]:
    out: list[Any] = []
    stack = [value]
    while stack and len(out) < 200:
        node = stack.pop()
        out.append(node)
        if isinstance(node, dict):
            stack.extend(node.values())
        elif isinstance(node, list):
            stack.extend(node)
    return out


def extract_merge_coords(
    tool_input: dict[str, Any], tool_response: Any
) -> tuple[str | None, str | None, str | None]:
    """Return (owner, repo, pr_number) from a merge event.

    Prefers ``pullRequestNumber`` in tool_input; falls back to a PR URL
    found anywhere in tool_response.
    """
    owner = tool_input.get("owner") if isinstance(tool_input, dict) else None
    repo = tool_input.get("repo") if isinstance(tool_input, dict) else None

    pr_number: str | None = None
    if isinstance(tool_input, dict):
        val = tool_input.get("pullRequestNumber")
        if isinstance(val, int) and val > 0:
            pr_number = str(val)
        elif isinstance(val, str) and val.isdecimal():
            pr_number = val

    if pr_number is None:
        for node in _walk(tool_response):
            if isinstance(node, str):
                m = _PR_URL_RE.search(node)
                if m:
                    if owner is None:
                        owner = m.group(1)
                    if repo is None:
                        repo = m.group(2)
                    pr_number = m.group(3)
                    break

    return owner, repo, pr_number


def _build_context(message: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": message,
        }
    }


def decide(event: dict[str, Any]) -> dict[str, Any] | None:
    """Return hook output for a PostToolUse merge event, or None if no action needed."""
    if event.get("tool_name") != TARGET_TOOL:
        return None

    tool_input = event.get("tool_input") or {}
    tool_response = event.get("tool_response")

    owner, repo, pr_number = extract_merge_coords(tool_input, tool_response)

    if pr_number is None:
        return _build_context(
            f"AUTO-RETRO DEDUP GUARD: {TARGET_TOOL} fired but the merged PR number "
            f"could not be extracted from tool_input or tool_response. "
            f"Do NOT open a new retrospective issue and do NOT post a separate "
            f"repair-analysis comment: CI post-merge.yml opens the canonical "
            f"auto-retro (title prefix '{RETRO_TITLE_PREFIX}') with its body "
            f"pre-filled, and the triage-report dashboard is the review surface. "
            f"Only create a retro if none exists after CI has run."
        )

    pr_label = f"{owner}/{repo}#{pr_number}" if owner and repo else f"PR #{pr_number}"

    return _build_context(
        f"AUTO-RETRO DEDUP GUARD: PR {pr_label} was just merged. "
        f"Do NOT open a new retrospective issue and do NOT post a separate "
        f"repair-analysis comment. "
        f"CI post-merge.yml will automatically open a retro titled "
        f"'{RETRO_TITLE_PREFIX}: review {pr_label} repair loops' (or similar) with "
        f"the repair-history table pre-filled from check_runs + commit subjects. "
        f"The triage-report dashboard "
        f"(docs/generated/scripts/auto-retro-triage-report.md) is the review "
        f"surface, so an appended comment is redundant noise.\n"
        f"Fallback only: if no auto-retro appears after CI has had time to run "
        f"(post-merge.yml was skipped or failed), create a new retro issue -- but "
        f"only after confirming no existing retro covers PR #{pr_number}.\n"
        f"Forbidden: opening a second retro issue when an auto-retro already exists "
        f"or is pending from CI."
    )


def main(argv: list[str] | None = None) -> int:
    del argv
    event = read_event("post_merge_retro_append")
    if event is None:
        return 0
    if not isinstance(event, dict):
        return 0
    emit_decision(decide(event))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
