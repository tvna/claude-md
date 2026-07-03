#!/usr/bin/env python3
"""Scan retro/follow-up linkage for drift and apply TP/FP candidate labels.

Invoked from ``.github/workflows/retro-followup-drift.yml`` as the single
``python3 scripts/scan_retro_followup_drift.py run`` entry point. The
workflow only marshals env vars; all logic lives here and is unit-tested
in ``tests/test_scan_retro_followup_drift.py``.

This is PR1 of the TP/FP retrofit that addresses retro-issue
non-convergence: ``scripts/auto_retro.py:compute_repair_signals`` uses
only single-PR local features, with no mid-to-long-term context. The
scanner closes the loop in the opposite direction; it watches the
follow-up issues/PRs the retro proposed and labels the retro when those
follow-ups drift (stale, abandoned, missing). Operators upgrade
``retro:fp-candidate`` to ``retro:fp`` (or relabel ``retro:tp``) at
close time; PR2/PR3 will then consume the labels as a prior for the
signal and classification layers.

Follows the refactor pattern established by ``scripts/scan_non_ascii.py``
and ``scripts/auto_retro.py``: pure functions on top, a thin
:func:`gh_api` REST boundary at the bottom, monkeypatched in tests.

Drift rules (deterministic, no body-text interpretation per
CLAUDE.md section 2; state, label, link-structure only):

* Follow-up issue closed with ``state_reason == "not_planned"`` -> ``fp_confirmed``.
* Follow-up PR closed unmerged (``state == "closed"`` and ``merged is False``)
  -> ``fp_confirmed``.
* Follow-up referenced ``#N`` returns 404 -> ``fp_candidate`` via the
  ``not_found`` per-followup result.
* Follow-up open and ``updated_at`` is ``stale_days`` (default 30) or
  more days stale -> ``fp_candidate``.
* All other cases -> ``ok`` (no label change).

Idempotency:

* Skip retros that already carry ``retro:tp`` or ``retro:fp``
  (operator-confirmed; the scanner must not overwrite operator state).
* Skip relabelling when ``retro:fp-candidate`` is already present for a
  candidate-level drift result.
* Upgrade ``retro:fp-candidate`` to ``retro:fp`` when the drift result
  is ``fp_confirmed``.

Refs #558.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import _ssot
from _github_api import GitHubApiError, rest_text
from _retro_labels import (
    RETRO_FP,
    RETRO_FP_CANDIDATE,
    RETRO_TP,
)
from issue_link import strip_html_comments

# Matches a markdown checkbox bullet (`- [ ]` or `- [x]`, `*` accepted)
# that contains at least one `#N` reference. Limited to the bullet's own
# line so adjacent prose cannot accidentally attach. Capturing group 1
# is the followup number.
_BULLET_REF_RE = re.compile(
    r"^[ \t]*[-*][ \t]+\[[ xX]\][^\n]*?#(\d+)",
    re.MULTILINE,
)

DEFAULT_STALE_DAYS = 30


# ---------------------------------------------------------------------------
# Pure functions
# ---------------------------------------------------------------------------


def parse_followup_refs(body: str) -> list[int]:
    """Return sorted-unique list of issue/PR numbers referenced in checkbox bullets.

    Matches markdown checkbox bullets (``- [ ]`` or ``- [x]``, ``*``
    accepted as an alternative marker) that contain a ``#N`` reference
    on the same line. HTML comments are stripped first via
    :func:`issue_link.strip_html_comments` so ``<!-- - [ ] #1 -->`` is
    ignored. Carriage returns are normalised before matching.

    The convention is loose by design: operators today fill follow-ups
    either as bullet item 5 of ``## Proposed work`` (auto-retro template)
    or as a standalone ``## Follow-up issues`` section (operator
    preference). Both are matched because the bullet shape is the
    machine-stable contract, not the surrounding heading.
    """
    cleaned = strip_html_comments(body.replace("\r", ""))
    found = {int(m.group(1)) for m in _BULLET_REF_RE.finditer(cleaned)}
    return sorted(found)


def _parse_iso(value: str) -> datetime | None:
    """Parse an ISO 8601 timestamp or date. Returns None on failure."""
    text = (value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


def days_between(updated_at: str, today: str) -> int:
    """Return integer days between two ISO 8601 timestamps.

    Returns ``0`` when either value fails to parse: conservative default
    so an unparseable ``updated_at`` cannot synthesise a false stale
    signal. Callers that need to distinguish "could not parse" from
    "exactly the same instant" must do so before calling.
    """
    u = _parse_iso(updated_at)
    t = _parse_iso(today)
    if u is None or t is None:
        return 0
    delta = t - u
    return delta.days


def classify_followup_drift(
    *,
    found: bool,
    is_pr: bool,
    state: str,
    state_reason: str | None,
    merged: bool,
    updated_at: str,
    today: str,
    stale_days: int = DEFAULT_STALE_DAYS,
) -> str:
    """Return the drift result for a single follow-up referent.

    Returns one of: ``"ok"``, ``"fp_candidate"``, ``"fp_confirmed"``,
    ``"not_found"``. The orchestrator aggregates per-followup results
    into a per-retro drift via :func:`aggregate_drift`.

    PR-specific rules apply when ``is_pr`` is true; otherwise the
    issue-specific rules apply.
    """
    if not found:
        return "not_found"
    if is_pr:
        if state == "closed" and not merged:
            return "fp_confirmed"
        if state == "open" and days_between(updated_at, today) >= stale_days:
            return "fp_candidate"
        return "ok"
    if state == "closed" and state_reason == "not_planned":
        return "fp_confirmed"
    if state == "open" and days_between(updated_at, today) >= stale_days:
        return "fp_candidate"
    return "ok"


def aggregate_drift(per_followup: list[str]) -> str | None:
    """Aggregate per-followup drift results into one verdict for the retro.

    Returns ``None`` when there are zero follow-up results (no parseable
    ``#N`` references in the retro body, so the scanner has nothing to
    act on). Otherwise returns the worst signal in priority order:

    1. any ``fp_confirmed`` -> ``"fp_confirmed"``
    2. any ``fp_candidate`` or ``not_found`` -> ``"fp_candidate"``
       (``not_found`` collapses into candidate because the operator
       has to decide whether the missing reference is a typo or a
       genuine gap)
    3. otherwise -> ``"ok"``
    """
    if not per_followup:
        return None
    if "fp_confirmed" in per_followup:
        return "fp_confirmed"
    if "fp_candidate" in per_followup or "not_found" in per_followup:
        return "fp_candidate"
    return "ok"


def decide_target_label(
    aggregate: str | None, existing_labels: list[str]
) -> str | None:
    """Return the label to add to the retro, or ``None`` when no change is needed.

    Idempotency rules:

    * Operator-confirmed retros (``retro:tp`` or ``retro:fp`` already
      present) are never modified; the scanner must not overwrite
      operator state.
    * A candidate-level result is suppressed when the retro already
      carries ``retro:fp-candidate``.
    * A confirmed-level result upgrades a candidate-labelled retro to
      ``retro:fp`` (the candidate label is left in place; operators may
      strip it manually if they prefer a clean label set).
    """
    if aggregate is None or aggregate == "ok":
        return None
    if RETRO_TP in existing_labels or RETRO_FP in existing_labels:
        return None
    if aggregate == "fp_confirmed":
        return RETRO_FP
    if aggregate == "fp_candidate":
        if RETRO_FP_CANDIDATE in existing_labels:
            return None
        return RETRO_FP_CANDIDATE
    return None


def is_pr_payload(issue_payload: dict[str, Any]) -> bool:
    """True iff a ``/repos/{repo}/issues/{N}`` response represents a PR.

    The GitHub Issues endpoint includes a ``pull_request`` sub-object
    on PR rows and omits it on plain issues. The sub-object's truthiness
    is the documented marker.
    """
    return bool(issue_payload.get("pull_request"))


def build_summary(
    retros_scanned: int,
    labels_applied: dict[str, int],
    errors: int,
) -> str:
    """Return the markdown table written to ``$GITHUB_STEP_SUMMARY``."""
    lines = [
        "## retro-followup-drift summary\n",
        "\n",
        "| Field | Value |\n",
        "|---|---|\n",
        f"| Retros scanned | {retros_scanned} |\n",
        f"| `{RETRO_FP_CANDIDATE}` applied | "
        f"{labels_applied.get(RETRO_FP_CANDIDATE, 0)} |\n",
        f"| `{RETRO_FP}` applied | {labels_applied.get(RETRO_FP, 0)} |\n",
        f"| Per-followup fetch errors | {errors} |\n",
    ]
    return "".join(lines)


# ---------------------------------------------------------------------------
# Side-effecting boundary; mocked in tests
# ---------------------------------------------------------------------------


def gh_api(
    method: str,
    path: str,
    json_body: dict[str, Any] | None = None,
) -> str:
    """Thin wrapper over :func:`_github_api.rest_text` (ambient GH_TOKEN auth).

    Raises GitHubApiError on non-2xx so callers can treat a 404 as a drift signal.
    """
    return rest_text(method, path, json_body)


def is_404_error(exc: GitHubApiError) -> bool:
    """Detect a GitHub API 404 from a :class:`_github_api.GitHubApiError`."""
    return exc.code == 404


_DISCOVERY_LABEL_EXCLUSIONS = frozenset({RETRO_TP, RETRO_FP, RETRO_FP_CANDIDATE})


def search_retro_issues(repo: str) -> list[dict[str, Any]]:
    """Search open + closed retro issues in *repo*.

    Filters by the labels ``auto_retro.issue_labels`` always applies to a
    retro issue, resolved from the ``.gitapex/ssot.json`` ``label_consumers``
    entry for this script via :func:`_ssot.consumer_labels` rather than
    hardcoded literals, so a future label rename (e.g. #1041's still-open
    successor-label decision) is a registry-only edit. That entry also
    carries the three operator-decision labels (``retro:tp``/``retro:fp``/
    ``retro:fp-candidate``) this script uses elsewhere for label-state
    decisions, not issue discovery, so they are excluded here. The
    combination is narrow enough to avoid scanning the whole repo's issue
    list. ``per_page=100`` is the GitHub Search API maximum; this is
    sufficient for the repo's current retro volume (well under 100 in the
    lifetime of the framework).
    """
    try:
        registry_labels = _ssot.consumer_labels("scripts/scan_retro_followup_drift.py")
    except (KeyError, TypeError) as exc:
        # Narrowed to this call site (rather than widening main()'s except
        # tuple) so a drifted registry fails loud here without also
        # swallowing unrelated KeyError/TypeError bugs elsewhere in the
        # module's plain dict/string parsing.
        raise RuntimeError(f"retro-followup-drift discovery labels: {exc}") from exc
    discovery_labels = [label for label in registry_labels if label not in _DISCOVERY_LABEL_EXCLUSIONS]
    label_clause = " ".join(f"label:{label}" for label in discovery_labels)
    query = f"repo:{repo} is:issue {label_clause} in:title retro"
    encoded = quote(query, safe="")
    raw = gh_api("GET", f"/search/issues?q={encoded}&per_page=100")
    data = json.loads(raw) if raw.strip() else {}
    return list(data.get("items") or [])


def fetch_issue_or_pr(repo: str, number: int) -> dict[str, Any] | None:
    """Fetch a single issue or PR by number. Returns ``None`` on HTTP 404.

    Other failures propagate (CLAUDE.md section 4: fail loudly). The
    orchestrator catches per-followup propagated failures so one bad
    referent does not abort the whole scan.
    """
    try:
        raw = gh_api("GET", f"/repos/{repo}/issues/{number}")
    except GitHubApiError as exc:
        if is_404_error(exc):
            return None
        raise
    return json.loads(raw) if raw.strip() else None


def fetch_pr_merged(repo: str, number: int) -> bool:
    """Return whether PR *number* is merged.

    Used only when :func:`fetch_issue_or_pr` returned a PR payload that
    is in ``closed`` state. The PR endpoint exposes the ``merged``
    boolean directly; the Issues endpoint does not, so this second call
    is required to distinguish merged from closed-unmerged. On
    non-2xx the function propagates (loud), matching the surrounding
    policy.
    """
    raw = gh_api("GET", f"/repos/{repo}/pulls/{number}")
    payload = json.loads(raw) if raw.strip() else {}
    return bool(payload.get("merged"))


def apply_label(repo: str, number: int, label: str) -> None:
    """POST a label onto issue *number*. Loud failure on non-2xx."""
    gh_api(
        "POST",
        f"/repos/{repo}/issues/{number}/labels",
        {"labels": [label]},
    )


# ---------------------------------------------------------------------------
# Orchestrator + CLI
# ---------------------------------------------------------------------------


def _append_summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return
    with Path(path).open("a", encoding="utf-8") as fp:
        fp.write(text)


def _resolve_one_followup(
    repo: str, number: int, today: str, stale_days: int
) -> str:
    """Return the per-followup drift result for one referenced number.

    Performs the second ``/pulls/{N}`` call only when needed (PR in
    ``closed`` state) so the scanner does not pay the cost on every
    follow-up.
    """
    payload = fetch_issue_or_pr(repo, number)
    if payload is None:
        return "not_found"
    state = str(payload.get("state") or "")
    state_reason = payload.get("state_reason")
    updated_at = str(payload.get("updated_at") or "")
    is_pr = is_pr_payload(payload)
    merged = False
    if is_pr and state == "closed":
        # Only fetch the PR-specific endpoint when needed to distinguish
        # merged-closed from closed-unmerged.
        merged = fetch_pr_merged(repo, number)
    return classify_followup_drift(
        found=True,
        is_pr=is_pr,
        state=state,
        state_reason=state_reason if isinstance(state_reason, str) else None,
        merged=merged,
        updated_at=updated_at,
        today=today,
        stale_days=stale_days,
    )


def _retro_existing_labels(retro: dict[str, Any]) -> list[str]:
    """Extract label names from a retro search-result row."""
    labels = retro.get("labels") or []
    out: list[str] = []
    for entry in labels:
        name = entry.get("name") if isinstance(entry, dict) else None
        if isinstance(name, str) and name:
            out.append(name)
    return out


def run(
    repo: str,
    *,
    today: str | None = None,
    stale_days: int = DEFAULT_STALE_DAYS,
) -> int:
    """Top-level orchestrator. Returns process exit code.

    Iterates retro issues, parses follow-up references from each body,
    classifies drift per follow-up, and applies the appropriate label
    (or no-op when nothing changed). Per-followup fetch errors are
    fail-soft (the failed followup is skipped, the scan continues) so
    a transient API problem on one item does not abort the whole pass.
    """
    today_iso = today or datetime.now(UTC).date().isoformat()
    retros = search_retro_issues(repo)

    labels_applied: dict[str, int] = {RETRO_FP_CANDIDATE: 0, RETRO_FP: 0}
    errors = 0

    for retro in retros:
        retro_number = retro.get("number")
        if not isinstance(retro_number, int):
            continue
        existing = _retro_existing_labels(retro)
        # Skip operator-confirmed retros early to save API quota.
        if RETRO_TP in existing or RETRO_FP in existing:
            continue
        body = str(retro.get("body") or "")
        refs = parse_followup_refs(body)
        if not refs:
            continue

        per_followup: list[str] = []
        for n in refs:
            try:
                per_followup.append(_resolve_one_followup(repo, n, today_iso, stale_days))
            except GitHubApiError as exc:
                errors += 1
                print(
                    f"::warning::followup #{n} fetch failed for retro "
                    f"#{retro_number} (HTTP {exc.code}); skipping followup",
                    file=sys.stderr,
                )

        aggregate = aggregate_drift(per_followup)
        target = decide_target_label(aggregate, existing)
        if target is None:
            continue
        apply_label(repo, retro_number, target)
        labels_applied[target] = labels_applied.get(target, 0) + 1
        print(
            f"applied {target!r} to retro #{retro_number} "
            f"(aggregate={aggregate})"
        )

    _append_summary(build_summary(len(retros), labels_applied, errors))
    return 0


def _cmd_run(args: argparse.Namespace) -> int:
    repo = (
        args.repo
        or os.environ.get("REPO")
        or os.environ.get("GITHUB_REPOSITORY")
    )
    if not repo:
        print(
            "::error::missing --repo / $REPO / $GITHUB_REPOSITORY",
            file=sys.stderr,
        )
        return 1
    return run(repo, today=args.today, stale_days=args.stale_days)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser(
        "run",
        help="Scan retro issues for follow-up drift and apply TP/FP labels.",
    )
    p_run.add_argument("--repo", help="Override $REPO (owner/name).")
    p_run.add_argument(
        "--today",
        help=(
            "Override today's date (ISO 8601). Used by tests to make the "
            "stale-days check deterministic. Falls back to UTC today."
        ),
    )
    p_run.add_argument(
        "--stale-days",
        type=int,
        default=DEFAULT_STALE_DAYS,
        help=(
            "Days of no `updated_at` movement before an open follow-up is "
            f"treated as a candidate (default {DEFAULT_STALE_DAYS})."
        ),
    )
    p_run.set_defaults(func=_cmd_run)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except GitHubApiError as exc:
        print(
            f"::error::GitHub API failed (HTTP {exc.code}): {exc.body}",
            file=sys.stderr,
        )
        return 1
    except (ValueError, RuntimeError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
