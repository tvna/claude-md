#!/usr/bin/env python3
"""Base-currency guard for ``pr_upsert.py upsert-files``.

``upsert-files`` commits the whole local working-tree file onto the real remote
base via ``createCommitOnBranch``. When the local checkout's base for a path is
stale or behind the real base, lines the operator never edited ship as an
unintended revert (the #2311 ``ops:dependencies`` regression that tripped the
dependabot label-drift gate).

This module owns the check that blocks that: for each committed path it compares
the local git base blob sha (``git rev-parse <base>:<path>``) to the real remote
base blob sha (the contents API ``sha`` field, which is the git blob object
name), transferring no file body. It lives in a sibling module to keep
``pr_upsert.py`` within the script size budget, mirroring ``_pr_commit_batch.py``
(Refs #1437, #1578). Refs #2315.
"""

from __future__ import annotations

import json
from collections.abc import Callable

from _git import run_git
from _github_api import apply_call as _github_apply_call

_API_ROOT = "https://api.github.com"


def _get_file_blob_sha(
    *,
    repo: str,
    path: str,
    ref: str,
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> str | None:
    """Return the git blob sha of *path* at *ref* on the remote, or ``None`` when absent.

    The contents API's ``sha`` field is the git blob object name, so comparing it
    to the local ``git rev-parse <ref>:<path>`` blob sha detects a stale local base
    without transferring or decoding the file body. A 404 means the path is absent
    at *ref*; any other non-2xx is a real error and raises.
    """
    url = f"{_API_ROOT}/repos/{repo}/contents/{path}?ref={ref}"
    code, body = apply_call(method="GET", url=url, payload=None, token=token)
    if code == 404:
        return None
    if not (200 <= code < 300):
        raise RuntimeError(f"Get contents sha {path}@{ref} failed: HTTP {code}: {body[:200]}")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Unexpected response from get contents sha {path}@{ref}: {body[:200]}") from exc
    sha = data.get("sha") if isinstance(data, dict) else None
    if not isinstance(sha, str) or not sha:
        raise RuntimeError(f"Get contents sha {path}@{ref} response missing sha: {body[:200]}")
    return sha


def _git_base_resolvable(base: str) -> bool:
    """Return True when *base* resolves to a commit in the local checkout.

    A CI job that checked out a shallow tree or a non-base ref will not have
    *base* locally; the base-currency check then cannot compare local to remote,
    so the caller skips it rather than block a legitimate commit (no false
    positive for the automated library callers).
    """
    return run_git(["rev-parse", "--verify", "--quiet", base]).returncode == 0


def _git_blob_sha(base: str, path: str) -> str | None:
    """Return the local git blob sha of *path* at *base*, or ``None`` when absent.

    ``git rev-parse <base>:<path>`` prints the blob object name; a non-zero exit
    means the path is absent in the local base tree.
    """
    result = run_git(["rev-parse", f"{base}:{path}"])
    if result.returncode != 0:
        return None
    return result.stdout.strip() or None


def verify_base_currency(
    *,
    repo: str,
    base: str,
    additions: list[tuple[str, bytes]],
    deletions: list[str],
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
    base_resolvable: Callable[[str], bool] = _git_base_resolvable,
    local_blob_sha: Callable[[str, str], str | None] = _git_blob_sha,
) -> None:
    """Raise ``RuntimeError`` when the local base is stale for any committed path.

    For each committed path (additions and deletions) this compares the local git
    base blob sha to the real remote base blob sha; any divergence means the local
    file was not built on top of the current base, so committing it would leak
    unintended reverts. When *base* is not resolvable locally the check is skipped,
    so a CI checkout that lacks the base ref never false-positives. Refs #2315.
    """
    if not base_resolvable(base):
        return
    stale: list[str] = []
    for path in [p for p, _ in additions] + deletions:
        remote_sha = _get_file_blob_sha(repo=repo, path=path, ref=base, token=token, apply_call=apply_call)
        if local_blob_sha(base, path) != remote_sha:
            stale.append(path)
    if stale:
        raise RuntimeError(
            "Local base is stale for: "
            + ", ".join(sorted(stale))
            + f". The local checkout's {base} for these paths differs from the real remote "
            + f"{base}, so committing the whole local file would leak unintended reverts. "
            + f"Rebuild each file on top of the real base (GET contents/<path>?ref={base}) and "
            + "re-verify the diff, or pass --allow-stale-base once you have confirmed the diff by hand."
        )
