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

# Fixed head branches of the post-merge bot PR series, in merge-priority order
# (index 0 merges first). The keeper holds a lower-priority series while a
# higher-priority one is still in flight so the bot PRs stop re-staling one
# another: ``.github/rulesets/main.json`` sets
# ``strict_required_status_checks_policy: true``, so every merge to ``main`` puts
# all open PRs ``behind``, and the only legal refresh is a ``--recreate`` that
# churns the PR number. The ``docs(generated)`` series (150+ files, Mermaid
# verification) finishes its checks slightly later than the triage-report
# series, so without an ordering it loses every race and is auto-closed unmerged
# (#2382). These are the same branches the manual-edit gate exempts
# (``gate_generated_scripts_manual_edit.EXEMPT_BRANCHES``); a contract test pins
# the two together so the priority list cannot silently drift from the
# recognised set of bot branches.
_BOT_PR_PRIORITY_BRANCHES: tuple[str, ...] = (
    "chore/update-generated-docs",
    "chore/refresh-auto-retro-triage-report",
)

# Check-run conclusions that mean a required check will not turn green on its
# own. Any of these on a higher-priority PR's head releases the hold on the
# lower-priority series: a higher PR whose checks have already failed must never
# permanently block a lower one (#2382). A still-running check has
# ``conclusion == null`` and is ignored here, so it counts as "in flight".
_FAILED_CHECK_CONCLUSIONS = frozenset(
    {"failure", "timed_out", "cancelled", "action_required", "startup_failure"}
)


def _pr_head_ref(pr: dict[str, Any]) -> str:
    """Return a PR object's head branch ref, or ``""`` when absent."""
    head = pr.get("head")
    return head.get("ref", "") if isinstance(head, dict) else ""


def _priority_rank(head_ref: str) -> int:
    """Return the merge-priority rank of *head_ref* (lower merges first).

    Branches absent from :data:`_BOT_PR_PRIORITY_BRANCHES` share the single
    lowest rank, so they never hold one another and are held by any in-flight
    listed branch above them.
    """
    try:
        return _BOT_PR_PRIORITY_BRANCHES.index(head_ref)
    except ValueError:
        return len(_BOT_PR_PRIORITY_BRANCHES)


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


def _merge_clean_pr(
    *,
    repo: str,
    number: int,
    head_ref: str,
    pr: dict[str, Any],
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> bool:
    """Squash-merge an already-polled clean *pr*, then delete its head branch.

    Split from :func:`_merge_pr_if_clean` so the priority-aware keeper can reuse
    the PR object it already fetched instead of polling a second time. Squash is
    fixed so the keyless ``required_signatures`` invariant on ``main`` (see
    ``docs/standards/commit-signing.md``) is preserved. Returns True when merged;
    a lost merge race is a no-op left for the next trigger, and only a real API
    error raises.
    """
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
    return _merge_clean_pr(
        repo=repo, number=number, head_ref=head_ref, pr=pr, token=token, apply_call=apply_call
    )


def _head_checks_failed(
    *,
    repo: str,
    sha: str,
    token: str,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> bool:
    """Return True if any check run on *sha* has a terminal non-success conclusion.

    Distinguishes a higher-priority PR whose checks are still in flight (hold the
    lower-priority series) from one whose checks have already failed (release the
    hold; a failed higher PR must never permanently block a lower one, #2382). A
    still-running check has ``conclusion == null`` and does not count as failed,
    so an in-flight or freshly-recreated head (no completed failing run yet) is
    reported as not-failed and keeps the hold.
    """
    url = f"{_API_ROOT}/repos/{repo}/commits/{sha}/check-runs?per_page=100"
    code, body = apply_call(method="GET", url=url, payload=None, token=token)
    if not (200 <= code < 300):
        raise RuntimeError(f"List check-runs for {sha[:12]} failed: HTTP {code}: {body[:200]}")
    try:
        data = json.loads(body)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Unexpected response from check-runs: {body[:200]}") from exc
    runs = data.get("check_runs", []) if isinstance(data, dict) else []
    for run in runs:
        conclusion = str(run.get("conclusion") or "").lower() if isinstance(run, dict) else ""
        if conclusion in _FAILED_CHECK_CONCLUSIONS:
            return True
    return False


def merge_bot_prs_in_priority_order(
    *,
    prs: list[dict[str, Any]],
    repo: str,
    token: str,
    sleeper: Callable[[float], None] = time.sleep,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> int:
    """Merge clean bot PRs in priority order, holding a lower-priority series
    while a higher-priority one is still in flight. Returns the number merged.

    Rule (Refs #2382): the fixed bot branches carry a merge priority
    (:data:`_BOT_PR_PRIORITY_BRANCHES`). PRs are considered from highest to
    lowest priority; a PR is *held* (skipped, left for the next trigger) when a
    strictly-higher-priority bot PR is open and still in flight (not yet
    ``clean`` and with no check run already failed). A higher PR that is ``clean``
    merges first; one whose checks have failed does not hold the lower series, so
    a broken higher PR can never permanently block a lower one. This stops the
    bot series from re-staling one another under
    ``strict_required_status_checks_policy``: merging a lower-priority PR would
    advance ``main`` and trigger the ``--recreate`` that auto-closes the still
    -pending higher PR before it can land.

    Only listed branches (rank < ``len(_BOT_PR_PRIORITY_BRANCHES)``) can hold a
    lower series; unlisted bot PRs share the lowest rank and merge under the
    pre-existing per-PR ``clean`` rule, so a repository with no drift in the
    listed series behaves exactly as before.
    """
    ordered = sorted(
        enumerate(prs),
        key=lambda item: (_priority_rank(_pr_head_ref(item[1])), item[0]),
    )
    merged = 0
    blocking_rank: int | None = None
    for _idx, pr in ordered:
        number = int(pr["number"])
        head_ref = _pr_head_ref(pr)
        rank = _priority_rank(head_ref)
        if blocking_rank is not None and rank > blocking_rank:
            print(
                f"PR #{number} ({head_ref or 'unknown branch'}) held: a higher-priority "
                "bot PR is still in flight; leaving for the next trigger"
            )
            continue
        polled = _poll_pr_mergeability(
            repo=repo, number=number, token=token, sleeper=sleeper, apply_call=apply_call
        )
        state = str(polled.get("mergeable_state") or "unknown").lower()
        if state == "clean":
            if _merge_clean_pr(
                repo=repo, number=number, head_ref=head_ref, pr=polled, token=token, apply_call=apply_call
            ):
                merged += 1
            continue
        print(
            f"PR #{number} ({head_ref or 'unknown branch'}) not mergeable yet "
            f"(mergeable_state={state}); leaving for the next trigger"
        )
        # A non-clean, listed (higher-priority) PR holds the lower series while
        # its checks are still in flight; a failed check releases the hold.
        if rank < len(_BOT_PR_PRIORITY_BRANCHES) and blocking_rank is None:
            head_sha = polled.get("head", {}).get("sha", "") if isinstance(polled.get("head"), dict) else ""
            if head_sha and not _head_checks_failed(
                repo=repo, sha=head_sha, token=token, apply_call=apply_call
            ):
                blocking_rank = rank
    return merged
