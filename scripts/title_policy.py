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
import re

_DEFAULT_MAX_FINDINGS = 10
_CONVENTIONAL_TYPES = (
    "build",
    "chore",
    "ci",
    "docs",
    "feat",
    "fix",
    "perf",
    "refactor",
    "revert",
    "style",
    "test",
    "tracking",
)
_TYPE_PATTERN = "|".join(_CONVENTIONAL_TYPES)
_CONVENTIONAL_TITLE_RE = re.compile(rf"^(?:{_TYPE_PATTERN})(?:\([a-z0-9][a-z0-9-]*\))?: .+")
# Per #167 and #214, PR subject lines must not carry issue refs like (#NNN);
# `.github/workflows/verify-issue-link.yml` already validates `Refs #NNN` in
# the PR body, so the title is redundant when it duplicates that link.
_PR_ISSUE_REF_RE = re.compile(r"\(#\d+\)")


def is_ascii_title(title: str) -> bool:
    """Return True if *title* contains only ASCII code points."""
    return title.isascii()


def follows_naming_convention(title: str, *, kind: str) -> bool:
    """Return True if *title* follows this repo's title convention."""
    if kind in {"issue", "pull_request"}:
        return _CONVENTIONAL_TITLE_RE.fullmatch(title) is not None
    raise ValueError(f"unsupported title kind: {kind!r}")


def pr_title_has_issue_ref(title: str) -> bool:
    """Return True if *title* contains a `(#NNN)` issue-ref token."""
    return _PR_ISSUE_REF_RE.search(title) is not None


def pr_title_issue_refs(title: str) -> list[str]:
    """Return every ``(#NNN)`` token in *title* in source order.

    Empty list when *title* carries no issue-reference token. Pairs with
    :func:`pr_title_has_issue_ref` so client-side preflights can list
    the offending tokens without re-implementing the regex.
    """
    return _PR_ISSUE_REF_RE.findall(title)


def pr_title_strip_issue_refs(title: str) -> str:
    """Return *title* with every ``(#NNN)`` token removed and whitespace collapsed."""
    stripped = _PR_ISSUE_REF_RE.sub("", title)
    return re.sub(r"\s+", " ", stripped).strip()


def allowed_types_csv() -> str:
    """Return the allowed conventional-commit types as a CSV string.

    Single source for operator-facing hint text so client-side preflight
    hooks and any future error messages cannot drift from
    ``_CONVENTIONAL_TYPES``.
    """
    return ", ".join(_CONVENTIONAL_TYPES)


def naming_convention_hint(kind: str) -> str:
    """Return the operator-facing expected title shape for *kind*."""
    if kind in {"issue", "pull_request"}:
        return "`type(scope): summary`"
    raise ValueError(f"unsupported title kind: {kind!r}")


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
    fail = 0
    if not is_ascii_title(title):
        details = ", ".join(describe_non_ascii(title))
        if details:
            details = f" Non-ASCII code points: {details}."
        print(f"::error::{kind} title must be ASCII-only for prompt-injection " f"defense.{details}")
        fail = 1

    if not follows_naming_convention(title, kind=kind):
        print(f"::error::{kind} title must follow repository naming convention: " f"{naming_convention_hint(kind)}.")
        fail = 1

    if kind == "pull_request" and pr_title_has_issue_ref(title):
        print(
            "::error::pull_request title must not contain issue references "
            "like (#NNN). Put `Refs #NNN` in the PR body instead. See #167."
        )
        fail = 1

    if fail:
        return 1

    print(f"OK: {kind} title is ASCII-only and follows naming convention.")
    return 0


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
