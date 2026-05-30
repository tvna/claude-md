#!/usr/bin/env python3
"""PreToolUse hook: fast-path evidence check before closing a GitHub issue.

Bound in ``.claude/settings.json`` to ``mcp__github__issue_write`` when
``state`` is ``"closed"``.  Reads the PreToolUse event JSON from stdin;
when the action is a close, searches GitHub for merged PRs that explicitly
reference the issue number and emits ``additionalContext`` describing the
evidence.

**This hook is advisory only — it never emits ``permissionDecision: deny``.**
Its purpose is to bound the investigation to direct merged-PR evidence
*before* a wider parent/sibling-issue analysis is attempted (issue #187).

Fast-path algorithm
-------------------
1. Extract ``owner``, ``repo``, and ``issue_number`` from the tool input.
2. Search for merged PRs in the same repo that mention the issue number in
   their title or body (GitHub Search API: ``is:pr is:merged #{number}``).
3. Report findings:
   - Exactly one match → confirm state and surface title + URL.
   - Multiple matches  → list all; let the operator pick.
   - No matches        → warn that no direct merged-PR evidence was found
     and advise verifying resolution before closing.
4. If the API call fails, emit a warning and proceed fail-open (no output).

Failure mode: fail-open (exit 0, no output on error).  A hook failure must
never block issue closure; the operator retains full control.
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from typing import Any

_TARGET_TOOL = "mcp__github__issue_write"
_CLOSE_STATE = "closed"

_Runner = Callable[..., "subprocess.CompletedProcess[str]"]


# ---------------------------------------------------------------------------
# GitHub search helper
# ---------------------------------------------------------------------------


def _search_merged_prs(
    owner: str,
    repo: str,
    issue_number: int,
    *,
    runner: _Runner = subprocess.run,
) -> list[dict[str, Any]] | None:
    """Return merged PRs mentioning *issue_number*, or ``None`` on API error."""
    query = f"repo:{owner}/{repo} is:pr is:merged #{issue_number}"
    cmd = [
        "gh",
        "api",
        f"search/issues?q={query}&per_page=10",
        "--jq",
        ".items[] | {number: .number, title: .title, html_url: .html_url, closed_at: .closed_at}",
    ]
    try:
        result = runner(cmd, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        print(
            f"::warning::issue_closure_fast_path: gh search failed: {exc}",
            file=sys.stderr,
        )
        return None
    if result.returncode != 0:
        return None

    items: list[dict[str, Any]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(obj, dict):
            items.append(obj)
    return items


# ---------------------------------------------------------------------------
# Core logic
# ---------------------------------------------------------------------------


def _extract_close_target(
    tool_name: str,
    tool_input: dict[str, Any],
) -> tuple[str, str, int] | None:
    """Return ``(owner, repo, issue_number)`` if this is a close action.

    Returns ``None`` when the tool name does not match, the action is not a
    close, or required fields are absent/malformed.
    """
    if tool_name != _TARGET_TOOL:
        return None
    state = tool_input.get("state")
    if state != _CLOSE_STATE:
        return None
    owner = tool_input.get("owner")
    repo = tool_input.get("repo")
    raw_number = tool_input.get("issue_number")
    if not (isinstance(owner, str) and owner):
        return None
    if not (isinstance(repo, str) and repo):
        return None
    if isinstance(raw_number, int) and raw_number > 0:
        return owner, repo, raw_number
    if isinstance(raw_number, str) and raw_number.isdecimal():
        return owner, repo, int(raw_number)
    return None


def _format_context(
    owner: str,
    repo: str,
    issue_number: int,
    prs: list[dict[str, Any]],
) -> str:
    issue_ref = f"{owner}/{repo}#{issue_number}"
    if not prs:
        return (
            f"FAST-PATH WARNING: No merged PRs found that reference {issue_ref}. "
            "Verify that the issue is genuinely resolved before closing it. "
            "If resolution arrived through a commit without a PR, cite the commit SHA "
            "in the closing comment as evidence.  "
            "If the issue is a duplicate or will-not-fix, state the reason explicitly."
        )
    if len(prs) == 1:
        pr = prs[0]
        url = pr.get("html_url") or f"{owner}/{repo}#PR{pr.get('number')}"
        title = pr.get("title") or "(no title)"
        closed_at = pr.get("closed_at") or "unknown"
        return (
            f"FAST-PATH OK: Exactly one merged PR references {issue_ref}. "
            f"Verified: PR \"{title}\" ({url}) merged at {closed_at}. "
            "Closing this issue is consistent with direct merged-PR evidence. "
            "Attach the PR URL in the closing comment so the evidence is explicit."
        )
    lines = [
        f"FAST-PATH INFO: {len(prs)} merged PR(s) reference {issue_ref}. "
        "Verify which PR(s) directly resolve the issue before closing:"
    ]
    for pr in prs:
        url = pr.get("html_url") or f"PR#{pr.get('number')}"
        title = pr.get("title") or "(no title)"
        lines.append(f"  - {url} — {title}")
    lines.append(
        "Cite the relevant PR URL(s) in the closing comment as closure evidence."
    )
    return "\n".join(lines)


def decide(
    tool_name: str,
    tool_input: dict[str, Any],
    *,
    runner: _Runner = subprocess.run,
) -> dict[str, Any] | None:
    """Return advisory hook output, or ``None`` if no action is needed."""
    target = _extract_close_target(tool_name, tool_input)
    if target is None:
        return None

    owner, repo, issue_number = target
    prs = _search_merged_prs(owner, repo, issue_number, runner=runner)
    if prs is None:
        # API failure — fail-open, emit no output
        return None

    context = _format_context(owner, repo, issue_number, prs)
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "additionalContext": context,
        }
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    del argv
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(
            f"::error::issue_closure_fast_path: malformed stdin JSON: {exc}",
            file=sys.stderr,
        )
        return 0
    if not isinstance(event, dict):
        return 0

    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    output = decide(tool_name, tool_input)
    if output is not None:
        sys.stdout.write(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
