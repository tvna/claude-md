#!/usr/bin/env python3
"""Verify that linked issue titles satisfy the repository title policy.

For each issue referenced in the PR body (via Refs/Closes/Fixes/Resolves #N),
fetches the issue title from GitHub and validates it with the same rules as
``title_policy.py verify --kind issue``. Fails the PR check when any linked
issue title violates policy, closing the gap where a PR could appear successful
while its linked issue carries a policy-violating title.

Tracked by #941.
"""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
from pathlib import Path

import title_policy
from _github_api import GitHubApiError, rest_json
from _ref_classifier import REF_LINE_KEYWORD_RE, strip_html_comments


def _extract_refs(body: str) -> list[int]:
    """Return sorted-unique list of issue numbers referenced in *body*.

    Line-anchored, case-insensitive match on the same keywords as
    ``issue_link.extract_refs``. Callers must pre-process *body* with
    :func:`strip_html_comments` to suppress commented-out references.
    """
    found = {int(m.group(2)) for m in REF_LINE_KEYWORD_RE.finditer(body)}
    return sorted(found)


def get_issue_title(
    repo: str,
    number: int,
    *,
    token: str | None = None,
) -> str | None:
    """Return the title of issue *number* in *repo*, or ``None`` on failure.

    ``None`` means the API call failed (no token, network error, non-2xx,
    malformed body); callers must treat it as a gate failure so a flaky API
    cannot silently allow a bad title through.
    """
    if token is None:
        token = os.environ.get("GH_TOKEN", "")
    try:
        data = rest_json("GET", f"/repos/{repo}/issues/{number}", token=token)
    except (GitHubApiError, urllib.error.URLError, OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    title = data.get("title")
    if not isinstance(title, str):
        return None
    return title.strip() or None


def _validate_issue_title(title: str, number: int) -> list[str]:
    """Return ``::error::`` lines for *title*; empty list when valid."""
    errors: list[str] = []
    suffix = f" Fix the title on issue #{number} before this PR can succeed."

    if not title_policy.is_ascii_title(title):
        details = ", ".join(title_policy.describe_non_ascii(title))
        detail_str = f" Non-ASCII code points: {details}." if details else ""
        errors.append(
            f"::error::Issue #{number}: title must be ASCII-only for "
            f"prompt-injection defense.{detail_str}{suffix}"
        )

    if not title_policy.follows_naming_convention(title, kind="issue"):
        hint = title_policy.naming_convention_hint("issue")
        errors.append(
            f"::error::Issue #{number}: title must follow repository naming "
            f"convention: {hint}.{suffix}"
        )
    else:
        for finding in title_policy.type_fit_findings(title, kind="issue"):
            formatted = title_policy.format_type_fit_finding(finding)
            errors.append(
                f"::error::Issue #{number}: title type does not fit the work: "
                f"{formatted}{suffix}"
            )

    return errors


def verify_linked_issue_titles(
    repo: str,
    body: str,
    *,
    token: str | None = None,
) -> int:
    """Validate linked issue titles; return 0 on success, 1 on failure."""
    cleaned = strip_html_comments(body.replace("\r", ""))
    refs = _extract_refs(cleaned)

    if not refs:
        print("note: PR body has no linked issues; linked-issue title check skipped.")
        return 0

    fail = 0
    for n in refs:
        issue_title = get_issue_title(repo, n, token=token)
        if issue_title is None:
            print(
                f"::error::Could not fetch title for issue #{n} in {repo}. "
                "Verify that GH_TOKEN has 'issues: read' permission."
            )
            fail = 1
            continue

        errors = _validate_issue_title(issue_title, n)
        if errors:
            for line in errors:
                print(line)
            fail = 1
        else:
            print(f"OK: issue #{n} title passes title policy.")

    return fail


def _cmd_verify(args: argparse.Namespace) -> int:
    if args.body_file is None:
        body = os.environ.get("PR_BODY", "")
    else:
        body = Path(args.body_file).read_text(encoding="utf-8")
    return verify_linked_issue_titles(args.repo, body)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Validate linked issue titles against the repository title policy.",
    )
    p_verify.add_argument(
        "--repo",
        required=True,
        help="Repository slug, e.g. 'owner/name'.",
    )
    p_verify.add_argument(
        "--body-file",
        help=(
            "Path to a file containing the PR body. Falls back to PR_BODY "
            "when omitted."
        ),
    )
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
