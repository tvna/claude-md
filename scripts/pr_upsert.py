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

from _git import run_git
from _github_api import apply_call as _github_apply_call
from _github_api import graphql_call as _github_graphql_call

# Signed commit creation (createCommitOnBranch) and the payload batching that
# keeps a large backlog from overflowing the mutation live in a sibling module
# to keep this one within the script size budget. Refs #1437, #1578.
from _pr_commit_batch import _create_commits_in_batches

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


def upsert_files_pr(
    *,
    repo: str,
    additions: list[tuple[str, bytes]],
    deletions: list[str],
    base: str,
    branch: str,
    title: str,
    body: str,
    commit_subject: str,
    commit_body: str,
    token: str,
    recreate: bool = False,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
    graphql_call: Callable[..., tuple[int, dict[str, Any]]] = _github_graphql_call,
) -> str:
    """Publish a multi-file change to *branch* and upsert a PR into *base*, never force-pushing.

    A large addition set is split across several chained signed commits
    (:func:`_create_commits_in_batches`) so the createCommitOnBranch payload
    cannot overflow the GraphQL request; a small payload stays a single commit
    with the unchanged headline. Refs #1578.

    The signed, reuse-safe generalisation of :func:`upsert_single_file_pr`.
    *additions* is a list of ``(path, content_bytes)`` pairs to write; *deletions*
    is a list of paths to remove in the same commit. The commit is created server
    side via GraphQL ``createCommitOnBranch`` (Refs #1437), which is signed/Verified
    and, by construction, a fast-forward append -- the #1466 replacement for the
    ``git checkout -B`` + ``git push --force-with-lease`` pattern the all-branches
    ``non_fast_forward`` ruleset rejects once the fixed *branch* already exists:

    * When every addition already matches *base* and every deletion is already
      absent on *base* (no drift), returns ``"up-to-date"`` without touching the
      branch or any PR.
    * When *branch* is absent, it is created off *base* and the commit is added on
      top -- a plain create, no force.
    * When *branch* already exists, the commit is appended onto its current tip
      (``expectedHeadOid`` = the branch head). If the tip already carries the same
      additions/deletions, no commit is made; the open PR (if any) is reconciled.

    When *recreate* is true and there is drift, the existing *branch* ref is
    deleted first (``_delete_branch``) so the run always lands on the branch-absent
    path: a fresh branch off *base* carrying a single signed commit. A delete is
    not a force-push, so the all-branches ``non_fast_forward`` ruleset is still
    honored; unlike the append path it leaves no accumulated ancestry on the reused
    branch, which is what lets an unsigned legacy ancestor permanently violate the
    main ``required_signatures`` rule (Refs #1560). Default false preserves the
    append semantics for every other caller.

    Returns ``"up-to-date"``, or ``"<verb>:<pr_number>"`` where *verb* is
    ``created`` (new branch -- always the verb under *recreate*), ``committed``
    (appended onto an existing branch), or ``branch-current`` (branch tip already
    matched, PR reconciled only).
    """
    if not additions and not deletions:
        return "up-to-date"

    if not _ref_drifts(
        repo=repo, ref=base, additions=additions, deletions=deletions, token=token, apply_call=apply_call
    ):
        return "up-to-date"

    api_additions = [{"path": path, "contents": base64.b64encode(content).decode("ascii")} for path, content in additions]
    api_deletions = [{"path": path} for path in deletions]
    if recreate:
        # Drop the reused branch's accumulated ancestry so the commit lands on a
        # fresh branch off base (single signed commit, no legacy unsigned
        # ancestor). Delete is not a force-push -> non_fast_forward is honored.
        # Refs #1560.
        _delete_branch(repo=repo, branch=branch, token=token, apply_call=apply_call)
    head_oid = _get_branch_head_oid(repo=repo, branch=branch, token=token, apply_call=apply_call)
    if head_oid is None:
        base_sha = _get_ref_sha(repo=repo, ref=f"heads/{base}", token=token, apply_call=apply_call)
        _create_branch_ref(repo=repo, branch=branch, sha=base_sha, token=token, apply_call=apply_call)
        _create_commits_in_batches(
            repo=repo,
            branch=branch,
            start_oid=base_sha,
            headline=commit_subject,
            body=commit_body,
            additions=api_additions,
            deletions=api_deletions,
            token=token,
            graphql_call=graphql_call,
        )
        verb = "created"
    elif not _ref_drifts(
        repo=repo, ref=branch, additions=additions, deletions=deletions, token=token, apply_call=apply_call
    ):
        verb = "branch-current"
    else:
        _create_commits_in_batches(
            repo=repo,
            branch=branch,
            start_oid=head_oid,
            headline=commit_subject,
            body=commit_body,
            additions=api_additions,
            deletions=api_deletions,
            token=token,
            graphql_call=graphql_call,
        )
        verb = "committed"

    _, number = _upsert_pr(
        repo=repo, head=branch, base=base, title=title, body=body, token=token, apply_call=apply_call
    )
    return f"{verb}:{number}"


def _ref_drifts(
    *,
    repo: str,
    ref: str,
    additions: list[tuple[str, bytes]],
    deletions: list[str],
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> bool:
    """Return True when *ref* does not already carry the requested additions/deletions.

    Drift exists when any addition path's content at *ref* differs from the desired
    bytes (including the path being absent), or any deletion path is still present
    at *ref*. Returns False only when *ref* already matches the full desired state,
    which lets the caller skip a redundant commit. Stops at the first divergence.
    """
    for path, content in additions:
        if _get_file_bytes(repo=repo, path=path, ref=ref, token=token, apply_call=apply_call) != content:
            return True
    for path in deletions:
        if _get_file_bytes(repo=repo, path=path, ref=ref, token=token, apply_call=apply_call) is not None:
            return True
    return False


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
    recreate: bool = False,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
    graphql_call: Callable[..., tuple[int, dict[str, Any]]] = _github_graphql_call,
) -> str:
    """Publish *content* to *path* on *branch* and upsert a PR into *base*, never force-pushing.

    Thin single-file wrapper over :func:`upsert_files_pr`; see that function for the
    reuse-safe (no force-push) semantics, the *recreate* delete+create option, and
    the ``"<verb>:<pr_number>"`` return contract. Refs #1437, #1466, #1560.
    """
    return upsert_files_pr(
        repo=repo,
        additions=[(path, content)],
        deletions=[],
        base=base,
        branch=branch,
        title=title,
        body=body,
        commit_subject=commit_subject,
        commit_body=commit_body,
        token=token,
        recreate=recreate,
        apply_call=apply_call,
        graphql_call=graphql_call,
    )


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


def _collect_worktree_changes(
    *, adds: list[str], diff_prefixes: list[str]
) -> tuple[list[tuple[str, bytes]], list[str]]:
    """Resolve ``--add`` paths and ``--from-diff`` prefixes into (additions, deletions).

    *adds* are explicit paths whose current working-tree bytes become additions; a
    missing path raises, since an explicit add of an absent file is a mistake. For
    each prefix in *diff_prefixes*, ``git status --porcelain -- <prefix>`` lists the
    changed paths under it: a path that still exists in the working tree is read as
    an addition, one that no longer exists is a deletion. Paths are de-duped, with
    explicit adds winning. Assumes ASCII paths without spaces (the repository's
    generated-doc tree), matching git's unquoted porcelain output for such names.
    """
    additions: dict[str, bytes] = {}
    deletions: set[str] = set()
    for path in adds:
        p = Path(path)
        if not p.is_file():
            raise RuntimeError(f"--add path is not a readable file: {path}")
        additions[path] = p.read_bytes()
    for prefix in diff_prefixes:
        result = run_git(["status", "--porcelain", "--", prefix])
        if result.returncode != 0:
            raise RuntimeError(f"git status failed for {prefix!r}: {result.stderr.strip()}")
        for line in result.stdout.splitlines():
            if not line.strip():
                continue
            # Porcelain v1 lines are "XY <path>"; renamed entries are "old -> new",
            # whose live path is the new one on the right.
            path = line[3:].split(" -> ", 1)[-1].strip()
            if path in additions:
                continue
            candidate = Path(path)
            if candidate.is_file():
                additions[path] = candidate.read_bytes()
                deletions.discard(path)
            else:
                deletions.add(path)
    return list(additions.items()), sorted(deletions)


def _cmd_upsert_files(args: argparse.Namespace) -> int:
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
        additions, deletions = _collect_worktree_changes(adds=args.add, diff_prefixes=args.from_diff)
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    if not additions and not deletions:
        print("No file changes to publish; skipping PR upsert.", file=sys.stderr)
        return 0
    try:
        result = upsert_files_pr(
            repo=repo,
            additions=additions,
            deletions=deletions,
            base=args.base,
            branch=args.head,
            title=args.title,
            body=body,
            commit_subject=args.commit_subject or args.title,
            commit_body=args.commit_body,
            token=token,
            recreate=args.recreate,
        )
    except RuntimeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    print(f"upsert-files: {result}", file=sys.stderr)
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

    files_p = sub.add_parser(
        "upsert-files",
        help="Commit working-tree files via a signed createCommitOnBranch and upsert a PR (no force-push)",
    )
    files_p.add_argument("--head", required=True, help="Head branch name")
    files_p.add_argument("--base", required=True, help="Base branch to merge into")
    files_p.add_argument("--title", required=True, help="PR title")
    files_p.add_argument("--body-file", required=True, dest="body_file", help="Path to file containing PR body")
    files_p.add_argument(
        "--commit-subject", dest="commit_subject", default="", help="Commit subject line (defaults to --title)"
    )
    files_p.add_argument("--commit-body", dest="commit_body", default="", help="Commit body/trailer line")
    files_p.add_argument(
        "--add", action="append", default=[], help="Explicit working-tree file to commit (repeatable)"
    )
    files_p.add_argument(
        "--from-diff",
        action="append",
        default=[],
        dest="from_diff",
        help="Path prefix; its git-status changes (add/modify/delete) are committed (repeatable)",
    )
    files_p.add_argument(
        "--recreate",
        action="store_true",
        help=(
            "On drift, delete the fixed head branch and recreate it off --base "
            "with a single signed commit instead of appending onto its tip. Use "
            "for a fixed bot branch that can fall far behind base (the "
            "createCommitOnBranch append then fails); mirrors the triage-report "
            "refresh path (Refs #1560)."
        ),
    )

    args = parser.parse_args(argv)

    if args.cmd == "upsert":
        return _cmd_upsert(args)
    if args.cmd == "find":
        return _cmd_find(args)
    if args.cmd == "upsert-files":
        return _cmd_upsert_files(args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
