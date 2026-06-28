#!/usr/bin/env python3
"""Signed commit creation for the bot-PR publisher, with payload batching.

The ``createCommitOnBranch`` GraphQL mutation is the repository's adopted path
for bot-authored, Verified commits (a GitHub App cannot hold its own signing
key, so a runner ``git commit`` is always unsigned; Refs #1437). This module
owns that mutation and the batching that keeps its single request from
overflowing: a large addition set; e.g. the full ``docs/generated/scripts/ast``
tree regenerated after the fixed branch fell far behind ``main``; is split
into several chained signed commits instead of one oversized mutation that
GitHub rejects with a generic "Something went wrong" error (Refs #1578).

Split out of ``pr_upsert.py`` to keep that module within the script size budget;
``pr_upsert`` re-imports these names, so callers and tests still reach them
through ``pr_upsert``.

Contract:
- :func:`_create_commit_on_branch` makes one signed commit and returns its oid.
- :func:`_batch_additions` splits additions by file count and cumulative size.
- :func:`_create_commits_in_batches` chains the two: one commit for a small
  payload (unchanged headline), several chained commits for a large one.
- Failure policy: fails loud per CLAUDE.md section 4; a non-2xx response, a
  GraphQL ``errors`` array, or a missing commit oid each raise ``RuntimeError``
  rather than returning a silent default.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from _github_api import graphql_call as _github_graphql_call

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

# createCommitOnBranch carries every addition's bytes (base64) in one GraphQL
# request. A large backlog; e.g. the full docs/generated/scripts/ast/ tree
# regenerated after the fixed branch fell far behind main; overflows the
# mutation and GitHub returns a generic "Something went wrong while executing
# your query" error. A manual decision-tree run reproduced it at 152 files /
# ~1.3 MB of base64 even with a fresh branch (so it is the payload, not the
# branch state). Split additions into batches bounded by both file count and
# cumulative base64 size, one signed commit each, chaining expectedHeadOid. The
# thresholds sit well below the ~1.3 MB that demonstrably failed; the exact
# GitHub limit is undocumented. Refs #1578.
_MAX_BATCH_FILES = 40
_MAX_BATCH_BASE64_BYTES = 256 * 1024


def _is_valid_commit_path(path: str) -> bool:
    """Return True when *path* is a concrete, relative file path.

    createCommitOnBranch accepts only individual file paths: a directory entry
    (trailing ``/``), an empty/absolute path, or an empty/``.``/``..`` segment
    is not a valid target. Refs #1784.
    """
    if not path or not path.strip() or path.endswith("/"):
        return False
    return all(segment not in ("", ".", "..") for segment in path.split("/"))


def _validate_commit_paths(
    additions: list[tuple[str, bytes]], deletions: list[str]
) -> None:
    """Fail loud at the API boundary on a malformed commit path.

    GitHub rejects a directory-level path with its generic "Something went
    wrong" error, which ``_github_api._graphql_is_transient`` retries three
    times before failing with a misleading "transient" label; the #1772 mode
    (a ``docs/generated/graph/`` directory used as a deletion target). Validating
    here turns that opaque retried failure into an immediate named error and
    guards every caller of the createCommitOnBranch path. Refs #1784, #1772.
    """
    bad = [f"addition {p!r}" for p, _ in additions if not _is_valid_commit_path(p)]
    bad += [f"deletion {p!r}" for p in deletions if not _is_valid_commit_path(p)]
    if bad:
        raise RuntimeError(
            "createCommitOnBranch requires concrete file paths; refusing "
            f"invalid entries: {', '.join(bad)}"
        )


def _create_commit_on_branch(
    *,
    repo: str,
    branch: str,
    expected_head_oid: str,
    headline: str,
    body: str,
    additions: list[dict[str, str]],
    deletions: list[dict[str, str]] | None = None,
    token: str,
    graphql_call: Callable[..., tuple[int, dict[str, Any]]] = _github_graphql_call,
) -> str:
    """Create a signed commit on *branch* via GraphQL; return the new commit oid.

    *additions* is a list of ``{"path", "contents"}`` where ``contents`` is the
    base64-encoded file bytes. *deletions* (when given) is a list of ``{"path"}``
    for files removed in the same commit; an empty/omitted list leaves the
    ``deletions`` key off the mutation entirely. *expected_head_oid* must equal
    the current head of *branch* or GitHub rejects the mutation (guarding against
    a racing write). See ``_CREATE_COMMIT_ON_BRANCH_MUTATION`` for why this path
    is required for a verified App-bot commit. Refs #1437.
    """
    message: dict[str, str] = {"headline": headline}
    if body:
        message["body"] = body
    file_changes: dict[str, list[dict[str, str]]] = {"additions": additions}
    if deletions:
        file_changes["deletions"] = deletions
    variables = {
        "input": {
            "branch": {"repositoryNameWithOwner": repo, "branchName": branch},
            "message": message,
            "expectedHeadOid": expected_head_oid,
            "fileChanges": file_changes,
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


def _batch_additions(
    additions: list[dict[str, str]],
    *,
    max_files: int = _MAX_BATCH_FILES,
    max_bytes: int = _MAX_BATCH_BASE64_BYTES,
) -> list[list[dict[str, str]]]:
    """Split createCommitOnBranch *additions* into size-bounded batches.

    *additions* is the mutation shape (``{"path", "contents"}`` with base64
    ``contents``). Each returned batch holds at most *max_files* entries and at
    most *max_bytes* of cumulative ``contents`` length, but always at least one
    entry, so a single oversized file still forms its own batch rather than an
    empty one. Order is preserved. An empty input yields an empty list.
    """
    batches: list[list[dict[str, str]]] = []
    current: list[dict[str, str]] = []
    size = 0
    for item in additions:
        item_size = len(item["contents"])
        if current and (len(current) >= max_files or size + item_size > max_bytes):
            batches.append(current)
            current = []
            size = 0
        current.append(item)
        size += item_size
    if current:
        batches.append(current)
    return batches


def _create_commits_in_batches(
    *,
    repo: str,
    branch: str,
    start_oid: str,
    headline: str,
    body: str,
    additions: list[dict[str, str]],
    deletions: list[dict[str, str]],
    token: str,
    graphql_call: Callable[..., tuple[int, dict[str, Any]]] = _github_graphql_call,
    max_files: int = _MAX_BATCH_FILES,
    max_bytes: int = _MAX_BATCH_BASE64_BYTES,
) -> str:
    """Publish *additions*/*deletions* onto *branch* as one or more signed commits.

    A payload that fits in a single batch is committed exactly as before: one
    :func:`_create_commit_on_branch` with the unmodified *headline*. A larger
    payload is split by :func:`_batch_additions`; the first commit carries the
    *deletions*, each batch is one signed commit, and ``expectedHeadOid`` is
    chained from *start_oid* through each returned oid so every commit is a
    fast-forward append (no force-push). The multi-commit case suffixes the
    headline ``(batch k/n)`` for traceability. Returns the final commit oid.
    Refs #1578.
    """
    batches = _batch_additions(additions, max_files=max_files, max_bytes=max_bytes) or [[]]
    total = len(batches)
    head_oid = start_oid
    for index, batch in enumerate(batches, start=1):
        commit_headline = headline if total == 1 else f"{headline} (batch {index}/{total})"
        head_oid = _create_commit_on_branch(
            repo=repo,
            branch=branch,
            expected_head_oid=head_oid,
            headline=commit_headline,
            body=body,
            additions=batch,
            deletions=deletions if index == 1 else None,
            token=token,
            graphql_call=graphql_call,
        )
    return head_oid
