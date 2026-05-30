#!/usr/bin/env python3
"""PostToolUse hook: start polling-based CI monitoring after MCP PR creation.

## Monitoring kind: polling/heartbeat

This hook launches ``gh pr checks --watch`` as a detached polling process.
It polls the GitHub API on a fixed interval until all checks settle. It is
NOT a webhook-backed monitor: there is no GitHub App event subscription, no
``workflow_run``/``check_suite`` push path, and no delivery guarantee.

Webhook-backed monitoring is provided by the ``subscribe_pr_activity`` MCP
tool (Claude Code session layer). Use that tool when low-latency, push-based
delivery is required. This hook is a deterministic polling fallback that runs
immediately after ``mcp__github__create_pull_request`` returns, before the
agent has had a chance to call ``subscribe_pr_activity``.

## Event source and delivery path

| Property         | This hook                          | Webhook path                      |
|------------------|------------------------------------|-----------------------------------|
| Trigger          | PostToolUse (``create_pull_request``) | GitHub App / ``check_suite`` push |
| Delivery         | ``gh pr checks --watch`` poll loop | HTTP POST to registered endpoint  |
| Latency          | Poll interval (≥ 10 s)             | Near real-time                    |
| Retry on failure | None — fire-and-forget subprocess  | GitHub redeliver mechanism        |
| Failure mode     | Log written to ``/tmp``; silent    | HTTP error logged by GitHub       |

## Early-failure watch phase vs steady-state heartbeat

The ``gh pr checks --watch`` poll this hook launches runs immediately after
PR creation and is the *early-failure watch phase*: it detects an
already-failed required check without waiting for a long session-level
heartbeat interval. The ``additionalContext`` returned to the agent makes
this explicit and instructs it to keep immediate/short-interval checks until
the required checks reach a terminal state, falling back to a longer
steady-state heartbeat interval only after that initial CI signal is known.
This closes the gap observed on PR #778 (issue #781), where a 30-minute
heartbeat monitor was the only signal and reported a CI failure late.

## Failure mode

If ``Popen`` fails, the hook returns an ``additionalContext`` error message
and exits 0 (fail-open). PR creation has already happened by the time
``PostToolUse`` runs, so blocking here would be counterproductive.

The hook never logs the full tool payload.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

TARGET_TOOLS: frozenset[str] = frozenset(
    {
        "mcp__github__create_pull_request",
        "mcp__codex_apps__github._create_pull_request",
    }
)
# Kept for backward compatibility with existing tests that reference the legacy name.
TARGET_TOOL = "mcp__github__create_pull_request"
GITHUB_PR_URL_RE = re.compile(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+/pull/([0-9]+)")
URL_KEYS = frozenset({"url", "html_url", "web_url", "pull_request_url"})
NUMBER_KEYS = frozenset({"number", "pullRequestNumber", "pull_request_number", "pr_number"})
REPO_KEYS = frozenset({"repo", "repository", "repository_full_name", "nameWithOwner"})


def _walk(value: Any) -> list[Any]:
    """Return a shallow bounded walk over JSON-like data."""
    out: list[Any] = []
    stack = [value]
    while stack and len(out) < 200:
        current = stack.pop()
        out.append(current)
        if isinstance(current, dict):
            stack.extend(current.values())
        elif isinstance(current, list):
            stack.extend(current)
    return out


def extract_pr_url(value: Any) -> str | None:
    """Return the first GitHub PR URL found in *value*."""
    for item in _walk(value):
        if isinstance(item, dict):
            for key, maybe_url in item.items():
                if key in URL_KEYS and isinstance(maybe_url, str):
                    match = GITHUB_PR_URL_RE.search(maybe_url)
                    if match is not None:
                        return match.group(0)
        elif isinstance(item, str):
            match = GITHUB_PR_URL_RE.search(item)
            if match is not None:
                return match.group(0)
    return None


def extract_pr_number(value: Any) -> str | None:
    """Return the first PR number found in *value*."""
    for item in _walk(value):
        if not isinstance(item, dict):
            continue
        for key, maybe_number in item.items():
            if key not in NUMBER_KEYS:
                continue
            if isinstance(maybe_number, int) and maybe_number > 0:
                return str(maybe_number)
            if isinstance(maybe_number, str) and maybe_number.isdecimal():
                return maybe_number
    return None


def extract_repo(value: Any) -> str | None:
    """Return an ``owner/repo`` string from hook input when present."""
    for item in _walk(value):
        if not isinstance(item, dict):
            continue
        owner = item.get("owner")
        name = item.get("repo") or item.get("repository") or item.get("name")
        if isinstance(owner, str) and isinstance(name, str):
            candidate = f"{owner}/{name}"
            if _is_owner_repo(candidate):
                return candidate
        for key, maybe_repo in item.items():
            if key in REPO_KEYS and isinstance(maybe_repo, str) and _is_owner_repo(maybe_repo):
                return maybe_repo
    return None


def _is_owner_repo(value: str) -> bool:
    parts = value.split("/")
    return len(parts) == 2 and all(re.fullmatch(r"[A-Za-z0-9_.-]+", part) for part in parts)


def build_watch_command(event: dict[str, Any]) -> tuple[list[str], str] | None:
    """Return ``(argv, pr_ref)`` for the CI watch command."""
    response = event.get("tool_response")
    tool_input = event.get("tool_input") if isinstance(event.get("tool_input"), dict) else {}

    pr_url = extract_pr_url(response)
    if pr_url is not None:
        return ["gh", "pr", "checks", pr_url, "--watch"], pr_url

    pr_number = extract_pr_number(response)
    if pr_number is None:
        return None

    argv = ["gh", "pr", "checks", pr_number, "--watch"]
    repo = extract_repo(tool_input)
    if repo is not None:
        argv.extend(["--repo", repo])
    return argv, pr_number


def start_monitor(argv: list[str], *, cwd: str | None = None) -> Path:
    """Start the CI monitor detached from the hook process and return its log path."""
    pr_label = re.sub(r"[^A-Za-z0-9_.-]+", "-", argv[3]).strip("-") or "unknown"
    log_path = Path(tempfile.gettempdir()) / f"claude-md-pr-ci-monitor-{pr_label}.log"
    try:
        with log_path.open("ab") as log:
            subprocess.Popen(  # noqa: S603 - argv is built by build_watch_command.
                argv,
                cwd=cwd or None,
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=subprocess.STDOUT,
                close_fds=True,
                start_new_session=True,
            )
    except Exception:
        raise
    return log_path


def build_context(message: str) -> dict[str, Any]:
    """Return PostToolUse additional context for the agent."""
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": message,
        }
    }


def decide(event: dict[str, Any]) -> dict[str, Any] | None:
    """Return hook output for a PostToolUse event."""
    if event.get("tool_name") not in TARGET_TOOLS:
        return None

    command = build_watch_command(event)
    if command is None:
        return build_context(
            "PR polling/heartbeat CI monitor was not started automatically: "
            "the MCP create_pull_request response did not contain a PR URL or "
            "number. Immediately run `gh pr checks <pr> --watch` (polling) as "
            "the early-failure watch phase, and keep checking on a short "
            "interval until the required checks reach a terminal state, before "
            "considering the PR handoff complete. Only then fall back to a "
            "longer steady-state heartbeat interval. For webhook-backed "
            "monitoring, call subscribe_pr_activity instead."
        )

    argv, pr_ref = command
    cwd = event.get("cwd") if isinstance(event.get("cwd"), str) else str(Path.cwd())
    try:
        log_path = start_monitor(argv, cwd=cwd)
    except OSError as exc:
        return build_context(
            "PR polling/heartbeat CI monitor failed to start automatically "
            f"after MCP PR creation for {pr_ref}: {exc}. Immediately run "
            f"`{' '.join(argv)}` (polling) as the early-failure watch phase, "
            "and keep checking on a short interval until the required checks "
            "reach a terminal state, before considering the PR handoff "
            "complete. Only then fall back to a longer steady-state heartbeat "
            "interval. For webhook-backed monitoring, call "
            "subscribe_pr_activity instead."
        )

    return build_context(
        "PR polling/heartbeat CI monitor started automatically after MCP PR "
        f"creation for {pr_ref}. Monitor log: {log_path}. This is a "
        "polling/heartbeat monitor (gh pr checks --watch); it is NOT "
        "webhook-backed. For push-based delivery, also call "
        "subscribe_pr_activity. This immediate watch is the early-failure "
        "watch phase: stay on immediate or short-interval CI checks until the "
        "required checks reach a terminal state (or a timeout window expires) "
        "so an already-failed check is detected without waiting for a long "
        "heartbeat interval. Only after that initial CI signal is known should "
        "you fall back to a longer steady-state heartbeat interval. Continue "
        "tracking CI, reviews, and comments until the PR reaches a terminal "
        "state."
    )


def main(argv: list[str] | None = None) -> int:
    del argv
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(f"::error::post_pr_create_ci_monitor: malformed stdin JSON: {exc}", file=sys.stderr)
        return 0

    if not isinstance(event, dict):
        return 0
    output = decide(event)
    if output is not None:
        sys.stdout.write(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
