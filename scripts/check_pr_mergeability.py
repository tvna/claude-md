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
import os
import re
import subprocess
import sys
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _github_api import apply_call
from _hook_runtime import emit_decision, read_event

_POST_TOOL_USE_TARGETS: frozenset[str] = frozenset(
    {
        "mcp__github__create_pull_request",
        "mcp__github__update_pull_request_branch",
    }
)

_PR_URL_RE = re.compile(r"https://github\.com/([A-Za-z0-9_.-]+)/([A-Za-z0-9_.-]+)/pull/(\d+)")
_OWNER_REPO_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
_GIT_REMOTE_RE = re.compile(r"github\.com[/:]([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?\s*$")

_POLL_INTERVAL_SECONDS = 2.0
_MAX_POLLS = 10

_Opener = Callable[[urllib.request.Request], Any]
_API_BASE = "https://api.github.com/"


# ---------------------------------------------------------------------------
# REST API helpers
# ---------------------------------------------------------------------------


def _get_token() -> str:
    return os.environ.get("GH_TOKEN", "")


def _rest_get(path: str, *, token: str, opener: _Opener = urllib.request.urlopen) -> dict[str, Any] | None:
    """Call GET /api.github.com/{path} and return parsed JSON object, or None."""
    if not token:
        return None
    url = f"{_API_BASE}{path}"
    try:
        code, body = apply_call(method="GET", url=url, payload=None, token=token, opener=opener)
    except Exception as exc:
        print(f"::warning::check_pr_mergeability: API call failed: {exc}", file=sys.stderr)
        return None
    if not (200 <= code < 300):
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None


def _rest_get_list(path: str, *, token: str, opener: _Opener = urllib.request.urlopen) -> list[Any] | None:
    """Call GET /api.github.com/{path} and return parsed JSON list, or None."""
    if not token:
        return None
    url = f"{_API_BASE}{path}"
    try:
        code, body = apply_call(method="GET", url=url, payload=None, token=token, opener=opener)
    except Exception as exc:
        print(f"::warning::check_pr_mergeability: API call failed: {exc}", file=sys.stderr)
        return None
    if not (200 <= code < 300):
        return None
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, list) else None


def _detect_repo() -> str | None:
    """Return owner/repo from GITHUB_REPOSITORY env var or git remote origin."""
    repo = os.environ.get("GITHUB_REPOSITORY", "")
    if repo and _OWNER_REPO_RE.match(repo):
        return repo
    try:
        result = subprocess.run(  # noqa: S603 — fixed args, not user input
            ["git", "remote", "get-url", "origin"],  # noqa: S607
            capture_output=True, text=True, timeout=5, check=False,
        )
        if result.returncode == 0:
            m = _GIT_REMOTE_RE.search(result.stdout.strip())
            if m:
                return m.group(1)
    except (OSError, subprocess.SubprocessError):
        pass
    return None


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


def _poll_mergeability(
    owner: str,
    repo: str,
    pr_number: str,
    *,
    opener: _Opener = urllib.request.urlopen,
    token: str = "",
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any] | None:
    """Poll until ``mergeable`` is non-null; return the PR data or None."""
    actual_token = token or _get_token()
    path = f"repos/{owner}/{repo}/pulls/{pr_number}"
    data: dict[str, Any] | None = None
    for attempt in range(_MAX_POLLS):
        if attempt > 0:
            sleeper(_POLL_INTERVAL_SECONDS)
        data = _rest_get(path, token=actual_token, opener=opener)
        if data is None:
            return None
        if data.get("mergeable") is not None:
            return data
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
    opener: _Opener = urllib.request.urlopen,
    token: str = "",
    sleeper: Callable[[float], None] = time.sleep,
) -> dict[str, Any] | None:
    """Return hook output for a PostToolUse event, or None if no action needed."""
    if event.get("tool_name") not in _POST_TOOL_USE_TARGETS:
        return None

    owner, repo, pr_number = _extract_pr_info(event)
    if pr_number is None:
        return _build_context(
            "Mergeability check skipped: could not extract PR number from tool response. "
            "Manually verify the PR mergeable_state via the GitHub REST API or UI "
            "before proceeding."
        )

    pr_label = f"{owner}/{repo}#{pr_number}" if owner and repo else f"PR #{pr_number}"

    if owner is None or repo is None:
        return _build_context(
            f"Mergeability check skipped for {pr_label}: owner/repo could not be "
            "determined. Verify the PR mergeable_state via the GitHub REST API or UI."
        )

    pr_data = _poll_mergeability(owner, repo, pr_number, opener=opener, token=token, sleeper=sleeper)
    if pr_data is None:
        return _build_context(
            f"Mergeability check failed for {pr_label}: GitHub API call failed. "
            "Manually verify the PR mergeable_state via the GitHub REST API or UI."
        )

    mergeable = pr_data.get("mergeable")
    state = str(pr_data.get("mergeable_state") or "unknown").lower()

    if mergeable is None:
        return _build_context(
            f"Mergeability check timed out for {pr_label}: GitHub has not yet computed "
            f"mergeability after {_MAX_POLLS} polls. Re-check the PR mergeable_state "
            "shortly via the GitHub REST API or UI."
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
        "Re-check the PR mergeable_state once CI settles."
    )


# ---------------------------------------------------------------------------
# SessionStart mode
# ---------------------------------------------------------------------------


def _list_open_prs(
    *,
    opener: _Opener = urllib.request.urlopen,
    token: str = "",
) -> list[dict[str, Any]]:
    """Return open PRs authored by the session user in the current repo."""
    actual_token = token or _get_token()
    if not actual_token:
        return []

    user_data = _rest_get("user", token=actual_token, opener=opener)
    if user_data is None:
        return []
    login = user_data.get("login")
    if not isinstance(login, str) or not login:
        return []

    repo_str = _detect_repo()
    if not repo_str:
        return []

    prs = _rest_get_list(
        f"repos/{repo_str}/pulls?state=open&per_page=20",
        token=actual_token,
        opener=opener,
    )
    if prs is None:
        return []

    result = []
    for pr in prs:
        if not isinstance(pr, dict):
            continue
        pr_user = pr.get("user") or {}
        if not isinstance(pr_user, dict) or pr_user.get("login") != login:
            continue
        number = pr.get("number")
        url = pr.get("html_url") or ""
        head = pr.get("head") or {}
        head_repo = head.get("repo") or {}
        owner_login = (head_repo.get("owner") or {}).get("login") or ""
        repo_name = head_repo.get("name") or ""
        result.append(
            {
                "number": number,
                "url": url,
                "headRepositoryOwner": {"login": owner_login},
                "headRepository": {"name": repo_name},
            }
        )
    return result


def run_session_start(
    *,
    opener: _Opener = urllib.request.urlopen,
    token: str = "",
    sleeper: Callable[[float], None] = time.sleep,
) -> None:
    """Scan open PRs for dirty/behind mergeability and print banners if any found."""
    prs = _list_open_prs(opener=opener, token=token)
    if not prs:
        return

    dirty: list[str] = []
    behind: list[str] = []
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
        pr_data = _poll_mergeability(owner, repo, number, opener=opener, token=token, sleeper=sleeper)
        if pr_data is None:
            continue
        state = str(pr_data.get("mergeable_state") or "").lower()
        url = pr.get("url") or f"{owner}/{repo}#{number}"
        if state == "dirty":
            dirty.append(url)
        elif state == "behind":
            behind.append(url)

    if dirty:
        lines = ["MERGE CONFLICT WARNING: the following open PRs have merge conflicts (mergeable_state=dirty):"]
        for url in dirty:
            lines.append(f"  - {url}")
        lines.append("Rebase or merge the base branch into each branch before continuing work.")
        print("\n".join(lines))

    if behind:
        lines = ["OUT-OF-DATE WARNING: the following open PRs are behind their base branch (mergeable_state=behind):"]
        for url in behind:
            lines.append(f"  - {url}")
        lines.append(
            "Update each branch before pushing new commits: "
            "`git fetch origin && git rebase origin/<base>` (or `git merge origin/<base>`), "
            "then force-push."
        )
        print("\n".join(lines))


# ---------------------------------------------------------------------------
# Entry points
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    if args and args[0] == "session-start":
        run_session_start()
        return 0

    event = read_event("check_pr_mergeability")
    if event is None or not isinstance(event, dict):
        return 0
    emit_decision(decide_post_tool_use(event))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
