#!/usr/bin/env python3
"""Codex PostToolUse hook: probe PR CI once shortly after PR creation.

The normal PR monitoring loop still owns the terminal all-green/all-failed
state. This hook only spends one early probe after ``create_pull_request`` so
an already-failed check can be surfaced before every workflow completes.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
from collections.abc import Callable
from typing import Any

_TARGET_TOOL = "mcp__github__create_pull_request"
_DEFAULT_DELAY_SECONDS = 30.0
_FAIL_CONCLUSIONS: frozenset[str] = frozenset(
    {"failure", "failed", "cancelled", "canceled", "timed_out", "action_required"}
)
_PR_URL_RE = re.compile(r"https://github\.com/([^/\s]+/[^/\s]+)/pull/(\d+)")


def _walk_strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        out: list[str] = []
        for item in value.values():
            out.extend(_walk_strings(item))
        return out
    if isinstance(value, list):
        out = []
        for item in value:
            out.extend(_walk_strings(item))
        return out
    return []


def extract_pr_target(event: dict[str, Any]) -> tuple[str | None, str | None]:
    """Return ``(repo, pr)`` from a PostToolUse event when available."""
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        tool_input = {}

    repo = tool_input.get("repo") or tool_input.get("repository")
    if not isinstance(repo, str) or not repo.strip():
        repo = None
    else:
        repo = repo.strip()

    for key in ("number", "pull_number", "pr_number"):
        value = tool_input.get(key)
        if isinstance(value, int):
            return repo, str(value)
        if isinstance(value, str) and value.strip().isdigit():
            return repo, value.strip()

    strings = _walk_strings(event.get("tool_response"))
    strings.extend(_walk_strings(tool_input))
    for text in strings:
        match = _PR_URL_RE.search(text)
        if match:
            url_repo, number = match.groups()
            return repo or url_repo, number
    return repo, None


def parse_delay(environ: dict[str, str] | None = None) -> float:
    env = os.environ if environ is None else environ
    raw = env.get("CODEX_CI_EARLY_PROBE_DELAY_SECONDS")
    if raw is None:
        return _DEFAULT_DELAY_SECONDS
    try:
        delay = float(raw)
    except ValueError:
        return _DEFAULT_DELAY_SECONDS
    return max(0.0, delay)


def run_checks(
    repo: str | None,
    pr: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> subprocess.CompletedProcess[str]:
    cmd = ["gh", "pr", "checks", pr, "--json", "name,state,conclusion,workflow"]
    if repo:
        cmd.extend(["--repo", repo])
    return runner(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )


def _load_check_rows(stdout: str) -> list[dict[str, Any]]:
    try:
        parsed = json.loads(stdout) if stdout.strip() else []
    except json.JSONDecodeError:
        return []
    if not isinstance(parsed, list):
        return []
    return [row for row in parsed if isinstance(row, dict)]


def failed_checks(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    failed: list[dict[str, Any]] = []
    for row in rows:
        conclusion = str(row.get("conclusion") or "").lower()
        state = str(row.get("state") or "").lower()
        if conclusion in _FAIL_CONCLUSIONS or state in _FAIL_CONCLUSIONS:
            failed.append(row)
    return failed


def _check_name(row: dict[str, Any]) -> str:
    name = row.get("name")
    workflow = row.get("workflow")
    if isinstance(workflow, str) and workflow and isinstance(name, str) and name:
        return f"{workflow} / {name}"
    if isinstance(name, str) and name:
        return name
    if isinstance(workflow, str) and workflow:
        return workflow
    return "(unnamed check)"


def build_additional_context(
    repo: str | None,
    pr: str,
    failed: list[dict[str, Any]],
    delay_seconds: float,
) -> dict[str, Any]:
    label = f"{repo}#{pr}" if repo else f"PR #{pr}"
    lines = [
        f"CI early status probe: after {delay_seconds:g}s, {label} already has failing checks.",
        "Treat this as the current repair signal; inspect the failing check logs before waiting for the full CI monitor.",
        "",
        "Failing checks:",
    ]
    for row in failed[:10]:
        conclusion = row.get("conclusion") or row.get("state") or "unknown"
        lines.append(f"- {_check_name(row)}: {conclusion}")
    if len(failed) > 10:
        lines.append(f"- ... {len(failed) - 10} more")
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": "\n".join(lines),
        }
    }


def decide(
    event: dict[str, Any],
    *,
    sleeper: Callable[[float], None] = time.sleep,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    environ: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    if event.get("tool_name") != _TARGET_TOOL:
        return None

    repo, pr = extract_pr_target(event)
    if pr is None:
        return None

    delay = parse_delay(environ)
    sleeper(delay)

    try:
        result = run_checks(repo, pr, runner=runner)
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"::warning::ci_early_status_probe: gh pr checks failed: {exc}", file=sys.stderr)
        return None

    rows = _load_check_rows(result.stdout)
    failed = failed_checks(rows)
    if not failed:
        return None
    return build_additional_context(repo, pr, failed, delay)


def main(argv: list[str] | None = None) -> int:
    del argv
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(f"::error::ci_early_status_probe: malformed stdin JSON: {exc}", file=sys.stderr)
        return 0
    if not isinstance(event, dict):
        return 0
    decision = decide(event)
    if decision is not None:
        sys.stdout.write(json.dumps(decision))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
