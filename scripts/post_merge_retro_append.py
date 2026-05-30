#!/usr/bin/env python3
"""PostToolUse hook: direct agent to append repair analysis to auto-retro after merge.

When mcp__github__merge_pull_request completes, CI post-merge.yml will
automatically open a retro issue titled "fix(auto-retro): review PR #NNN ...".
Without a hook, the agent also creates a second retro (CLAUDE.md section 3),
producing duplicate issues. Observed on PR #908: auto-retro #914 + agent #915.

This hook emits additionalContext that:
  1. Forbids creating a new retro issue when an auto-retro already exists.
  2. Instructs the agent to search for the auto-retro (title prefix
     "fix(auto-retro)", containing "PR #NNN") and append its repair analysis
     as a comment via mcp__github__add_issue_comment.
  3. Allows creating a new issue only when the CI retro never appears
     (e.g. workflow skipped).

Fail-open: malformed input, missing fields, or off-target tools exit 0 with
no output so a hook bug cannot block unrelated tool calls.

Refs: issue #916.
"""

from __future__ import annotations

import json
import re
import sys
from typing import Any

TARGET_TOOL = "mcp__github__merge_pull_request"

_PR_URL_RE = re.compile(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/pull/(\d+)")
_NUMBER_KEYS = frozenset({"number", "pullRequestNumber", "pull_request_number", "pr_number"})


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
    """Return (owner, repo, pr_number) from the merge event fields.

    Prefers a PR URL in tool_response; falls back to structured number
    fields combined with owner/repo from tool_input.
    """
    for node in _walk(tool_response):
        if isinstance(node, str):
            m = _PR_URL_RE.search(node)
            if m:
                return m.group(1), m.group(2), m.group(3)

    owner = tool_input.get("owner") if isinstance(tool_input, dict) else None
    repo = tool_input.get("repo") if isinstance(tool_input, dict) else None

    # PR number may live in tool_input for merge (pullRequestNumber)
    if isinstance(tool_input, dict):
        for key in _NUMBER_KEYS:
            val = tool_input.get(key)
            if isinstance(val, int) and val > 0:
                return owner, repo, str(val)
            if isinstance(val, str) and val.isdecimal():
                return owner, repo, val

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
    """Return hook output for a PostToolUse merge event, or None if no action needed."""
    if event.get("tool_name") != TARGET_TOOL:
        return None

    tool_input = event.get("tool_input") or {}
    tool_response = event.get("tool_response")

    owner, repo, pr_number = extract_merge_coords(
        tool_input if isinstance(tool_input, dict) else {}, tool_response
    )

    if pr_number is None:
        return _build_context(
            "RETRO APPEND: merge detected but PR number could not be extracted. "
            "Manually search for an auto-retro issue titled "
            "'fix(auto-retro): review PR #NNN' and append your repair analysis "
            "as a comment. Do NOT create a new retro issue if one already exists."
        )

    owner_str = owner or "(see tool_input)"
    repo_str = repo or "(see tool_input)"
    repo_slug = f"{owner}/{repo}" if owner and repo else repo_str

    return _build_context(
        f"MANDATORY RETRO APPEND: PR #{pr_number} in {repo_slug} was just merged. "
        f"CI post-merge.yml will create an auto-retro issue automatically. "
        f"Follow this two-step procedure BEFORE creating any new issue:\n\n"
        f"STEP 1 — SEARCH: Use mcp__github__search_issues to find an open issue in "
        f"owner={owner_str}, repo={repo_str} whose title starts with "
        f"'fix(auto-retro)' and contains 'PR #{pr_number}'. "
        f"The CI workflow may take up to 2 minutes; if the issue is not found "
        f"immediately, wait briefly and search again (up to ~3 attempts).\n\n"
        f"STEP 2 — APPEND: Once found, call mcp__github__add_issue_comment on that "
        f"issue to add your repair analysis: list every repair made between PR open "
        f"and merge, identify the earliest deterministic gate that should have "
        f"prevented each repair, and state how the next run will reproduce the "
        f"no-repair path. Classify each repair as: missing deterministic gate, "
        f"unclear agent instruction, or external/human decision.\n\n"
        f"FALLBACK (use only if no auto-retro appears after ~3 searches): "
        f"Create a new retro issue titled "
        f"'fix(auto-retro): review PR #{pr_number} repair loops' "
        f"and include the repair analysis in the body.\n\n"
        f"FORBIDDEN: Do NOT create a new retro issue when an auto-retro already exists."
    )


def main(argv: list[str] | None = None) -> int:
    del argv
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(f"::error::post_merge_retro_append: malformed stdin JSON: {exc}", file=sys.stderr)
        return 0
    if not isinstance(event, dict):
        return 0
    output = decide(event)
    if output is not None:
        sys.stdout.write(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
