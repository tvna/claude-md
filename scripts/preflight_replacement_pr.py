#!/usr/bin/env python3
"""Preflight guard for replacement pull-request loops.

Issue #632 records two failure modes:

* pre-merge replacement churn: an agent closes and recreates PRs to escape
  branch, CI, or single-commit pressure without stopping for root-cause
  analysis.
* post-terminal stale continuation: an agent opens another replacement after a
  candidate PR has already merged.

This script is a read-only guard for the PR-creation boundary. It can read a
fixture JSON file in tests or fetch candidate PRs from GitHub in live use, then
fails before another replacement PR is opened when the session needs a stop.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.parse
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from _github_api import apply_call

API_ROOT = "https://api.github.com"
REPLACEMENT_CLOSE_MARKER = "<!-- repair-loop:replacement-pr -->"
ROOT_CAUSE_REQUIRED_HEADINGS: tuple[str, ...] = (
    "Root cause:",
    "Existing PR cannot be repaired in place:",
    "Replacement is lower risk because:",
)

DecisionKind = Literal["allow", "require_root_cause", "hard_stop_already_merged"]


@dataclass(frozen=True)
class CandidatePR:
    """PR state needed by the replacement guard."""

    number: int
    state: str
    merged: bool
    created_at: str
    html_url: str = ""
    title: str = ""


@dataclass(frozen=True)
class GuardMetrics:
    """Machine-readable repair-loop pressure signal."""

    candidate_count: int
    replacement_count: int
    closed_superseded_count: int
    merged_numbers: tuple[int, ...]
    first_pr_created_at: str | None
    elapsed_seconds: int | None


@dataclass(frozen=True)
class GuardDecision:
    """The guard verdict plus enough context for a close/replan note."""

    kind: DecisionKind
    metrics: GuardMetrics
    reasons: tuple[str, ...]


def parse_candidate(raw: dict[str, Any]) -> CandidatePR:
    """Return a :class:`CandidatePR` from fixture or GitHub search JSON."""
    pull_request = raw.get("pull_request")
    merged_at = raw.get("merged_at")
    if isinstance(pull_request, dict):
        merged_at = pull_request.get("merged_at", merged_at)
    number = raw.get("number")
    if not isinstance(number, int):
        raise ValueError(f"candidate has invalid number: {number!r}")
    state = raw.get("state")
    if not isinstance(state, str):
        raise ValueError(f"candidate #{number} has invalid state: {state!r}")
    created_at = raw.get("created_at")
    if not isinstance(created_at, str) or not created_at:
        raise ValueError(f"candidate #{number} has invalid created_at: {created_at!r}")
    html_url = raw.get("html_url")
    title = raw.get("title")
    return CandidatePR(
        number=number,
        state=state.lower(),
        merged=bool(merged_at) or raw.get("merged") is True,
        created_at=created_at,
        html_url=html_url if isinstance(html_url, str) else "",
        title=title if isinstance(title, str) else "",
    )


def parse_candidates(raw: Any) -> list[CandidatePR]:
    """Parse candidates from either ``{"items": [...]}`` or ``[...]`` JSON."""
    items = raw.get("items") if isinstance(raw, dict) else raw
    if not isinstance(items, list):
        raise ValueError("candidate JSON must be a list or an object with an 'items' list")
    return sorted((parse_candidate(item) for item in items), key=lambda pr: (pr.created_at, pr.number))


def has_complete_root_cause_note(note: str) -> bool:
    """True when the note contains all required replacement-PR justifications."""
    return all(heading in note for heading in ROOT_CAUSE_REQUIRED_HEADINGS)


def compute_metrics(candidates: list[CandidatePR], *, now: datetime | None = None) -> GuardMetrics:
    """Return the repair-loop pressure metrics for *candidates*."""
    replacement_count = max(0, len(candidates) - 1)
    closed_superseded = sum(1 for pr in candidates if pr.state == "closed" and not pr.merged)
    merged_numbers = tuple(pr.number for pr in candidates if pr.merged)
    first_created = candidates[0].created_at if candidates else None
    elapsed = None
    if first_created and now is not None:
        elapsed = max(0, int((now - parse_iso8601(first_created)).total_seconds()))
    return GuardMetrics(
        candidate_count=len(candidates),
        replacement_count=replacement_count,
        closed_superseded_count=closed_superseded,
        merged_numbers=merged_numbers,
        first_pr_created_at=first_created,
        elapsed_seconds=elapsed,
    )


def decide_replacement(
    candidates: list[CandidatePR],
    *,
    root_cause_note: str,
    now: datetime | None = None,
) -> GuardDecision:
    """Decide whether opening another replacement PR is allowed."""
    metrics = compute_metrics(candidates, now=now)
    if metrics.merged_numbers:
        merged = ", ".join(f"#{n}" for n in metrics.merged_numbers)
        return GuardDecision(
            kind="hard_stop_already_merged",
            metrics=metrics,
            reasons=(
                f"candidate PR already merged: {merged}",
                "stop PR creation and write the retrospective note instead",
            ),
        )
    if metrics.replacement_count >= 1 and not has_complete_root_cause_note(root_cause_note):
        missing = [
            heading
            for heading in ROOT_CAUSE_REQUIRED_HEADINGS
            if heading not in root_cause_note
        ]
        return GuardDecision(
            kind="require_root_cause",
            metrics=metrics,
            reasons=(
                "replacement PR threshold crossed",
                "missing required note headings: " + ", ".join(missing),
            ),
        )
    return GuardDecision(
        kind="allow",
        metrics=metrics,
        reasons=("replacement PR preflight passed",),
    )


def format_close_marker(*, superseded_pr: int, issue: int, replacement_pr: int | None = None) -> str:
    """Return a stable marker for replacement-close comments."""
    parts = [
        REPLACEMENT_CLOSE_MARKER,
        f"superseded_pr=#{superseded_pr}",
        f"issue=#{issue}",
    ]
    if replacement_pr is not None:
        parts.append(f"replacement_pr=#{replacement_pr}")
    return " ".join(parts)


def render_report(decision: GuardDecision) -> str:
    """Return a human-readable report with stable metric lines."""
    metrics = decision.metrics
    lines = [
        f"decision: {decision.kind}",
        f"candidate_count: {metrics.candidate_count}",
        f"replacement_count: {metrics.replacement_count}",
        f"closed_superseded_count: {metrics.closed_superseded_count}",
        "merged_prs: "
        + (", ".join(f"#{n}" for n in metrics.merged_numbers) if metrics.merged_numbers else "(none)"),
        f"first_pr_created_at: {metrics.first_pr_created_at or '(none)'}",
        f"elapsed_seconds: {metrics.elapsed_seconds if metrics.elapsed_seconds is not None else '(unknown)'}",
    ]
    lines.extend(f"reason: {reason}" for reason in decision.reasons)
    if decision.kind == "allow":
        lines.insert(0, "OK: replacement PR preflight passed")
    else:
        lines.insert(0, "::error::replacement PR preflight blocked PR creation")
    return "\n".join(lines)


def load_root_cause_note(path: str | None, inline: str | None) -> str:
    """Load root-cause text from ``--root-cause-note`` and/or inline text."""
    parts: list[str] = []
    if path:
        parts.append(Path(path).read_text(encoding="utf-8"))
    if inline:
        parts.append(inline)
    return "\n".join(parts)


def load_candidates_from_file(path: str) -> list[CandidatePR]:
    """Load candidate PR states from fixture JSON."""
    return parse_candidates(json.loads(Path(path).read_text(encoding="utf-8")))


def fetch_candidates(repo: str, issue: int, *, token: str) -> list[CandidatePR]:
    """Fetch PRs that mention ``#<issue>`` from GitHub search.

    GitHub's search result embeds only a small ``pull_request`` object; it does
    not reliably include ``merged_at``. Fetch each PR detail before parsing so
    the hard-stop branch can see a merged terminal state.
    """
    query = urllib.parse.quote(f"repo:{repo} type:pr #{issue}", safe="")
    status, body = apply_call(
        method="GET",
        url=f"{API_ROOT}/search/issues?q={query}",
        payload=None,
        token=token,
    )
    if not (200 <= status < 300):
        raise RuntimeError(f"GitHub search failed with HTTP {status}: {body[:200]}")
    raw = json.loads(body)
    items = raw.get("items") if isinstance(raw, dict) else None
    if not isinstance(items, list):
        raise ValueError("GitHub search response did not contain an items list")
    details = [fetch_pr_detail(repo, parse_candidate(item).number, token=token) for item in items]
    return parse_candidates(details)


def fetch_pr_detail(repo: str, number: int, *, token: str) -> dict[str, Any]:
    """Fetch a PR detail object with reliable ``merged_at`` information."""
    status, body = apply_call(
        method="GET",
        url=f"{API_ROOT}/repos/{repo}/pulls/{number}",
        payload=None,
        token=token,
    )
    if not (200 <= status < 300):
        raise RuntimeError(f"PR detail fetch for #{number} failed with HTTP {status}: {body[:200]}")
    data = json.loads(body)
    if not isinstance(data, dict):
        raise ValueError(f"PR detail fetch for #{number} returned non-object JSON")
    return data


def parse_iso8601(value: str) -> datetime:
    """Parse GitHub-style ISO 8601 timestamps as aware UTC datetimes."""
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def parse_now(value: str | None) -> datetime | None:
    """Return an aware UTC datetime for ``--now`` or ``None`` when absent."""
    if value is None:
        return None
    return parse_iso8601(value)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="Check whether another replacement PR may be opened.")
    verify.add_argument("--repo", required=True, help="Repository in owner/name form.")
    verify.add_argument("--issue", required=True, type=int, help="Parent issue number.")
    verify.add_argument("--candidates-json", help="Fixture JSON with candidate PR states.")
    verify.add_argument("--root-cause-note", help="Path to the root-cause note.")
    verify.add_argument("--root-cause-text", help="Inline root-cause note text.")
    verify.add_argument("--now", help="UTC timestamp used for elapsed-time reporting.")
    marker = sub.add_parser("close-marker", help="Render the stable replacement close-comment marker.")
    marker.add_argument("--issue", required=True, type=int)
    marker.add_argument("--superseded-pr", required=True, type=int)
    marker.add_argument("--replacement-pr", type=int)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "close-marker":
        print(
            format_close_marker(
                superseded_pr=args.superseded_pr,
                issue=args.issue,
                replacement_pr=args.replacement_pr,
            )
        )
        return 0

    try:
        if args.candidates_json:
            candidates = load_candidates_from_file(args.candidates_json)
        else:
            token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
            if not token:
                print(
                    "::error::GH_TOKEN or GITHUB_TOKEN is required when --candidates-json is not provided",
                    file=sys.stderr,
                )
                return 1
            candidates = fetch_candidates(args.repo, args.issue, token=token)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"::error::preflight_replacement_pr: {exc}", file=sys.stderr)
        return 1

    try:
        root_cause_note = load_root_cause_note(args.root_cause_note, args.root_cause_text)
        decision = decide_replacement(candidates, root_cause_note=root_cause_note, now=parse_now(args.now))
    except (OSError, ValueError) as exc:
        print(f"::error::preflight_replacement_pr: {exc}", file=sys.stderr)
        return 1

    report = render_report(decision)
    stream = sys.stdout if decision.kind == "allow" else sys.stderr
    print(report, file=stream)
    return 0 if decision.kind == "allow" else 1


if __name__ == "__main__":
    raise SystemExit(main())
