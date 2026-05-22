#!/usr/bin/env python3
"""Validate issue and PR titles before they enter repository metadata.

The workflow ``.github/workflows/verify-title-policy.yml`` calls this
module for issue and pull request title checks. Title text is header-level
metadata: it appears in notifications, project lists, triage queues, and
agent summaries before body context is inspected. Keep it ASCII-only so
zero-width marks, RTL controls, emoji, Japanese text, and homoglyphs are
rejected at the boundary.

Tracked by #155.
"""

from __future__ import annotations

import argparse
import os
import sys

_DEFAULT_MAX_FINDINGS = 10


def is_ascii_title(title: str) -> bool:
    """Return True if *title* contains only ASCII code points."""
    return title.isascii()


def describe_non_ascii(title: str, limit: int = _DEFAULT_MAX_FINDINGS) -> list[str]:
    """Return human-readable descriptions of non-ASCII code points."""
    findings: list[str] = []
    for index, char in enumerate(title):
        if char.isascii():
            continue
        findings.append(f"index {index}: U+{ord(char):04X}")
        if len(findings) >= limit:
            break
    return findings


def verify_title(title: str, *, kind: str) -> int:
    """Print a GitHub Actions annotation and return a process exit code."""
    if is_ascii_title(title):
        print(f"OK: {kind} title is ASCII-only.")
        return 0

    details = ", ".join(describe_non_ascii(title))
    if details:
        details = f" Non-ASCII code points: {details}."
    print(
        f"::error::{kind} title must be ASCII-only for prompt-injection "
        f"defense.{details}"
    )
    return 1


def _cmd_verify(args: argparse.Namespace) -> int:
    title = args.title
    if title is None:
        title = os.environ.get("TITLE", "")
    return verify_title(title, kind=args.kind)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Verify a title is ASCII-only.",
    )
    p_verify.add_argument(
        "--kind",
        choices=("issue", "pull_request"),
        required=True,
        help="GitHub event object kind being validated.",
    )
    p_verify.add_argument(
        "--title",
        help="Title to validate. Defaults to the TITLE environment variable.",
    )
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
