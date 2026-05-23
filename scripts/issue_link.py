#!/usr/bin/env python3
"""Verify that a PR body references at least one existing issue/PR.

The workflow ``.github/workflows/verify-issue-link.yml`` shells out to
this module. The contract is:

* Read the PR body from ``--body-file`` when supplied, otherwise from
  the ``PR_BODY`` env var for compatibility.
* Strip HTML comments before parsing, so ``<!-- Refs #1 -->`` is ignored.
* Extract case-insensitive line-anchored references of the form
  ``(Refs|Closes|Fixes|Resolves) #N``.
* Verify each ``#N`` resolves via ``gh api /repos/<repo>/issues/N``.
* Exit 0 only when at least one reference is present AND every reference
  resolves; exit 1 otherwise. ``::error::`` annotations surface failures
  in the GitHub Actions UI.

Tested by ``tests/test_issue_link.py``. CLAUDE.md section 3
(deterministic harness) and #123 (CI shell -> Python+pytest).
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
import os
from pathlib import Path
import re
import subprocess
import sys

from _trusted_bots import _TRUSTED_BOT_LOGINS

_HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)

# Match a line that begins (after optional indentation) with one of the
# GitHub-recognized issue keywords followed by ``#N``. Anchored to the
# start of the line so a passing mention like "see Refs #5 above" is
# ignored, matching the original ``grep -E '^[[:space:]]*...'``.
_REF_LINE = re.compile(
    r"^[ \t]*(?:Refs|Closes|Fixes|Resolves)[ \t]+#(\d+)",
    re.IGNORECASE | re.MULTILINE,
)

_NO_REFS_MSG = (
    "::error::PR body has no issue reference. Add a line like "
    "'Refs #<num>' or 'Closes #<num>' (case-insensitive keywords: "
    "Refs, Closes, Fixes, Resolves). See CLAUDE.md §3."
)


def strip_html_comments(body: str) -> str:
    """Remove ``<!-- ... -->`` blocks (including multi-line) from *body*.

    Equivalent to ``perl -0777 -pe 's/<!--.*?-->//gs'``: non-greedy so
    sequential comments are stripped independently.
    """
    return _HTML_COMMENT.sub("", body)


def extract_refs(body: str) -> list[int]:
    """Return sorted-unique list of issue numbers referenced in *body*.

    Matching is case-insensitive and line-anchored: only references where
    the keyword appears at the start of the line (optionally indented)
    are returned. Composes with :func:`strip_html_comments` -- callers
    that want HTML-commented refs ignored must pre-process *body*.
    """
    found = {int(m.group(1)) for m in _REF_LINE.finditer(body)}
    return sorted(found)


def verify_ref_exists(
    repo: str,
    number: int,
    *,
    runner: Callable[..., object] | None = None,
) -> bool:
    """Return True iff ``gh api /repos/<repo>/issues/<number>`` succeeds.

    Returns False on any subprocess failure (missing ``gh``, auth error,
    HTTP 404, timeout). Callers that need to distinguish causes should
    use ``subprocess.run`` directly; this function collapses "exists"
    into a single bool to match the workflow's behaviour.
    """
    if runner is None:
        runner = subprocess.run

    try:
        runner(
            [
                "gh", "api",
                f"/repos/{repo}/issues/{number}",
                "--silent",
            ],
            capture_output=True,
            timeout=30,
            check=True,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return False
    return True


def issue_exists(repo: str, number: int) -> bool:
    """Backward-compatible wrapper for older callers/tests."""
    return verify_ref_exists(repo, number)


def _verify(repo: str, body: str, author: str | None = None) -> int:
    if author is not None and author in _TRUSTED_BOT_LOGINS:
        print(f"skipped: trusted bot author ({author})")
        return 0

    cleaned = strip_html_comments(body.replace("\r", ""))
    refs = extract_refs(cleaned)

    if not refs:
        print(_NO_REFS_MSG)
        return 1

    fail = 0
    for n in refs:
        if issue_exists(repo, n):
            print(f"OK: #{n} resolves in {repo}.")
        else:
            print(f"::error::Referenced #{n} does not exist in {repo}.")
            fail = 1
    return fail


def _cmd_verify(args: argparse.Namespace) -> int:
    if args.body_file is None:
        body = os.environ.get("PR_BODY", "")
    else:
        body = Path(args.body_file).read_text(encoding="utf-8")
    author = args.author if args.author is not None else os.environ.get("PR_AUTHOR")
    return _verify(args.repo, body, author=author or None)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Verify each Refs/Closes/Fixes/Resolves #N in PR_BODY resolves.",
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
    p_verify.add_argument(
        "--author",
        help=(
            "PR author login (e.g. 'dependabot[bot]'). When the login is in "
            "the trusted-bot allowlist, the Refs check is skipped. Falls back "
            "to $PR_AUTHOR when omitted."
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
