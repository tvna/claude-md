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
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

from _ref_classifier import (
    CLOSING_KEYWORDS as _CLOSING_KEYWORDS,
)
from _ref_classifier import (
    TRACKING_LABEL as _TRACKING_LABEL,
)
from _ref_classifier import (
    body_has_partial_marker as _shared_body_has_partial_marker,
)
from _ref_classifier import (
    classify_refs as _shared_classify_refs,
)
from _ref_classifier import (
    format_no_closing_keyword_msg as _shared_format_no_closing_keyword_msg,
)
from _ref_classifier import (
    strip_html_comments as _shared_strip_html_comments,
)
from _trusted_bots import _TRUSTED_BOT_LOGINS

# ``_REF_LINE`` is the keyword-non-capturing variant used only by
# :func:`extract_refs`. The keyword-capturing form lives in
# ``_ref_classifier`` (shared with the client-side hook) -- this regex
# is local because no other module needs the bare number-only view.
_REF_LINE = re.compile(
    r"^[ \t]*(?:Refs|Closes|Fixes|Resolves)[ \t]+#(\d+)",
    re.IGNORECASE | re.MULTILINE,
)

_NO_REFS_MSG = (
    "::error::PR body has no issue reference. Add a line like "
    "'Closes #<num>' or 'Refs #<num>' (case-insensitive keywords: "
    "Refs, Closes, Fixes, Resolves). See CLAUDE.md §3."
)


def strip_html_comments(body: str) -> str:
    """Remove ``<!-- ... -->`` blocks (including multi-line) from *body*.

    Equivalent to ``perl -0777 -pe 's/<!--.*?-->//gs'``: non-greedy so
    sequential comments are stripped independently.
    """
    return _shared_strip_html_comments(body)


def extract_refs(body: str) -> list[int]:
    """Return sorted-unique list of issue numbers referenced in *body*.

    Matching is case-insensitive and line-anchored: only references where
    the keyword appears at the start of the line (optionally indented)
    are returned. Composes with :func:`strip_html_comments` -- callers
    that want HTML-commented refs ignored must pre-process *body*.
    """
    found = {int(m.group(1)) for m in _REF_LINE.finditer(body)}
    return sorted(found)


def classify_refs(body: str) -> list[tuple[str, int]]:
    """Return [(keyword_lowercase, number)] for each reference in *body*.

    Preserves insertion order, de-duplicated on the (keyword, number)
    pair. Same line-anchored matching contract as :func:`extract_refs`,
    but exposes the keyword so callers can distinguish closing keywords
    (`Closes`, `Fixes`, `Resolves`) from the non-closing `Refs`.
    """
    return _shared_classify_refs(body)


def body_has_partial_marker(raw_body: str) -> bool:
    """Return True if *raw_body* contains a ``<!-- partial -->`` marker.

    Checked against the raw body BEFORE :func:`strip_html_comments`,
    because the marker itself is an HTML comment that would otherwise be
    removed. The marker opts the PR out of the closing-keyword gate
    (per #216 PR-A) for legitimate partial work against a non-umbrella
    issue.
    """
    return _shared_body_has_partial_marker(raw_body)


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


def get_issue_labels(
    repo: str,
    number: int,
    *,
    runner: Callable[..., object] | None = None,
) -> list[str] | None:
    """Return label names on issue/PR <number>, or ``None`` on failure.

    Uses ``gh api ... --jq '.labels[].name'`` so the output is one label
    per line and no JSON parsing is needed. ``None`` means "could not
    determine" -- callers should fail-safe (treat as not tracking) so
    flaky API calls cannot silently unlock the closing-keyword gate.
    """
    if runner is None:
        runner = subprocess.run

    try:
        result = runner(
            [
                "gh", "api",
                f"/repos/{repo}/issues/{number}",
                "--jq", ".labels[].name",
            ],
            capture_output=True,
            timeout=30,
            check=True,
        )
    except (subprocess.SubprocessError, FileNotFoundError, OSError):
        return None

    raw = getattr(result, "stdout", b"") or b""
    if isinstance(raw, bytes):
        raw = raw.decode("utf-8", errors="replace")
    return [line.strip() for line in raw.splitlines() if line.strip()]


def _format_no_closing_keyword_msg(numbers: list[int]) -> str:
    return _shared_format_no_closing_keyword_msg(numbers, prefix="::error::")


def _verify(repo: str, body: str, author: str | None = None) -> int:
    if author is not None and author in _TRUSTED_BOT_LOGINS:
        print(f"skipped: trusted bot author ({author})")
        return 0

    raw_body = body.replace("\r", "")
    cleaned = strip_html_comments(raw_body)
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
    if fail:
        return 1

    # Closing-keyword gate (per #216 PR-A): if at least one reference is
    # a closing keyword, the PR will auto-close its issue on merge -- pass.
    classified = classify_refs(cleaned)
    if any(kw in _CLOSING_KEYWORDS for kw, _ in classified):
        return 0

    # All references are non-closing 'Refs'. Allow opt-out via marker.
    if body_has_partial_marker(raw_body):
        print(
            "note: PR body has '<!-- partial -->' marker; "
            "closing-keyword check skipped."
        )
        return 0

    # Otherwise require every Refs target to be a tracking umbrella.
    refs_only = sorted({n for kw, n in classified if kw == "refs"})
    for n in refs_only:
        labels = get_issue_labels(repo, n)
        if labels is None or _TRACKING_LABEL not in labels:
            print(_format_no_closing_keyword_msg(refs_only))
            return 1
    print(
        f"note: PR body references only tracking umbrellas "
        f"({', '.join(f'#{n}' for n in refs_only)}); "
        "closing-keyword check passes."
    )
    return 0


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
