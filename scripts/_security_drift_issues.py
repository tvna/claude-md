#!/usr/bin/env python3
"""Rolling per-family drift-issue reconcile IO (#1726).

Split out of ``scripts/security_drift_report.py`` to keep that module within its
maintainability size budget (``docs/standards/module-size-distribution.toml``),
mirroring the ``_security_drift_families.py`` split (#1488).

This module owns the GitHub-issue lifecycle that maintains exactly ONE rolling
issue per control family instead of flooding a fresh issue every run -- the root
cause of the #1432/#1507/#1653 pile-up. The HTTP boundary is injected as
``apply`` (``_github_api.apply_call`` in production), so tests stay offline.

``security_drift_report`` re-imports the public names, so ``sdr.render_family_issue_title``
etc. stay stable for callers and tests. Refs #180, parent #178, #1726.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
from collections.abc import Callable

import issue_anchors
from _security_drift_families import FAMILY_ISSUE_SPEC, ISSUE_LABELS, TARGET_FAMILIES

API_ROOT = "https://api.github.com"
# Anchor table (#1640): a renumbering is a one-file diff to the TOML.
DEFAULT_TRACKING_ISSUE = issue_anchors.resolve("security-tracking")

# Auto-close / dedup comments for the rolling per-family issue lifecycle (#1726).
# ASCII only: these are posted to GitHub.
RESOLVED_COMMENT = (
    "Resolved: the security-control-drift job observed no further drift for this "
    "control family, so this rolling issue is auto-closed. If the drift recurs, a "
    "fresh rolling issue is filed automatically."
)
DEDUP_COMMENT_TEMPLATE = (
    "Superseded: consolidating duplicate scheduled-drift issues for this control "
    "family into the single rolling issue #{keep}. Closing this duplicate so the "
    "family tracks one rolling issue that auto-closes on resolve."
)


# ---------------------------------------------------------------------------
# Pure renderers / matchers
# ---------------------------------------------------------------------------

def render_family_issue_title(family: str) -> str:
    """Stable, date-free rolling-issue title for a control family.

    The date is intentionally NOT in the title (it lives in the body) so a
    re-detected drift maps to the SAME open rolling issue instead of stacking a
    fresh one each run -- the root cause of the #1432/#1507/#1653 pile-up (#1726).
    """
    spec = FAMILY_ISSUE_SPEC[family]
    return f"fix({spec['scope']}): scheduled drift detected"


def render_family_issue_body(family: str, *, run_url: str, run_date: str) -> str:
    spec = FAMILY_ISSUE_SPEC[family]
    return (
        f"Parent: #{DEFAULT_TRACKING_ISSUE}\n"
        "\n"
        f"Scheduled drift detected for the `{family}` security control family by "
        "the weekly `security-control-drift` job in "
        "`.github/workflows/weekly-maintenance.yml`.\n"
        "\n"
        f"- Run: {run_url}\n"
        f"- Detected at: {run_date}\n"
        f"- Detector: `{spec['detector']}`\n"
        f"- Evidence: `{spec['evidence']}`\n"
        "\n"
        "## Remediation\n"
        "\n"
        f"{spec['remediation']}\n"
        "\n"
        "This is a single rolling issue: it is auto-closed once the drift clears "
        "and re-filed if it recurs (#1726). Auto-filed to meet the "
        "`detect-and-file` floor (`.github/security-control-floor.toml`, "
        "`docs/prd/security-control-inventory.md`). The cross-family status is "
        f"tracked in the rolling comment on #{DEFAULT_TRACKING_ISSUE}.\n"
    )


def is_family_issue_title(title: str, stable_title: str) -> bool:
    """Match a family's rolling issue, including legacy dated titles.

    The current scheme titles issues exactly ``stable_title``; issues filed
    before #1726 carry a `` (YYYY-MM-DD)`` suffix. Both forms are matched so the
    reconcile pass can consolidate the legacy duplicates into one rolling issue.
    """
    return title == stable_title or title.startswith(f"{stable_title} (")


# ---------------------------------------------------------------------------
# GitHub REST helpers (apply boundary injected)
# ---------------------------------------------------------------------------

def list_open_family_issues(
    apply: Callable[..., tuple[int, str]], repo: str, token: str
) -> list[tuple[int, str]] | None:
    """Return open ``(number, title)`` pairs labelled like the rolling issues.

    Filters on :data:`ISSUE_LABELS` so the set is small, and drops pull requests
    (the issues endpoint returns both). Returns ``None`` on a failed GET so the
    caller fails loud rather than reconciling against a partial view. A single
    100-item page is read; the open meta-fix issue set is far smaller in practice.
    """
    query = urllib.parse.urlencode(
        {"state": "open", "labels": ",".join(ISSUE_LABELS), "per_page": "100"}
    )
    code, response = apply(
        method="GET",
        url=f"{API_ROOT}/repos/{repo}/issues?{query}",
        payload=None,
        token=token,
    )
    if not 200 <= code < 300:
        print(
            f"::error::GET issues failed (HTTP {code}); body: {response[:200]}",
            file=sys.stderr,
        )
        return None
    try:
        entries = json.loads(response)
    except json.JSONDecodeError as exc:
        print(f"::error::Could not parse issues JSON: {exc}", file=sys.stderr)
        return None
    if not isinstance(entries, list):
        print("::error::Issues response was not a JSON array.", file=sys.stderr)
        return None

    result: list[tuple[int, str]] = []
    for entry in entries:
        if not isinstance(entry, dict) or "pull_request" in entry:
            continue
        number, title = entry.get("number"), entry.get("title")
        if isinstance(number, int) and isinstance(title, str):
            result.append((number, title))
    return result


def close_family_issue(
    apply: Callable[..., tuple[int, str]],
    repo: str,
    number: int,
    token: str,
    comment: str,
) -> bool:
    """Comment then close issue ``number``. Returns True on success."""
    code, response = apply(
        method="POST",
        url=f"{API_ROOT}/repos/{repo}/issues/{number}/comments",
        payload={"body": comment},
        token=token,
    )
    if not 200 <= code < 300:
        print(
            f"::error::POST close-comment on #{number} failed (HTTP {code}); "
            f"body: {response[:200]}",
            file=sys.stderr,
        )
        return False
    code, response = apply(
        method="PATCH",
        url=f"{API_ROOT}/repos/{repo}/issues/{number}",
        payload={"state": "closed", "state_reason": "completed"},
        token=token,
    )
    if not 200 <= code < 300:
        print(
            f"::error::PATCH close #{number} failed (HTTP {code}); "
            f"body: {response[:200]}",
            file=sys.stderr,
        )
        return False
    return True


def create_family_issue(
    apply: Callable[..., tuple[int, str]],
    repo: str,
    family: str,
    *,
    run_url: str,
    run_date: str,
    token: str,
) -> bool:
    """Create the rolling issue for ``family``. Returns True on success."""
    payload = {
        "title": render_family_issue_title(family),
        "body": render_family_issue_body(family, run_url=run_url, run_date=run_date),
        "labels": list(ISSUE_LABELS),
    }
    code, response = apply(
        method="POST",
        url=f"{API_ROOT}/repos/{repo}/issues",
        payload=payload,
        token=token,
    )
    if not 200 <= code < 300:
        print(
            f"::error::POST issue for {family} failed (HTTP {code}); "
            f"body: {response[:200]}",
            file=sys.stderr,
        )
        return False
    return True


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def reconcile_family_issues(
    *,
    apply: Callable[..., tuple[int, str]],
    repo: str,
    run_url: str,
    run_date: str,
    drifting: list[str],
    resolved: list[str],
    dry_run: bool,
) -> int:
    """Maintain ONE rolling issue per target family (create / dedupe / close).

    Each target family is reconciled by its observed status:

    - ``drifting`` + no open rolling issue   -> create one;
    - ``drifting`` + open rolling issue(s)   -> keep the oldest, close any extras
                                                (consolidates legacy duplicates);
    - ``resolved`` (EXPLICIT covered) + open  -> auto-close them;
    - ``resolved`` + none                     -> stay silent;
    - neither (detector error / unknown)      -> leave untouched, so a transient
                                                failure cannot auto-close and hide
                                                an active drift issue (#1730 review).

    Honours ``dry_run`` (no API calls). Returns a process exit code.
    """
    if dry_run:
        for family in TARGET_FAMILIES:
            if family in drifting:
                print(
                    f"[dry-run] {family}: drift -> ensure one open rolling issue "
                    f"{render_family_issue_title(family)!r} (create if absent, "
                    "dedupe extras)"
                )
            elif family in resolved:
                print(f"[dry-run] {family}: covered -> close any open rolling issue")
            else:
                print(
                    f"[dry-run] {family}: error/unknown -> leave any open rolling "
                    "issue untouched"
                )
        return 0

    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("::error::GH_TOKEN is not set.", file=sys.stderr)
        return 1

    open_issues = list_open_family_issues(apply, repo, token)
    if open_issues is None:
        return 1

    failed = False
    for family in TARGET_FAMILIES:
        stable = render_family_issue_title(family)
        matches = sorted(
            num for num, title in open_issues if is_family_issue_title(title, stable)
        )
        if family in drifting:
            failed |= not _ensure_single_open(
                apply, repo, family, matches, token,
                run_url=run_url, run_date=run_date,
            )
        elif family in resolved:
            failed |= not _close_all(apply, repo, family, matches, token)
        # else: detector error / unknown -- leave any open issue untouched.
    return 1 if failed else 0


def _ensure_single_open(
    apply: Callable[..., tuple[int, str]],
    repo: str,
    family: str,
    matches: list[int],
    token: str,
    *,
    run_url: str,
    run_date: str,
) -> bool:
    """Drifting family: keep the oldest open issue, dedupe extras, or create."""
    if not matches:
        if create_family_issue(
            apply, repo, family, run_url=run_url, run_date=run_date, token=token
        ):
            print(f"Filed rolling drift issue for {family} on {repo}.")
            return True
        return False
    keep, *extras = matches
    ok = True
    for dup in extras:
        ok &= close_family_issue(
            apply, repo, dup, token, DEDUP_COMMENT_TEMPLATE.format(keep=keep)
        )
    print(f"{family}: kept rolling issue #{keep} open; closed {len(extras)} duplicate(s).")
    return ok


def _close_all(
    apply: Callable[..., tuple[int, str]],
    repo: str,
    family: str,
    matches: list[int],
    token: str,
) -> bool:
    """Resolved family: auto-close every open rolling issue."""
    ok = True
    for num in matches:
        if close_family_issue(apply, repo, num, token, RESOLVED_COMMENT):
            print(f"{family}: auto-closed resolved drift issue #{num}.")
        else:
            ok = False
    return ok
