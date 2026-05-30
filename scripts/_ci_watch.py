#!/usr/bin/env python3
"""Internal helper: poll GitHub CI check runs for a PR until all settle.

Launched as a detached background process by post_pr_create_ci_monitor.py.
All output is written to a log file via stdout redirection.

Usage:
    python3 scripts/_ci_watch.py --pr <PR-URL-or-number> [--repo owner/repo]

GH_TOKEN environment variable must be set.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _github_api import apply_call

_POLL_INTERVAL = 15.0
_MAX_POLLS = 40  # ~10 minutes total
_PR_URL_RE = re.compile(r"https://github\.com/([^/\s]+)/([^/\s]+)/pull/(\d+)")
_FAIL_CONCLUSIONS: frozenset[str] = frozenset(
    {"failure", "failed", "cancelled", "canceled", "timed_out", "action_required"}
)


def _rest_get(url: str, *, token: str) -> tuple[int, Any]:
    """Return (status_code, parsed_json_or_None)."""
    try:
        code, body = apply_call(method="GET", url=url, payload=None, token=token)
    except Exception:
        return 0, None
    try:
        return code, json.loads(body)
    except json.JSONDecodeError:
        return code, None


def poll_ci(owner: str, repo: str, pr_number: str, *, token: str) -> int:
    print(f"CI watch: {owner}/{repo}#{pr_number}", flush=True)

    # Resolve head SHA from PR
    code, pr_data = _rest_get(
        f"https://api.github.com/repos/{owner}/{repo}/pulls/{pr_number}",
        token=token,
    )
    if not isinstance(pr_data, dict) or not (200 <= code < 300):
        print(f"error: HTTP {code} fetching PR {owner}/{repo}#{pr_number}", flush=True)
        return 1

    sha = (pr_data.get("head") or {}).get("sha")
    if not isinstance(sha, str):
        print("error: no head SHA in PR response", flush=True)
        return 1

    print(f"head SHA: {sha[:8]}", flush=True)

    for poll in range(_MAX_POLLS):
        if poll > 0:
            time.sleep(_POLL_INTERVAL)

        code, data = _rest_get(
            f"https://api.github.com/repos/{owner}/{repo}/commits/{sha}/check-runs?per_page=100",
            token=token,
        )
        if not isinstance(data, dict) or not (200 <= code < 300):
            print(f"poll {poll + 1}: HTTP {code}", flush=True)
            continue

        runs = data.get("check_runs") or []
        total = len(runs)
        completed = sum(1 for r in runs if r.get("status") == "completed")
        failed = [r for r in runs if str(r.get("conclusion") or "").lower() in _FAIL_CONCLUSIONS]

        print(f"poll {poll + 1}: {completed}/{total} checks complete, {len(failed)} failed", flush=True)
        for r in failed:
            print(f"  FAILED: {r.get('name')} ({r.get('conclusion')})", flush=True)

        if total > 0 and completed == total:
            if failed:
                print(f"CI FAILED: {len(failed)} check(s) failed", flush=True)
            else:
                print("CI PASSED: all checks passed", flush=True)
            return 0

    print(
        f"CI WATCH TIMEOUT: checks not settled after {_MAX_POLLS} polls "
        f"({_MAX_POLLS * _POLL_INTERVAL:.0f}s)",
        flush=True,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Poll GitHub CI check runs for a PR.")
    parser.add_argument("--pr", required=True, help="PR URL or number")
    parser.add_argument("--repo", default="", help="owner/repo (required when --pr is a number)")
    args = parser.parse_args(argv)

    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("error: GH_TOKEN not set", file=sys.stderr, flush=True)
        return 1

    pr_str = args.pr
    m = _PR_URL_RE.match(pr_str)
    if m:
        owner, repo, pr_number = m.group(1), m.group(2), m.group(3)
    else:
        if not args.repo or "/" not in args.repo:
            print(
                f"error: --repo owner/repo required when --pr is a number (got: {pr_str!r})",
                file=sys.stderr,
                flush=True,
            )
            return 1
        parts = args.repo.split("/", 1)
        owner, repo, pr_number = parts[0], parts[1], pr_str

    return poll_ci(owner, repo, pr_number, token=token)


if __name__ == "__main__":
    raise SystemExit(main())
