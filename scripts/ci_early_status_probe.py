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
import sys
import time
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _github_api import apply_call

_TARGET_TOOLS: frozenset[str] = frozenset(
    {
        "mcp__github__create_pull_request",
        "mcp__codex_apps__github._create_pull_request",
    }
)
_DEFAULT_DELAY_SECONDS = 30.0
_FAIL_CONCLUSIONS: frozenset[str] = frozenset(
    {"failure", "failed", "cancelled", "canceled", "timed_out", "action_required"}
)
_PR_URL_RE = re.compile(r"https://github\.com/([^/\s]+/[^/\s]+)/pull/(\d+)")

_Opener = Callable[[urllib.request.Request], Any]


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


def _rest_get(path: str, *, token: str, opener: _Opener = urllib.request.urlopen) -> tuple[int, Any]:
    """Return (status_code, parsed_json_or_None) for a GET request."""
    url = f"https://api.github.com/{path}"
    try:
        code, body = apply_call(method="GET", url=url, payload=None, token=token, opener=opener)
    except Exception as exc:
        print(f"::warning::ci_early_status_probe: API call failed: {exc}", file=sys.stderr)
        return 0, None
    try:
        return code, json.loads(body)
    except json.JSONDecodeError:
        return code, None


def run_checks(
    repo: str | None,
    pr: str,
    *,
    opener: _Opener = urllib.request.urlopen,
    token: str = "",
) -> list[dict[str, Any]]:
    """Return check rows for *pr* in *repo*, or empty list on error.

    Each row has ``name``, ``state``, ``conclusion``, and optionally
    ``workflow`` (workflow run name, when determinable).
    """
    actual_token = token or os.environ.get("GH_TOKEN", "")
    if not actual_token:
        print("::warning::ci_early_status_probe: GH_TOKEN not set", file=sys.stderr)
        return []

    if not repo or "/" not in repo:
        print(f"::warning::ci_early_status_probe: cannot determine owner/repo from {repo!r}", file=sys.stderr)
        return []

    owner, repo_name = repo.split("/", 1)

    # Resolve head SHA from PR number
    code, pr_data = _rest_get(f"repos/{repo}/pulls/{pr}", token=actual_token, opener=opener)
    if not isinstance(pr_data, dict) or not (200 <= code < 300):
        print(f"::warning::ci_early_status_probe: gh pr checks failed: HTTP {code} fetching PR", file=sys.stderr)
        return []
    sha = (pr_data.get("head") or {}).get("sha")
    if not isinstance(sha, str):
        return []

    # Fetch check runs
    code, checks_data = _rest_get(
        f"repos/{repo}/commits/{sha}/check-runs?per_page=100",
        token=actual_token,
        opener=opener,
    )
    if not isinstance(checks_data, dict) or not (200 <= code < 300):
        print(f"::warning::ci_early_status_probe: gh pr checks failed: HTTP {code} fetching check runs", file=sys.stderr)
        return []
    check_runs = checks_data.get("check_runs") or []

    # Fetch workflow runs to map check_suite_id → workflow name
    wf_map: dict[str, str] = {}
    wf_code, wf_data = _rest_get(
        f"repos/{repo}/actions/runs?head_sha={sha}&per_page=50",
        token=actual_token,
        opener=opener,
    )
    if isinstance(wf_data, dict) and 200 <= wf_code < 300:
        for wf_run in wf_data.get("workflow_runs") or []:
            if not isinstance(wf_run, dict):
                continue
            cs_id = str(wf_run.get("check_suite_id") or wf_run.get("check_suite", {}).get("id") or "")
            wf_name = wf_run.get("name") or ""
            if cs_id and wf_name:
                wf_map[cs_id] = wf_name

    # Normalise to the structure expected by _load_check_rows / failed_checks
    rows: list[dict[str, Any]] = []
    for run in check_runs:
        if not isinstance(run, dict):
            continue
        cs_id = str((run.get("check_suite") or {}).get("id") or "")
        rows.append(
            {
                "name": run.get("name") or "",
                "state": (run.get("status") or "").upper(),
                "conclusion": run.get("conclusion") or "",
                "workflow": wf_map.get(cs_id, ""),
            }
        )
    return rows


def _load_check_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [row for row in rows if isinstance(row, dict)]


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
    opener: _Opener = urllib.request.urlopen,
    token: str = "",
    environ: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    if event.get("tool_name") not in _TARGET_TOOLS:
        return None

    repo, pr = extract_pr_target(event)
    if pr is None:
        return None

    delay = parse_delay(environ)
    sleeper(delay)

    try:
        rows = run_checks(repo, pr, opener=opener, token=token)
    except (OSError, Exception) as exc:
        print(f"::warning::ci_early_status_probe: gh pr checks failed: {exc}", file=sys.stderr)
        return None

    loaded = _load_check_rows(rows)
    failed = failed_checks(loaded)
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
