#!/usr/bin/env python3
"""Verify that issue and PR bodies contain their template's required sections.

The workflow ``.github/workflows/verify-body-policy.yml`` shells out to
this module. The contract is:

* Read the body from ``--body-file`` when supplied, otherwise from the
  ``ISSUE_BODY`` or ``PR_BODY`` env var (whichever matches ``--kind``).
* Strip HTML comments before parsing (delegating to
  ``issue_link.strip_html_comments`` so the regex stays single-sourced).
* Extract every ``## Heading`` and ``### Heading`` line; lower-level
  headings are ignored to keep PR template H2 and Issue Forms H3
  rendering both passing.
* Require a fixed list of section headings per kind. For issues a
  tracking-shaped body (presence of ``Initial child issues``) swaps to
  the tracking-template required set; otherwise the common baseline
  shared by feat/fix/refactor/docs/chore/generic forms applies.
* Skip trusted bot authors (see ``_trusted_bots._TRUSTED_BOT_LOGINS``).
* Skip events whose ``--created-at`` predates ``--cutoff`` so the
  back-catalog is not retro-failed when the gate lands.
* Exit 0 when every required section is present (or when a skip
  applies); exit 1 otherwise. ``::error::`` annotations surface
  individual missing sections in the GitHub Actions UI.

Tested by ``tests/test_body_policy.py``. Refs #205.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import os
from pathlib import Path
import re
import sys

from _trusted_bots import _TRUSTED_BOT_LOGINS
from issue_link import strip_html_comments

_HEADING_RE = re.compile(r"^(#{2,3})[ \t]+(.+?)[ \t]*$", re.MULTILINE)
_TRAILING_COLON_RE = re.compile(r":+\s*$")
_TRACKING_MARKER = "Initial child issues"

_PR_REQUIRED: tuple[str, ...] = (
    "Facts",
    "Assumptions",
    "Risk & blast radius",
    "Rollback",
    "Verification",
    "Checklist",
)
_ISSUE_COMMON_REQUIRED: tuple[str, ...] = (
    "Scope",
    "Facts",
    "Proposed work",
    "Verification",
    "Acceptance criteria",
)
_ISSUE_TRACKING_REQUIRED: tuple[str, ...] = (
    "Scope",
    "Facts",
    "Initial child issues",
    "Completion criteria",
)


def extract_headings(body: str) -> list[tuple[int, str]]:
    """Return ``(level, text)`` tuples for every H2/H3 heading in *body*.

    HTML-commented headings are not returned. Trailing whitespace is
    stripped from the heading text; trailing colons are removed so that
    ``## Scope:`` and ``## Scope`` match the same required key.
    """
    cleaned = strip_html_comments(body.replace("\r", ""))
    out: list[tuple[int, str]] = []
    for match in _HEADING_RE.finditer(cleaned):
        level = len(match.group(1))
        text = _TRAILING_COLON_RE.sub("", match.group(2)).strip()
        if text:
            out.append((level, text))
    return out


def required_sections(kind: str, *, body: str) -> tuple[str, ...]:
    """Return the section list to enforce for *kind* and *body*."""
    if kind == "pull_request":
        return _PR_REQUIRED
    if kind == "issue":
        cleaned = strip_html_comments(body.replace("\r", ""))
        if _TRACKING_MARKER.lower() in cleaned.lower():
            return _ISSUE_TRACKING_REQUIRED
        return _ISSUE_COMMON_REQUIRED
    raise ValueError(f"unsupported body kind: {kind!r}")


def missing_sections(
    required: tuple[str, ...] | list[str],
    headings: list[tuple[int, str]],
) -> list[str]:
    """Return required entries not present in *headings* (case-sensitive)."""
    present = {text for _, text in headings}
    return [name for name in required if name not in present]


def _parse_iso(value: str) -> datetime | None:
    if not value:
        return None
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def is_within_gate_window(created_at: str, cutoff: str) -> bool:
    """Return True when *created_at* is at or after *cutoff*.

    Empty or unparseable inputs default to True (enforce). A parseable
    *created_at* that strictly precedes a parseable *cutoff* returns
    False so the caller can short-circuit with a skip message.
    """
    created = _parse_iso(created_at)
    cut = _parse_iso(cutoff)
    if created is None or cut is None:
        return True
    return created >= cut


def _verify(
    kind: str,
    body: str,
    *,
    author: str | None = None,
    created_at: str = "",
    cutoff: str = "",
) -> int:
    if author is not None and author in _TRUSTED_BOT_LOGINS:
        print(f"skipped: trusted bot author ({author})")
        return 0

    if created_at and cutoff and not is_within_gate_window(created_at, cutoff):
        print(
            f"skipped: {kind} created at {created_at} predates gate cutoff "
            f"{cutoff}."
        )
        return 0

    required = required_sections(kind, body=body)
    headings = extract_headings(body)
    missing = missing_sections(required, headings)

    if missing:
        for name in missing:
            print(
                f"::error::{kind} body is missing required section: "
                f"## {name} (or ### {name})."
            )
        return 1

    print(f"OK: {kind} body contains all required sections.")
    return 0


def _resolve_body(args: argparse.Namespace) -> str:
    if args.body_file is not None:
        return Path(args.body_file).read_text(encoding="utf-8")
    env_name = "PR_BODY" if args.kind == "pull_request" else "ISSUE_BODY"
    return os.environ.get(env_name, "")


def _resolve_author(args: argparse.Namespace) -> str | None:
    if args.author is not None:
        return args.author or None
    env_name = "PR_AUTHOR" if args.kind == "pull_request" else "ISSUE_AUTHOR"
    return os.environ.get(env_name) or None


def _resolve_created_at(args: argparse.Namespace) -> str:
    if args.created_at is not None:
        return args.created_at
    env_name = (
        "PR_CREATED_AT" if args.kind == "pull_request" else "ISSUE_CREATED_AT"
    )
    return os.environ.get(env_name, "")


def _resolve_cutoff(args: argparse.Namespace) -> str:
    if args.cutoff is not None:
        return args.cutoff
    return os.environ.get("BODY_POLICY_CUTOFF", "")


def _cmd_verify(args: argparse.Namespace) -> int:
    body = _resolve_body(args)
    author = _resolve_author(args)
    created_at = _resolve_created_at(args)
    cutoff = _resolve_cutoff(args)
    return _verify(
        args.kind,
        body,
        author=author,
        created_at=created_at,
        cutoff=cutoff,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Verify a body contains its template's required H2/H3 sections.",
    )
    p_verify.add_argument(
        "--kind",
        choices=("issue", "pull_request"),
        required=True,
        help="GitHub event object kind being validated.",
    )
    p_verify.add_argument(
        "--body-file",
        help=(
            "Path to a file containing the body. Falls back to ISSUE_BODY or "
            "PR_BODY (per --kind) when omitted."
        ),
    )
    p_verify.add_argument(
        "--author",
        help=(
            "Author login. When the login is in the trusted-bot allowlist the "
            "check is skipped. Falls back to ISSUE_AUTHOR or PR_AUTHOR when "
            "omitted."
        ),
    )
    p_verify.add_argument(
        "--created-at",
        help=(
            "ISO-8601 creation timestamp of the issue/PR. Compared against "
            "--cutoff to keep the back-catalog exempt. Falls back to "
            "ISSUE_CREATED_AT or PR_CREATED_AT when omitted."
        ),
    )
    p_verify.add_argument(
        "--cutoff",
        help=(
            "ISO-8601 cutoff. Bodies created strictly before this moment are "
            "skipped. Falls back to BODY_POLICY_CUTOFF when omitted."
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
