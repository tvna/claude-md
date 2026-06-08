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
import base64
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from _github_api import apply_call as _github_apply_call
from _github_api import graphql_call as _github_graphql_call

_API_ROOT = "https://api.github.com"

# Commits authored through this mutation are signed by GitHub and shown as
# Verified, with the authenticated token's identity (the App bot) as author.
# This is the only way to produce a verified commit for an App-bot author: a
# GitHub App account cannot hold its own GPG/SSH signing key, so a local
# ``git commit`` on the runner is always unsigned and rejected by the
# ``required_signatures`` rule on ``main``. Refs #1437.
_CREATE_COMMIT_ON_BRANCH_MUTATION = """
mutation($input: CreateCommitOnBranchInput!) {
  createCommitOnBranch(input: $input) {
    commit { oid }
  }
}
"""


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


def _get_ref_sha(
    *,
    repo: str,
    ref: str,
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> str:
    """Return the commit sha that ``refs/{ref}`` points at (e.g. ``ref='heads/main'``)."""
    url = f"{_API_ROOT}/repos/{repo}/git/ref/{ref}"
    code, body = apply_call(method="GET", url=url, payload=None, token=token)
    if not (200 <= code < 300):
        raise RuntimeError(f"Get ref {ref} failed: HTTP {code}: {body[:200]}")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Unexpected response from get ref {ref}: {body[:200]}") from exc
    sha = data.get("object", {}).get("sha") if isinstance(data, dict) else None
    if not isinstance(sha, str) or not sha:
        raise RuntimeError(f"Get ref {ref} response missing object.sha: {body[:200]}")
    return sha


def _create_branch_ref(
    *,
    repo: str,
    branch: str,
    sha: str,
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> None:
    """Create ``refs/heads/{branch}`` pointing at *sha*."""
    url = f"{_API_ROOT}/repos/{repo}/git/refs"
    payload = {"ref": f"refs/heads/{branch}", "sha": sha}
    code, resp = apply_call(method="POST", url=url, payload=payload, token=token)
    if not (200 <= code < 300):
        raise RuntimeError(f"Create branch ref {branch} failed: HTTP {code}: {resp[:200]}")


def _create_commit_on_branch(
    *,
    repo: str,
    branch: str,
    expected_head_oid: str,
    headline: str,
    body: str,
    additions: list[dict[str, str]],
    token: str,
    graphql_call: Callable[..., tuple[int, dict[str, Any]]] = _github_graphql_call,
) -> str:
    """Create a signed commit on *branch* via GraphQL; return the new commit oid.

    *additions* is a list of ``{"path", "contents"}`` where ``contents`` is the
    base64-encoded file bytes. *expected_head_oid* must equal the current head of
    *branch* or GitHub rejects the mutation (guarding against a racing write).
    See ``_CREATE_COMMIT_ON_BRANCH_MUTATION`` for why this path is required for a
    verified App-bot commit. Refs #1437.
    """
    message: dict[str, str] = {"headline": headline}
    if body:
        message["body"] = body
    variables = {
        "input": {
            "branch": {"repositoryNameWithOwner": repo, "branchName": branch},
            "message": message,
            "expectedHeadOid": expected_head_oid,
            "fileChanges": {"additions": additions},
        }
    }
    code, response = graphql_call(query=_CREATE_COMMIT_ON_BRANCH_MUTATION, variables=variables, token=token)
    if not (200 <= code < 300):
        raise RuntimeError(f"createCommitOnBranch HTTP {code}")
    if "errors" in response:
        raise RuntimeError(f"createCommitOnBranch errors: {response['errors']}")
    try:
        oid = response["data"]["createCommitOnBranch"]["commit"]["oid"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(f"createCommitOnBranch: unexpected response: {str(response)[:200]}") from exc
    if not isinstance(oid, str) or not oid:
        raise RuntimeError(f"createCommitOnBranch: missing commit oid: {str(response)[:200]}")
    return oid


def _get_branch_head_oid(
    *,
    repo: str,
    branch: str,
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> str | None:
    """Return the head commit oid of ``refs/heads/{branch}``, or ``None`` if absent.

    A 404 means the branch does not exist yet -- the first run, or a prior run's
    branch that was merged and deleted -- so the caller creates it off the base
    instead. Any other non-2xx is a real error and raises.
    """
    url = f"{_API_ROOT}/repos/{repo}/git/ref/heads/{branch}"
    code, body = apply_call(method="GET", url=url, payload=None, token=token)
    if code == 404:
        return None
    if not (200 <= code < 300):
        raise RuntimeError(f"Get branch ref {branch} failed: HTTP {code}: {body[:200]}")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Unexpected response from get branch ref {branch}: {body[:200]}") from exc
    sha = data.get("object", {}).get("sha") if isinstance(data, dict) else None
    if not isinstance(sha, str) or not sha:
        raise RuntimeError(f"Get branch ref {branch} response missing object.sha: {body[:200]}")
    return sha


def _get_file_bytes(
    *,
    repo: str,
    path: str,
    ref: str,
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> bytes | None:
    """Return the decoded bytes of *path* at *ref*, or ``None`` when absent there.

    Uses the contents API, which returns the file base64-encoded. A 404 means the
    path does not exist at *ref* (the snapshot has never been committed, or the
    branch is absent). A non-base64 encoding -- the API returns ``encoding: "none"``
    for blobs over 1 MB -- raises, so a silently truncated body can never
    masquerade as matching content. Any other non-2xx is a real error and raises.
    """
    url = f"{_API_ROOT}/repos/{repo}/contents/{path}?ref={ref}"
    code, body = apply_call(method="GET", url=url, payload=None, token=token)
    if code == 404:
        return None
    if not (200 <= code < 300):
        raise RuntimeError(f"Get contents {path}@{ref} failed: HTTP {code}: {body[:200]}")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Unexpected response from get contents {path}@{ref}: {body[:200]}") from exc
    if not isinstance(data, dict):
        raise RuntimeError(f"Expected object from get contents {path}@{ref}: {body[:200]}")
    encoding = data.get("encoding")
    content = data.get("content")
    if encoding != "base64" or not isinstance(content, str):
        raise RuntimeError(f"Get contents {path}@{ref}: unexpected encoding {encoding!r}")
    return base64.b64decode(content)


def upsert_single_file_pr(
    *,
    repo: str,
    path: str,
    content: bytes,
    base: str,
    branch: str,
    title: str,
    body: str,
    commit_subject: str,
    commit_body: str,
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
    graphql_call: Callable[..., tuple[int, dict[str, Any]]] = _github_graphql_call,
) -> str:
    """Publish *content* to *path* on *branch* and upsert a PR into *base*, never force-pushing.

    Replaces the ``git checkout -B`` + ``git push --force-with-lease`` pattern that
    the all-branches ``non_fast_forward`` ruleset rejects once the fixed *branch*
    already exists (the #1466 reused-branch failure). The commit is created server
    side via GraphQL ``createCommitOnBranch`` (Refs #1437), which is signed/Verified
    and, by construction, a fast-forward append:

    * When *path* on *base* already equals *content*, there is no drift to publish;
      returns ``"up-to-date"`` without touching the branch or any PR.
    * When *branch* is absent, it is created off *base* and the commit is added on
      top -- a plain create, no force.
    * When *branch* already exists, the commit is appended onto its current tip
      (``expectedHeadOid`` = the branch head), so the ``non_fast_forward`` rule is
      satisfied. If the tip already carries *content*, no commit is made; the open
      PR (if any) is still reconciled.

    Returns ``"up-to-date"``, or ``"<verb>:<pr_number>"`` where *verb* is
    ``created`` (new branch), ``committed`` (appended onto an existing branch), or
    ``branch-current`` (branch tip already matched, PR reconciled only).
    """
    base_bytes = _get_file_bytes(repo=repo, path=path, ref=base, token=token, apply_call=apply_call)
    if base_bytes is not None and base_bytes == content:
        return "up-to-date"

    additions = [{"path": path, "contents": base64.b64encode(content).decode("ascii")}]
    head_oid = _get_branch_head_oid(repo=repo, branch=branch, token=token, apply_call=apply_call)
    if head_oid is None:
        base_sha = _get_ref_sha(repo=repo, ref=f"heads/{base}", token=token, apply_call=apply_call)
        _create_branch_ref(repo=repo, branch=branch, sha=base_sha, token=token, apply_call=apply_call)
        _create_commit_on_branch(
            repo=repo,
            branch=branch,
            expected_head_oid=base_sha,
            headline=commit_subject,
            body=commit_body,
            additions=additions,
            token=token,
            graphql_call=graphql_call,
        )
        verb = "created"
    else:
        branch_bytes = _get_file_bytes(repo=repo, path=path, ref=branch, token=token, apply_call=apply_call)
        if branch_bytes == content:
            verb = "branch-current"
        else:
            _create_commit_on_branch(
                repo=repo,
                branch=branch,
                expected_head_oid=head_oid,
                headline=commit_subject,
                body=commit_body,
                additions=additions,
                token=token,
                graphql_call=graphql_call,
            )
            verb = "committed"

    _, number = _upsert_pr(
        repo=repo, head=branch, base=base, title=title, body=body, token=token, apply_call=apply_call
    )
    return f"{verb}:{number}"


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
