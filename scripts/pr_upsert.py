#!/usr/bin/env python3
"""Create, update, or find pull requests via the GitHub REST API.

Usage::

    python3 scripts/pr_upsert.py upsert \\
        --head BRANCH --base BASE --title TITLE --body-file FILE

    python3 scripts/pr_upsert.py find --head BRANCH

``upsert`` prints the PR number to stdout (one integer, no decoration).
``find`` prints the PR number to stdout if an open PR exists for the head
branch, or nothing if none is found.

Environment variables:
    GH_TOKEN  GitHub token with pull-requests:write scope.
    REPO      Repository in ``owner/repo`` format.

Exit codes:
    0  Success.
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
from urllib.parse import quote

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


def _list_open_prs_by_prefix(
    *,
    repo: str,
    prefix: str,
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> list[dict[str, Any]]:
    """Return open PRs whose head branch name starts with *prefix* (paginated)."""
    results: list[dict[str, Any]] = []
    for page in range(1, 11):  # bound the scan; pin PRs are few
        url = f"{_API_ROOT}/repos/{repo}/pulls?state=open&per_page=100&page={page}"
        code, body = apply_call(method="GET", url=url, payload=None, token=token)
        if not (200 <= code < 300):
            raise RuntimeError(f"List PRs failed: HTTP {code}: {body[:200]}")
        try:
            data = json.loads(body)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Unexpected response from list PRs: {body[:200]}") from exc
        if not isinstance(data, list):
            raise RuntimeError(f"Expected list from list PRs, got: {body[:200]}")
        for pr in data:
            ref = pr.get("head", {}).get("ref", "") if isinstance(pr, dict) else ""
            if isinstance(ref, str) and ref.startswith(prefix):
                results.append(pr)
        if len(data) < 100:
            break
    return results


def _compare_behind(
    *,
    repo: str,
    base: str,
    head: str,
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> int:
    """Return how many commits *head* is behind *base* (``behind_by`` from compare)."""
    url = f"{_API_ROOT}/repos/{repo}/compare/{base}...{head}"
    code, body = apply_call(method="GET", url=url, payload=None, token=token)
    if not (200 <= code < 300):
        raise RuntimeError(f"Compare {base}...{head} failed: HTTP {code}: {body[:200]}")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Unexpected response from compare: {body[:200]}") from exc
    behind = data.get("behind_by") if isinstance(data, dict) else None
    if not isinstance(behind, int):
        raise RuntimeError(f"Compare response missing behind_by: {body[:200]}")
    return behind


def _get_pr(
    *,
    repo: str,
    number: int,
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> dict[str, Any]:
    """Return the full PR object for *number* (includes ``mergeable``/``mergeable_state``)."""
    url = f"{_API_ROOT}/repos/{repo}/pulls/{number}"
    code, body = apply_call(method="GET", url=url, payload=None, token=token)
    if not (200 <= code < 300):
        raise RuntimeError(f"Get PR #{number} failed: HTTP {code}: {body[:200]}")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Unexpected response from get PR: {body[:200]}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected object from get PR, got: {body[:200]}")
    return data


def _get_user_id(
    *,
    login: str,
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> int:
    """Return the numeric account id for *login*.

    Used to build a GitHub App bot's canonical noreply commit email
    (``<id>+<slug>[bot]@users.noreply.github.com``). ``login`` is URL-encoded so
    a bot login such as ``my-app[bot]`` (with ``[``/``]``) is requested safely.
    """
    url = f"{_API_ROOT}/users/{quote(login)}"
    code, body = apply_call(method="GET", url=url, payload=None, token=token)
    if not (200 <= code < 300):
        raise RuntimeError(f"Get user {login} failed: HTTP {code}: {body[:200]}")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Unexpected response from get user {login}: {body[:200]}") from exc
    uid = data.get("id") if isinstance(data, dict) else None
    if not isinstance(uid, int):
        raise RuntimeError(f"Get user {login} response missing integer id: {body[:200]}")
    return uid


def _merge_pr(
    *,
    repo: str,
    number: int,
    sha: str,
    merge_method: str,
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> bool:
    """Merge a PR via the REST merge API, pinning the head *sha*.

    Returns ``True`` when the merge succeeded. Returns ``False`` for the two
    expected "not mergeable right now" races, which the caller retries on the
    next keeper trigger instead of failing the run:

    - ``405 Method Not Allowed`` -- base-branch protection is not yet satisfied
      (a required check still pending, the branch is behind, etc.).
    - ``409 Conflict`` -- the provided *sha* no longer matches the PR head (a
      newer commit landed); pinning the sha guarantees we never merge a stale
      tree.

    Any other non-2xx response is a real error and raises ``RuntimeError``.
    """
    url = f"{_API_ROOT}/repos/{repo}/pulls/{number}/merge"
    payload = {"merge_method": merge_method, "sha": sha}
    code, resp = apply_call(method="PUT", url=url, payload=payload, token=token)
    if 200 <= code < 300:
        return True
    if code in (405, 409):
        return False
    raise RuntimeError(f"Merge PR #{number} failed: HTTP {code}: {resp[:200]}")


def _close_pr(
    *,
    repo: str,
    number: int,
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> None:
    """Close an open PR without merging it."""
    url = f"{_API_ROOT}/repos/{repo}/pulls/{number}"
    code, resp = apply_call(method="PATCH", url=url, payload={"state": "closed"}, token=token)
    if not (200 <= code < 300):
        raise RuntimeError(f"Close PR #{number} failed: HTTP {code}: {resp[:200]}")


def _delete_branch(
    *,
    repo: str,
    branch: str,
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> None:
    """Delete a remote branch ref. A 404/422 (already gone) is treated as success."""
    url = f"{_API_ROOT}/repos/{repo}/git/refs/heads/{branch}"
    code, resp = apply_call(method="DELETE", url=url, payload=None, token=token)
    if (200 <= code < 300) or code in (404, 422):
        return
    raise RuntimeError(f"Delete branch {branch} failed: HTTP {code}: {resp[:200]}")


def _comment_pr(
    *,
    repo: str,
    number: int,
    body: str,
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> None:
    """Post an issue comment on a PR."""
    url = f"{_API_ROOT}/repos/{repo}/issues/{number}/comments"
    code, resp = apply_call(method="POST", url=url, payload={"body": body}, token=token)
    if not (200 <= code < 300):
        raise RuntimeError(f"Comment on #{number} failed: HTTP {code}: {resp[:200]}")


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
    print(f"PR #{number} {action}.", file=sys.stderr)
    print(number)
    return 0


def _cmd_find(args: argparse.Namespace) -> int:
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("Error: GH_TOKEN environment variable is required", file=sys.stderr)
        return 1
    repo = os.environ.get("REPO", "")
    if not repo:
        print("Error: REPO environment variable is required", file=sys.stderr)
        return 1
    try:
        prs = _list_open_prs(repo=repo, head=args.head, token=token)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if prs:
        print(prs[0]["number"])
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create, update, or find a pull request.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    upsert_p = sub.add_parser("upsert", help="Create or update a PR for a branch")
    upsert_p.add_argument("--head", required=True, help="Head branch name")
    upsert_p.add_argument("--base", required=True, help="Base branch to merge into")
    upsert_p.add_argument("--title", required=True, help="PR title")
    upsert_p.add_argument("--body-file", required=True, dest="body_file", help="Path to file containing PR body")

    find_p = sub.add_parser("find", help="Print the open PR number for a head branch, or nothing if not found")
    find_p.add_argument("--head", required=True, help="Head branch name")

    args = parser.parse_args(argv)

    if args.cmd == "upsert":
        return _cmd_upsert(args)
    if args.cmd == "find":
        return _cmd_find(args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
