#!/usr/bin/env python3
"""Create or update (upsert) a pull request via the GitHub REST API.

Usage::

    python3 scripts/pr_upsert.py upsert \\
        --head BRANCH --base BASE --title TITLE --body-file FILE

Environment variables:
    GH_TOKEN  GitHub token with pull-requests:write scope.
    REPO      Repository in ``owner/repo`` format.

Exit codes:
    0  Success (PR created or updated).
    1  Missing env var, missing body file, or API error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from _github_api import apply_call as _github_apply_call

_API_ROOT = "https://api.github.com"


def _list_open_prs(
    *,
    repo: str,
    head: str,
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> list[dict[str, Any]]:
    """Return open PRs whose head branch matches *head*."""
    owner = repo.split("/")[0]
    url = f"{_API_ROOT}/repos/{repo}/pulls?head={owner}:{head}&state=open&per_page=1"
    code, body = apply_call(method="GET", url=url, payload=None, token=token)
    if not (200 <= code < 300):
        raise RuntimeError(f"List PRs failed: HTTP {code}: {body[:200]}")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Unexpected response from list PRs: {body[:200]}") from exc
    if not isinstance(data, list):
        raise RuntimeError(f"Expected list from list PRs, got: {body[:200]}")
    return data


def _create_pr(
    *,
    repo: str,
    head: str,
    base: str,
    title: str,
    body: str,
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> int:
    """Create a new PR and return its number."""
    url = f"{_API_ROOT}/repos/{repo}/pulls"
    payload = {"title": title, "head": head, "base": base, "body": body}
    code, resp = apply_call(method="POST", url=url, payload=payload, token=token)
    if not (200 <= code < 300):
        raise RuntimeError(f"Create PR failed: HTTP {code}: {resp[:200]}")
    return int(json.loads(resp)["number"])


def _update_pr(
    *,
    repo: str,
    number: int,
    title: str,
    body: str,
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> None:
    """Update an existing PR's title and body."""
    url = f"{_API_ROOT}/repos/{repo}/pulls/{number}"
    payload = {"title": title, "body": body}
    code, resp = apply_call(method="PATCH", url=url, payload=payload, token=token)
    if not (200 <= code < 300):
        raise RuntimeError(f"Update PR failed: HTTP {code}: {resp[:200]}")


def _upsert_pr(
    *,
    repo: str,
    head: str,
    base: str,
    title: str,
    body: str,
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> tuple[str, int]:
    """Create or update a PR. Returns ``(action, pr_number)``."""
    prs = _list_open_prs(repo=repo, head=head, token=token, apply_call=apply_call)
    if prs:
        number = int(prs[0]["number"])
        _update_pr(repo=repo, number=number, title=title, body=body, token=token, apply_call=apply_call)
        return "updated", number
    number = _create_pr(repo=repo, head=head, base=base, title=title, body=body, token=token, apply_call=apply_call)
    return "created", number


def _cmd_upsert(args: argparse.Namespace) -> int:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("Error: GH_TOKEN environment variable is required", file=sys.stderr)
        return 1
    repo = os.environ.get("REPO", "")
    if not repo:
        print("Error: REPO environment variable is required", file=sys.stderr)
        return 1
    body_path = Path(args.body_file)
    if not body_path.exists():
        print(f"Error: body file not found: {args.body_file}", file=sys.stderr)
        return 1
    body = body_path.read_text(encoding="utf-8")
    try:
        action, number = _upsert_pr(
            repo=repo,
            head=args.head,
            base=args.base,
            title=args.title,
            body=body,
            token=token,
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"PR #{number} {action}.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create or update a pull request.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    upsert_p = sub.add_parser("upsert", help="Create or update a PR for a branch")
    upsert_p.add_argument("--head", required=True, help="Head branch name")
    upsert_p.add_argument("--base", required=True, help="Base branch to merge into")
    upsert_p.add_argument("--title", required=True, help="PR title")
    upsert_p.add_argument("--body-file", required=True, dest="body_file", help="Path to file containing PR body")

    args = parser.parse_args(argv)

    if args.cmd == "upsert":
        return _cmd_upsert(args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
