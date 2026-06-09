#!/usr/bin/env python3
"""Shared auto-merge keeper helpers for App-bot pull requests.

These build on the low-level REST primitives in ``pr_upsert`` to provide the
"merge this PR once it is clean" behaviour used by both the unified
``bot_pr_automerge.py`` keeper and the ``devcontainer_pin_pr.py refresh`` flow.
Squash is fixed throughout so the keyless ``required_signatures`` invariant on
``main`` (see ``docs/standards/commit-signing.md``) is preserved. Refs #1539.
"""

from __future__ import annotations

import json
import sys
import time
from collections.abc import Callable
from typing import Any

from _github_api import apply_call as _github_apply_call
from pr_upsert import _API_ROOT, _delete_branch, _get_pr, _merge_pr


def _list_open_prs_by_author(
    *,
    repo: str,
    author_login: str,
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> list[dict[str, Any]]:
    """Return open PRs whose author ``user.login`` equals *author_login* (paginated).

    The REST ``/pulls`` list endpoint has no author filter, so the scan reads up
    to ten pages of open PRs and filters client-side. Automated bot PRs are few,
    so this bound is never reached in practice.
    """
    results: list[dict[str, Any]] = []
    for page in range(1, 11):  # bound the scan; bot PRs are few
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
            login = pr.get("user", {}).get("login", "") if isinstance(pr, dict) else ""
            if login == author_login:
                results.append(pr)
        if len(data) < 100:
            break
    return results


# Mergeability is computed asynchronously by GitHub, so the ``mergeable`` field
# is null for a short window after a push or check completes. Poll a bounded
# number of times before giving up and leaving the merge for the next trigger.
_MERGE_POLL_ATTEMPTS = 6
_MERGE_POLL_INTERVAL_SECONDS = 5.0


def _poll_pr_mergeability(
    *,
    repo: str,
    number: int,
    token: str,
    sleeper: Callable[[float], None] = time.sleep,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> dict[str, Any]:
    """Return the PR object once GitHub has computed ``mergeable`` (or the last poll)."""
    pr: dict[str, Any] = {}
    for attempt in range(_MERGE_POLL_ATTEMPTS):
        if attempt:
            sleeper(_MERGE_POLL_INTERVAL_SECONDS)
        pr = _get_pr(repo=repo, number=number, token=token, apply_call=apply_call)
        if pr.get("mergeable") is not None:
            break
    return pr


def _merge_pr_if_clean(
    *,
    repo: str,
    number: int,
    head_ref: str,
    token: str,
    sleeper: Callable[[float], None] = time.sleep,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> bool:
    """Squash-merge PR *number* iff it is ``mergeable_state == clean``, then delete its branch.

    Squash is fixed so the keyless ``required_signatures`` invariant on ``main``
    (see ``docs/standards/commit-signing.md``) is preserved. Returns True when the
    PR was merged. A PR that is not yet clean (required checks pending, branch
    behind, conflicts) or that loses the merge race is a no-op left for the next
    trigger; only a real API error raises.
    """
    pr = _poll_pr_mergeability(repo=repo, number=number, token=token, sleeper=sleeper, apply_call=apply_call)
    state = str(pr.get("mergeable_state") or "unknown").lower()
    if state != "clean":
        print(f"PR #{number} not mergeable yet (mergeable_state={state}); leaving for the next trigger")
        return False
    head_sha = pr.get("head", {}).get("sha", "") if isinstance(pr.get("head"), dict) else ""
    if not head_sha:
        raise RuntimeError(f"PR #{number} is clean but has no head sha")
    if not _merge_pr(
        repo=repo, number=number, sha=head_sha, merge_method="squash", token=token, apply_call=apply_call
    ):
        print(f"PR #{number} was not mergeable at merge time; leaving for the next trigger")
        return False
    print(f"merged PR #{number}")
    if head_ref:
        try:
            _delete_branch(repo=repo, branch=head_ref, token=token, apply_call=apply_call)
        except RuntimeError as exc:
            print(f"::warning::merged PR #{number} but branch cleanup failed: {exc}", file=sys.stderr)
    return True
