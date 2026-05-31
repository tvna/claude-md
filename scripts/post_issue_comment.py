#!/usr/bin/env python3
"""Post a comment to a GitHub issue via the REST API.

Usage::

    python3 scripts/post_issue_comment.py create \\
        --issue-number NUMBER (--body TEXT | --body-file FILE)

Environment variables:
    GH_TOKEN  GitHub token with issues:write scope.
    REPO      Repository in ``owner/repo`` format.

Exit codes:
    0  Success.
    1  Missing env var, missing body, or API error.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Callable
from pathlib import Path

from _github_api import apply_call as _github_apply_call

_API_ROOT = "https://api.github.com"


def _post_comment(
    *,
    repo: str,
    issue_number: int,
    body: str,
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> None:
    """Post a new comment to a GitHub issue."""
    url = f"{_API_ROOT}/repos/{repo}/issues/{issue_number}/comments"
    code, resp = apply_call(method="POST", url=url, payload={"body": body}, token=token)
    if not (200 <= code < 300):
        raise RuntimeError(f"Post comment failed: HTTP {code}: {resp[:200]}")


def _cmd_create(args: argparse.Namespace) -> int:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("Error: GH_TOKEN environment variable is required", file=sys.stderr)
        return 1
    repo = os.environ.get("REPO", "")
    if not repo:
        print("Error: REPO environment variable is required", file=sys.stderr)
        return 1

    if args.body_file:
        body = Path(args.body_file).read_text(encoding="utf-8")
    elif args.body is not None:
        body = args.body
    else:
        print("Error: one of --body or --body-file is required", file=sys.stderr)
        return 1

    try:
        _post_comment(repo=repo, issue_number=int(args.issue_number), body=body, token=token)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Post a comment to a GitHub issue.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    create_p = sub.add_parser("create", help="Post a new comment to an issue")
    create_p.add_argument("--issue-number", required=True, dest="issue_number", help="Issue number")
    create_p.add_argument("--body", default=None, help="Comment body text")
    create_p.add_argument("--body-file", default=None, dest="body_file", help="Path to file containing comment body")

    args = parser.parse_args(argv)

    if args.cmd == "create":
        return _cmd_create(args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
