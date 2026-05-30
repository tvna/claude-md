#!/usr/bin/env python3
"""Detect merge conflicts early via mergeability polling.

## Modes

**PostToolUse** (default, reads JSON from stdin):
After ``mcp__github__create_pull_request`` or
``mcp__github__update_pull_request_branch``, polls
``GET /repos/{owner}/{repo}/pulls/{number}`` until the ``mergeable`` field
is non-null (GitHub computes mergeability asynchronously), then surfaces
``mergeable_state`` to the agent:

- ``clean``   -> no action needed.
- ``dirty``   -> instruct agent to rebase/merge immediately.
- ``blocked`` / ``unknown`` -> advisory only.

**SessionStart** (CLI: ``python3 scripts/check_pr_mergeability.py session-start``):
Scans open PRs authored by the session user for ``mergeable_state: dirty``
and emits a banner if any are found, so a resumed session catches stale
branches immediately.

## Failure mode

Both modes are fail-open (exit 0). Mergeability detection is advisory;
a failure here must never block PR creation or session startup.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Any

_POST_TOOL_USE_TARGETS: frozenset[str] = frozenset(
    {
        "mcp__github__create_pull_request",
        "mcp__github__update_pull_request_branch",
    }
)

_PR_URL_RE = re.compile(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/pull/(\d+)")
_OWNER_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")

_POLL_INTERVAL_SECONDS = 2.0
_MAX_POLLS = 10

_Runner = Callable[..., "subprocess.CompletedProcess[str]"]


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


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


def _extract_pr_info(event: dict[str, Any]) -> tuple[str | None, str | None, str | None]:
    """Return ``(owner, repo, pr_number)`` from a PostToolUse event."""
    tool_input = event.get("tool_input") or {}
    tool_response = event.get("tool_response")

    # Try PR URL first (most reliable)
    for node in _walk(tool_response) + _walk(tool_input):
        if isinstance(node, str):
            m = _PR_URL_RE.search(node)
            if m:
                return m.group(1), m.group(2), m.group(3)

    # Fallback: structured fields
    owner = tool_input.get("owner") if isinstance(tool_input, dict) else None
    repo = tool_input.get("repo") if isinstance(tool_input, dict) else None

    for node in _walk(tool_response):
        if not isinstance(node, dict):
            continue
        for key in ("number", "pullRequestNumber", "pull_request_number", "pr_number"):
            val = node.get(key)
            if isinstance(val, int) and val > 0:
                return owner, repo, str(val)
            if isinstance(val, str) and val.isdecimal():
                return owner, repo, val

    return None, None, None


def _gh_api(
    path: str,
    *,
    runner: _Runner = subprocess.run,
) -> dict[str, Any] | None:
    """Call ``gh api {path}`` and return parsed JSON, or None on error."""
    cmd = ["gh", "api", path]
    try:
        result = runner(cmd, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"::warning::check_pr_mergeability: gh api failed: {exc}", file=sys.stderr)
        return None
    if result.returncode != 0:
        return None
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _poll_mergeability(
    owner: str,
    repo: str,
    pr_number: str,
    *,
    runner: _Runner = subprocess.run,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any] | None:
    """Poll until ``mergeable`` is non-null; return the PR data or None."""
    path = f"repos/{owner}/{repo}/pulls/{pr_number}"
    for attempt in range(_MAX_POLLS):
        if attempt > 0:
            sleeper(_POLL_INTERVAL_SECONDS)
        data = _gh_api(path, runner=runner)
        if data is None:
            return None
        if data.get("mergeable") is not None:
            return data
    # Last attempt timed out; return whatever we have (data is dict | None here)
    return data


def _build_context(message: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": message,
        }
    }


# ---------------------------------------------------------------------------
# PostToolUse mode
# ---------------------------------------------------------------------------


def decide_post_tool_use(
    event: dict[str, Any],
    *,
    runner: _Runner = subprocess.run,
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any] | None:
    """Return hook output for a PostToolUse event, or None if no action needed."""
    if event.get("tool_name") not in _POST_TOOL_USE_TARGETS:
        return None

    owner, repo, pr_number = _extract_pr_info(event)
    if pr_number is None:
        return _build_context(
            "Mergeability check skipped: could not extract PR number from tool response. "
            "Manually run `gh pr view <pr> --json mergeable,mergeableState` to check "
            "whether the branch has conflicts before proceeding."
        )

    pr_label = f"{owner}/{repo}#{pr_number}" if owner and repo else f"PR #{pr_number}"

    if owner is None or repo is None:
        # Cannot poll without owner+repo
        return _build_context(
            f"Mergeability check skipped for {pr_label}: owner/repo could not be "
            "determined. Manually run `gh pr view <pr> --json mergeable,mergeableState` "
            "to check for conflicts."
        )

    pr_data = _poll_mergeability(owner, repo, pr_number, runner=runner, sleeper=sleeper)
    if pr_data is None:
        return _build_context(
            f"Mergeability check failed for {pr_label}: GitHub API call failed. "
            "Manually verify `gh pr view <pr> --json mergeable,mergeableState`."
        )

    mergeable = pr_data.get("mergeable")
    state = str(pr_data.get("mergeable_state") or "unknown").lower()

    if mergeable is None:
        return _build_context(
            f"Mergeability check timed out for {pr_label}: GitHub has not yet computed "
            f"mergeability after {_MAX_POLLS} polls. Run "
            "`gh pr view <pr> --json mergeable,mergeableState` shortly to verify."
        )

    if state == "dirty":
        return _build_context(
            f"MERGE CONFLICT DETECTED: {pr_label} has mergeable_state=dirty. "
            "The branch has conflicts with the base branch. "
            "Rebase or merge the base branch into your branch immediately before proceeding: "
            "`git fetch origin && git rebase origin/<base>` (or `git merge origin/<base>`), "
            "then force-push and re-run checks."
        )

    if state == "clean":
        return _build_context(f"Mergeability OK: {pr_label} has mergeable_state=clean. No conflicts detected.")

    # blocked / unknown / draft / etc — advisory
    return _build_context(
        f"Mergeability advisory for {pr_label}: mergeable_state={state}. "
        "This may indicate required status checks are pending (blocked) or "
        "that mergeability is still being computed (unknown). "
        "Re-check with `gh pr view <pr> --json mergeable,mergeableState` once CI settles."
    )


# ---------------------------------------------------------------------------
# SessionStart mode
# ---------------------------------------------------------------------------


def _list_open_prs(*, runner: _Runner = subprocess.run) -> list[dict[str, Any]]:
    """Return open PRs from the current repo authored by the session user."""
    cmd = [
        "gh",
        "pr",
        "list",
        "--author",
        "@me",
        "--state",
        "open",
        "--json",
        "number,headRepositoryOwner,headRepository,url",
        "--limit",
        "20",
    ]
    try:
        result = runner(cmd, capture_output=True, text=True, timeout=30, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"::warning::check_pr_mergeability: gh pr list failed: {exc}", file=sys.stderr)
        return []
    if result.returncode != 0:
        return []
    try:
        data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def run_session_start(
    *,
    runner: _Runner = subprocess.run,
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    """Scan open PRs for dirty mergeability and print a banner if any found."""
    prs = _list_open_prs(runner=runner)
    if not prs:
        return

    dirty: list[str] = []
    for pr in prs:
        number = str(pr.get("number") or "")
        if not number:
            continue
        owner_obj = pr.get("headRepositoryOwner") or {}
        owner = owner_obj.get("login") if isinstance(owner_obj, dict) else None
        repo_obj = pr.get("headRepository") or {}
        repo = repo_obj.get("name") if isinstance(repo_obj, dict) else None
        if not owner or not repo:
            continue
        pr_data = _poll_mergeability(owner, repo, number, runner=runner, sleeper=sleeper)
        if pr_data is None:
            continue
        state = str(pr_data.get("mergeable_state") or "").lower()
        if state == "dirty":
            url = pr.get("url") or f"{owner}/{repo}#{number}"
            dirty.append(url)

    if dirty:
        lines = ["MERGE CONFLICT WARNING: the following open PRs have merge conflicts (mergeable_state=dirty):"]
        for url in dirty:
            lines.append(f"  - {url}")
        lines.append("Rebase or merge the base branch into each branch before continuing work.")
        print("\n".join(lines))


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    if args and args[0] == "session-start":
        run_session_start()
        return 0

    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(f"::error::check_pr_mergeability: malformed stdin JSON: {exc}", file=sys.stderr)
        return 0
    if not isinstance(event, dict):
        return 0
    output = decide_post_tool_use(event)
    if output is not None:
        sys.stdout.write(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
