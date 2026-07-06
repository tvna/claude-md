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
from datetime import UTC, datetime
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

# A non-clean higher-priority bot PR holds the lower series only while it is
# still plausibly running its checks. The keeper's App token is scoped to
# ``contents`` + ``pull-requests`` only (see
# ``docs/prd/security-control-inventory.md``), so it cannot read the Checks API
# to tell "checks pending" from "checks failed" (both surface as
# ``mergeable_state == blocked``). The hold is therefore time-bounded instead:
# past this TTL a still-non-clean higher PR is treated as settled-and-stuck (a
# healthy PR's checks would have gone green well before now) and no longer holds
# the lower series, so a broken higher PR can never permanently starve a lower
# one (#2382). Each drift recreates the fixed bot branch as a brand-new PR, so
# ``created_at`` is the age of the current attempt: a healthy in-flight PR is
# always fresh and holds, while a genuinely stuck one ages out and releases.
_HIGHER_PRIORITY_HOLD_TTL_SECONDS = 45 * 60


def _pr_head_ref(pr: dict[str, Any]) -> str:
    """Return a PR object's head branch ref, or ``""`` when absent."""
    head = pr.get("head")
    return head.get("ref", "") if isinstance(head, dict) else ""


def _pr_created_at(pr: dict[str, Any]) -> datetime | None:
    """Return a PR object's ``created_at`` as an aware datetime, or None if absent/unparseable."""
    raw = pr.get("created_at")
    if not isinstance(raw, str) or not raw:
        return None
    try:
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None


def _higher_pr_still_holds(pr: dict[str, Any], now: datetime) -> bool:
    """Return True if non-clean higher-priority *pr* should still hold the lower series.

    True while the PR is fresh (created within
    :data:`_HIGHER_PRIORITY_HOLD_TTL_SECONDS`); False once it has aged past the
    TTL, so a stuck higher PR eventually releases the lower series instead of
    blocking it forever (#2382). A PR with a missing or unparseable ``created_at``
    is treated as aged-out (release), the fail-safe that can never permanently
    block a lower PR on bad data.
    """
    created = _pr_created_at(pr)
    if created is None:
        return False
    return (now - created).total_seconds() < _HIGHER_PRIORITY_HOLD_TTL_SECONDS


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


def merge_bot_prs_in_priority_order(
    *,
    prs: list[dict[str, Any]],
    repo: str,
    token: str,
    now: datetime | None = None,
    sleeper: Callable[[float], None] = time.sleep,
    apply_call: Callable[..., tuple[int, str]] = _github_apply_call,
) -> int:
    """Merge clean bot PRs in priority order, holding a lower-priority series
    while a higher-priority one is still in flight. Returns the number merged.

    Rule (Refs #2382): the fixed bot branches carry a merge priority
    (:data:`_BOT_PR_PRIORITY_BRANCHES`). PRs are considered from highest to
    lowest priority; a PR is *held* (skipped, left for the next trigger) when a
    strictly-higher-priority bot PR is open, not yet ``clean``, and still fresh
    (created within :data:`_HIGHER_PRIORITY_HOLD_TTL_SECONDS`). A higher PR that
    is ``clean`` merges first; one that has been non-clean past the TTL is
    treated as stuck and no longer holds the lower series, so a broken higher PR
    can never permanently block a lower one. This stops the bot series from
    re-staling one another under ``strict_required_status_checks_policy``:
    merging a lower-priority PR would advance ``main`` and trigger the
    ``--recreate`` that auto-closes the still-pending higher PR before it lands.

    The token is scoped to ``contents`` + ``pull-requests`` only, so the hold
    decision uses just the already-polled PR object (``mergeable_state`` and
    ``created_at``); it never calls the Checks API, which would need a
    ``checks: read`` scope the keeper does not hold.

    Only listed branches (rank < ``len(_BOT_PR_PRIORITY_BRANCHES)``) can hold a
    lower series; unlisted bot PRs share the lowest rank and merge under the
    pre-existing per-PR ``clean`` rule, so a repository with no drift in the
    listed series behaves exactly as before.
    """
    now = now if now is not None else datetime.now(UTC)
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
        # A non-clean, listed (higher-priority) PR holds the lower series while it
        # is still fresh; once it ages past the hold TTL it is treated as stuck
        # and releases the hold so it cannot permanently block a lower PR.
        if rank < len(_BOT_PR_PRIORITY_BRANCHES) and blocking_rank is None:
            if _higher_pr_still_holds(polled, now):
                blocking_rank = rank
            else:
                print(
                    f"PR #{number} ({head_ref or 'unknown branch'}) has been non-clean past "
                    "the hold TTL; releasing lower-priority bot PRs to merge"
                )
    return merged
