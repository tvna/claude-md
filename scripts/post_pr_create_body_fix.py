#!/usr/bin/env python3
"""PostToolUse hook: fix PR body corruption after mcp__github__create_pull_request.

mcp__github__create_pull_request has two defects that corrupt the stored body:
  1. Encodes & as &amp; before storing (HTML encoding defect).
  2. Appends a duplicate footer even when one already exists.

This hook emits additionalContext instructing the agent to immediately call
mcp__github__update_pull_request with the original authored body from
tool_input, bypassing both defects.

Fail-open: malformed input, missing fields, or off-target tools exit 0 with
no output so a hook bug cannot wedge unrelated tool calls.

Refs: issue #892.
"""

from __future__ import annotations

import re
from typing import Any

from _hook_runtime import emit_decision, read_event

TARGET_TOOL = "mcp__github__create_pull_request"

_PR_URL_RE = re.compile(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/pull/(\d+)")
_NUMBER_KEYS = frozenset({"number", "pullRequestNumber", "pull_request_number", "pr_number"})
_MAX_BODY_PREVIEW = 4000  # characters; truncated beyond this to avoid excessive context


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


def extract_pr_coords(
    tool_input: dict[str, Any], tool_response: Any
) -> tuple[str | None, str | None, str | None]:
    """Return (owner, repo, pr_number) from event fields.

    Prefers a PR URL in tool_response (most reliable); falls back to
    structured number fields combined with owner/repo from tool_input.
    """
    for node in _walk(tool_response):
        if isinstance(node, str):
            m = _PR_URL_RE.search(node)
            if m:
                return m.group(1), m.group(2), m.group(3)

    owner = tool_input.get("owner") if isinstance(tool_input, dict) else None
    repo = tool_input.get("repo") if isinstance(tool_input, dict) else None

    for node in _walk(tool_response):
        if not isinstance(node, dict):
            continue
        for key in _NUMBER_KEYS:
            val = node.get(key)
            if isinstance(val, int) and val > 0:
                return owner, repo, str(val)
            if isinstance(val, str) and val.isdecimal():
                return owner, repo, val

    return None, None, None


def _build_context(message: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": message,
        }
    }


def decide(event: dict[str, Any]) -> dict[str, Any] | None:
    """Return hook output for a PostToolUse event, or None if no action needed."""
    if event.get("tool_name") != TARGET_TOOL:
        return None

    tool_input = event.get("tool_input") or {}
    tool_response = event.get("tool_response")

    body = tool_input.get("body") if isinstance(tool_input, dict) else None
    if not isinstance(body, str) or not body.strip():
        return _build_context(
            "PR body fix skipped: original authored body not found in tool_input. "
            "Verify the stored PR body for & → &amp; encoding and duplicate footer; "
            "call mcp__github__update_pull_request to rewrite if either defect is present."
        )

    owner, repo, pr_number = extract_pr_coords(tool_input, tool_response)
    if pr_number is None:
        return _build_context(
            "PR body fix skipped: could not extract PR number from tool response. "
            "Verify the stored PR body for & → &amp; encoding and duplicate footer; "
            "call mcp__github__update_pull_request to rewrite if either defect is present."
        )

    pr_label = f"{owner}/{repo}#{pr_number}" if owner and repo else f"PR #{pr_number}"
    body_repr = body if len(body) <= _MAX_BODY_PREVIEW else body[:_MAX_BODY_PREVIEW] + "\n…(truncated)"

    return _build_context(
        f"MANDATORY BODY FIX: mcp__github__create_pull_request corrupts stored PR "
        f"bodies with two defects — (1) & is HTML-encoded as &amp;, (2) a duplicate "
        f"footer is appended. Immediately call mcp__github__update_pull_request for "
        f"{pr_label} with the exact body below before taking any other action. "
        f"owner={owner or '(see tool_input)'}, repo={repo or '(see tool_input)'}, "
        f"pullNumber={pr_number}.\n\n"
        f"--- AUTHORED BODY (verbatim) ---\n{body_repr}\n--- END BODY ---"
    )


def main(argv: list[str] | None = None) -> int:
    del argv
    event = read_event("post_pr_create_body_fix")
    if event is None:
        return 0
    if not isinstance(event, dict):
        return 0
    emit_decision(decide(event))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
