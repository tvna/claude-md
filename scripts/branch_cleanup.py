#!/usr/bin/env python3
"""Branch cleanup survey and rolling issue reconciliation helpers.

This module keeps the read-only branch cleanup workflow testable. The
destructive delete path from #31 Goal D is intentionally out of scope.
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal
from urllib.parse import quote

import _ssot
from _github_api import GitHubApiError, paginate, rest_json

IssueAction = Literal["create", "append", "close", "silent"]

SECONDS_PER_DAY = 86_400


def parse_dry_run(raw: str) -> bool:
    if raw == "true":
        return True
    if raw == "false":
        return False
    raise ValueError(f"Invalid dry_run value: {raw}")


def parse_min_age_days(raw: str) -> int:
    if not raw.isdecimal():
        raise ValueError(f"Invalid min_age_days (must be non-negative integer): {raw}")
    return int(raw)


def is_candidate(
    *,
    branch: str,
    default_branch: str,
    last_commit_utc: datetime,
    now_utc: datetime,
    min_age_days: int,
    has_open_pr: bool,
) -> bool:
    if branch == default_branch:
        return False
    if has_open_pr:
        return False
    age_seconds = int((now_utc - last_commit_utc).total_seconds())
    return age_seconds > min_age_days * SECONDS_PER_DAY


def format_summary_row(
    branch: str,
    last_commit_utc: datetime,
    age_days: int,
    sha: str,
) -> str:
    return (
        f"| `{branch}` | {_format_github_datetime(last_commit_utc)} | "
        f"{age_days} | `{sha[:7]}` |"
    )


def decide_issue_action(
    *,
    candidate_count: int,
    existing_issue: dict[str, Any] | None,
    idle_seconds: int,
    idle_threshold_seconds: int,
) -> IssueAction:
    if candidate_count > 0:
        return "append" if existing_issue is not None else "create"
    if existing_issue is None:
        return "silent"
    if idle_seconds >= idle_threshold_seconds:
        return "close"
    return "silent"


def _token() -> str:
    return os.environ.get("GH_TOKEN", "")


def list_branches(repo: str) -> list[tuple[str, str]]:
    branches: list[tuple[str, str]] = []
    for entry in paginate(f"/repos/{repo}/branches", token=_token()):
        if not isinstance(entry, dict):
            continue
        name = entry.get("name")
        sha = ((entry.get("commit") or {}).get("sha"))
        if not isinstance(name, str) or not isinstance(sha, str):
            raise ValueError(f"malformed branch row from API: {entry!r}")
        branches.append((name, sha))
    return branches


def get_last_commit_date(repo: str, sha: str) -> datetime:
    data = rest_json("GET", f"/repos/{repo}/commits/{sha}", token=_token())
    commit = (data or {}).get("commit") or {}
    committer = commit.get("committer") or {}
    return _parse_github_datetime(str(committer.get("date") or "").strip())


def count_open_prs_for_head(repo: str, branch: str) -> int:
    owner = repo.split("/", 1)[0]
    # Encode the owner:branch value: a branch ref may legally contain `#`, `&`,
    # or a space, which would otherwise be parsed as a URL fragment / extra
    # query parameter and silently zero the count (Codex review on #2122).
    # Keep `:` and `/` literal so GitHub still parses the head filter and
    # slash-containing branch names (feature/foo) match.
    head = quote(f"{owner}:{branch}", safe=":/")
    prs = paginate(
        f"/repos/{repo}/pulls?state=open&head={head}", token=_token()
    )
    return len(prs)


def find_rolling_issue(repo: str, title: str) -> dict[str, Any] | None:
    query = f'repo:{repo} is:issue is:open in:title "{title}"'
    data = rest_json(
        "GET", f"/search/issues?q={quote(query, safe='')}", token=_token()
    )
    for issue in (data or {}).get("items") or []:
        if isinstance(issue, dict) and issue.get("title") == title:
            return _normalize_issue(issue)
    return None


def comment_on_issue(repo: str, issue_number: int, body_file: Path) -> None:
    body = body_file.read_text(encoding="utf-8")
    rest_json(
        "POST",
        f"/repos/{repo}/issues/{issue_number}/comments",
        {"body": body},
        token=_token(),
    )


def create_issue(repo: str, title: str, body_file: Path) -> None:
    body = body_file.read_text(encoding="utf-8")
    labels = list(_ssot.consumer_labels("scripts/branch_cleanup.py"))
    rest_json(
        "POST",
        f"/repos/{repo}/issues",
        {"title": title, "body": body, "labels": labels},
        token=_token(),
    )


def close_issue_with_comment(repo: str, issue_number: int, comment: str) -> None:
    # gh issue close --comment posts a comment then closes; replicate as a
    # comment POST followed by a state PATCH so the rolling issue keeps its
    # closing note.
    token = _token()
    rest_json(
        "POST",
        f"/repos/{repo}/issues/{issue_number}/comments",
        {"body": comment},
        token=token,
    )
    rest_json(
        "PATCH",
        f"/repos/{repo}/issues/{issue_number}",
        {"state": "closed", "state_reason": "completed"},
        token=token,
    )


def fetch_issue_last_activity(repo: str, issue_number: int) -> datetime:
    token = _token()
    issue = rest_json("GET", f"/repos/{repo}/issues/{issue_number}", token=token)
    comments = paginate(
        f"/repos/{repo}/issues/{issue_number}/comments", token=token
    )
    comment_dates = [
        c["created_at"]
        for c in comments
        if isinstance(c, dict) and isinstance(c.get("created_at"), str)
    ]
    last_activity = comment_dates[-1] if comment_dates else (issue or {}).get("created_at", "")
    return _parse_github_datetime(str(last_activity).strip())


def render_survey(
    *,
    repo: str,
    dry_run_raw: str,
    min_age_days_raw: str,
    default_branch: str,
    event_name: str,
    run_url: str,
    now_utc: datetime,
) -> tuple[str, str | None, int]:
    dry_run = parse_dry_run(dry_run_raw)
    min_age_days = parse_min_age_days(min_age_days_raw)
    branches = list_branches(repo)
    rows: list[str] = []

    for branch, sha in branches:
        if branch == default_branch:
            continue
        last_commit = get_last_commit_date(repo, sha)
        age_seconds = int((now_utc - last_commit).total_seconds())
        if age_seconds <= min_age_days * SECONDS_PER_DAY:
            continue
        has_open_pr = count_open_prs_for_head(repo, branch) > 0
        if not is_candidate(
            branch=branch,
            default_branch=default_branch,
            last_commit_utc=last_commit,
            now_utc=now_utc,
            min_age_days=min_age_days,
            has_open_pr=has_open_pr,
        ):
            continue
        age_days = age_seconds // SECONDS_PER_DAY
        rows.append(format_summary_row(branch, last_commit, age_days, sha))

    summary_lines = _survey_header(
        event_name=event_name,
        run_url=run_url,
        dry_run=dry_run,
        min_age_days=min_age_days,
        default_branch=default_branch,
        branch_count=len(branches),
    )
    comment_lines = _comment_header(
        now_utc=now_utc,
        event_name=event_name,
        run_url=run_url,
        dry_run=dry_run,
        min_age_days=min_age_days,
    )

    if rows:
        summary_lines.extend(rows)
        comment_lines.extend(rows)
    else:
        summary_lines.append("| _(none)_ | - | - | - |")

    footer = (
        f"Candidates: `{len(rows)}`. **dry-run** - no branches deleted "
        "(no DELETE code path exists yet; see #31 Goal D)."
    )
    summary_lines.extend(["", footer])

    comment: str | None = None
    if rows:
        comment_lines.extend(["", footer])
        comment = "\n".join(comment_lines) + "\n"
    else:
        summary_lines.extend(
            [
                "",
                '_Empty run - rolling issue not touched. See "Maintain rolling '
                'summary issue" step for idle-close behaviour._',
            ]
        )

    return "\n".join(summary_lines) + "\n", comment, len(rows)


def _cmd_survey(args: argparse.Namespace) -> int:
    now = _now_utc()
    summary, comment, candidate_count = render_survey(
        repo=args.repo,
        dry_run_raw=args.dry_run,
        min_age_days_raw=args.min_age_days,
        default_branch=args.default_branch,
        event_name=args.event_name,
        run_url=args.run_url,
        now_utc=now,
    )
    print(summary, end="")
    print(f"candidate_count={candidate_count}", file=sys.stderr)
    if args.github_output:
        with Path(args.github_output).open("a", encoding="utf-8") as fp:
            fp.write(f"candidate_count={candidate_count}\n")
    out = Path(args.out)
    if comment is None:
        out.unlink(missing_ok=True)
    else:
        out.write_text(comment, encoding="utf-8")
    return 0


def _cmd_reconcile(args: argparse.Namespace) -> int:
    candidate_count = int(args.candidate_count)
    existing_issue = find_rolling_issue(args.repo, args.title)
    idle_threshold_seconds = int(args.idle_close_days) * SECONDS_PER_DAY
    idle_seconds = 0
    last_activity: datetime | None = None
    now = _now_utc()

    if existing_issue is not None:
        last_activity = fetch_issue_last_activity(args.repo, existing_issue["number"])
        idle_seconds = int((now - last_activity).total_seconds())

    action = decide_issue_action(
        candidate_count=candidate_count,
        existing_issue=existing_issue,
        idle_seconds=idle_seconds,
        idle_threshold_seconds=idle_threshold_seconds,
    )

    if action == "append":
        number = existing_issue["number"]  # type: ignore[index]
        print(f"Appending to existing summary issue #{number}")
        comment_on_issue(args.repo, number, Path(args.comment_file))
    elif action == "create":
        print("Creating new rolling summary issue (first non-empty run)")
        create_issue(args.repo, args.title, Path(args.comment_file))
    elif action == "close":
        number = existing_issue["number"]  # type: ignore[index]
        idle_days = idle_seconds // SECONDS_PER_DAY
        # Narrowing: idle_seconds is set only when last_activity is not None
        # (see the matching branch above). CI runs Python without -O, so this
        # assert still raises if the invariant is ever violated. Tracked in #190.
        assert last_activity is not None  # noqa: S101 -- type-narrowing invariant
        print(
            f"Issue #{number} idle for {idle_days}d "
            f"(>= {args.idle_close_days}d). Auto-closing."
        )
        close_issue_with_comment(
            args.repo,
            number,
            _close_comment(
                idle_days=idle_days,
                idle_close_days=int(args.idle_close_days),
                last_activity=last_activity,
                run_url=args.run_url,
            ),
        )
    else:
        if existing_issue is None:
            print("Empty run, no open rolling issue. Silent.")
        else:
            number = existing_issue["number"]
            idle_days = idle_seconds // SECONDS_PER_DAY
            print(
                f"Issue #{number} idle for {idle_days}d "
                f"(< {args.idle_close_days}d). No action."
            )
    return 0


def _survey_header(
    *,
    event_name: str,
    run_url: str,
    dry_run: bool,
    min_age_days: int,
    default_branch: str,
    branch_count: int,
) -> list[str]:
    return [
        "## Branch cleanup - survey",
        "",
        f"- Trigger: `{event_name}`",
        f"- Run: {run_url}",
        f"- dry_run: `{str(dry_run).lower()}`",
        f"- min_age_days: `{min_age_days}`",
        f"- default_branch: `{default_branch}` (excluded)",
        f"- Total branches: `{branch_count}`",
        "",
        "| Branch | Last commit (UTC) | Age (days) | Last commit SHA |",
        "|---|---|---|---|",
    ]


def _comment_header(
    *,
    now_utc: datetime,
    event_name: str,
    run_url: str,
    dry_run: bool,
    min_age_days: int,
) -> list[str]:
    return [
        f"## Run {_format_github_datetime(now_utc)}",
        "",
        f"- Trigger: `{event_name}`",
        f"- Run: {run_url}",
        f"- dry_run: `{str(dry_run).lower()}`",
        f"- min_age_days: `{min_age_days}`",
        "",
        "| Branch | Last commit (UTC) | Age (days) | Last commit SHA |",
        "|---|---|---|---|",
    ]


def _close_comment(
    *,
    idle_days: int,
    idle_close_days: int,
    last_activity: datetime,
    run_url: str,
) -> str:
    return (
        f"Auto-closed: no cleanup candidates for {idle_days} days "
        f"(last activity: {_format_github_datetime(last_activity)}; "
        f"threshold: {idle_close_days} days).\n\n"
        "The next non-empty survey will open a fresh rolling issue. To reopen "
        "this one manually, comment and use **Reopen**; the workflow will "
        "resume appending to it on the next non-empty run.\n\n"
        f"Closed by [run]({run_url})."
    )


def _parse_github_datetime(raw: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"malformed GitHub datetime: {raw!r}") from exc
    if parsed.tzinfo is None:
        raise ValueError(f"GitHub datetime must include timezone: {raw!r}")
    return parsed.astimezone(UTC)


def _format_github_datetime(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _normalize_issue(issue: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(issue)
    if "createdAt" in normalized:
        normalized["created_at"] = normalized.pop("createdAt")
    return normalized


def _now_utc() -> datetime:
    return datetime.now(UTC)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_survey = sub.add_parser("survey", help="Render branch cleanup survey.")
    p_survey.add_argument("--repo", required=True)
    p_survey.add_argument("--dry-run", required=True)
    p_survey.add_argument("--min-age-days", required=True)
    p_survey.add_argument("--default-branch", required=True)
    p_survey.add_argument("--event-name", default="")
    p_survey.add_argument("--run-url", default="")
    p_survey.add_argument("--out", required=True)
    p_survey.add_argument("--github-output")
    p_survey.set_defaults(func=_cmd_survey)

    p_reconcile = sub.add_parser(
        "reconcile", help="Reconcile rolling branch cleanup issue."
    )
    p_reconcile.add_argument("--repo", required=True)
    p_reconcile.add_argument("--title", required=True)
    p_reconcile.add_argument("--candidate-count", required=True)
    p_reconcile.add_argument("--comment-file", required=True)
    p_reconcile.add_argument("--idle-close-days", required=True)
    p_reconcile.add_argument("--run-url", default="")
    p_reconcile.set_defaults(func=_cmd_reconcile)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (GitHubApiError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
