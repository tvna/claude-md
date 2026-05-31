#!/usr/bin/env python3
"""Single-command local PR body validator.

Combines the checks scattered across individual PreToolUse hooks into one
command so agents can validate a candidate PR body **before** creating the PR
via MCP:

* Required H2/H3 sections (``scripts/body_policy.py`` baseline gate)
* Verification command/result pairs (post-2026-05-26 shape gate)
* Checklist subsections: Bootstrap, After-merge, Post-merge
* Agent attribution footer
* ASCII-only content (client-side mirror of ``scripts/scan_non_ascii.py``)
* Issue reference - ``Closes``/``Fixes``/``Resolves``/``Refs #N``
  (optional; enabled by ``--issue``)

Usage::

    python3 scripts/preflight_pr_body.py verify --body-file body.md
    python3 scripts/preflight_pr_body.py verify --body-file body.md --issue 938

Exit codes:
    0  All checks pass.
    1  One or more checks fail (errors printed to stdout as ``::error::`` lines).

All checks import directly from :mod:`body_policy`, :mod:`scan_non_ascii`,
and :mod:`_ref_classifier` so this tool and the server-side CI gate cannot
drift. Refs #938.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from _ref_classifier import classify_refs, strip_html_comments
from body_policy import (
    extract_headings,
    missing_sections,
    required_sections,
    strip_devin_review_badge,
    verify_pr_agent_attribution_footer,
    verify_pr_checklist_subsections,
    verify_pr_verification_pairs,
)
from scan_non_ascii import detect_non_ascii, has_ack_marker


def evaluate(body: str, *, issue: int | None = None) -> list[str]:
    """Return ``::error::`` strings for every policy violation; empty list means OK.

    Checks are ordered from cheapest to most specific so the list is
    readable top-to-bottom (structure first, content second).
    """
    # Strip bot-injected badge blocks before validation so that
    # Devin Review badge HTML does not interfere with footer detection
    # or trigger false-positive ASCII violations.  Refs #994.
    body = strip_devin_review_badge(body)

    errors: list[str] = []

    # 1. Required H2/H3 sections.
    required = required_sections("pull_request", body=body)
    headings = extract_headings(body)
    for name in missing_sections(required, headings):
        errors.append(
            f"::error::PR body is missing required section: ## {name} "
            f"(body_policy baseline gate)."
        )

    # 2. Verification command/result pairs (post-2026-05-26 shape gate).
    errors.extend(verify_pr_verification_pairs(body))

    # 3. Checklist H3 subsections (post-2026-05-26 shape gate).
    errors.extend(verify_pr_checklist_subsections(body))

    # 4. Agent attribution footer (post-2026-05-26 shape gate).
    errors.extend(verify_pr_agent_attribution_footer(body))

    # 5. ASCII-only content.  Honor the operator ack marker so bodies
    #    with <!-- non-ascii-ack --> are not false-positively flagged.
    if not has_ack_marker(body) and detect_non_ascii(body):
        errors.append(
            "::error::PR body contains non-ASCII characters. "
            "GitHub posts must be ASCII-only (preflight_non_ascii.py). "
            "Either translate to English or append <!-- non-ascii-ack --> to the body."
        )

    # 6. Issue reference (only when caller requests it).
    if issue is not None:
        cleaned = strip_html_comments(body)
        refs = classify_refs(cleaned)
        if not refs:
            errors.append(
                f"::error::PR body has no issue reference "
                f"(Closes/Fixes/Resolves/Refs #N). "
                f"Add a `Closes #{issue}` line in the Related Issue section."
            )
        elif not any(n == issue for _, n in refs):
            found = ", ".join(f"#{n}" for _, n in refs)
            errors.append(
                f"::error::PR body references {found} but not #{issue}. "
                f"Add a `Closes #{issue}` (or `Refs #{issue}`) line."
            )

    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Validate a PR body file against all local policy checks.",
    )
    p_verify.add_argument(
        "--body-file",
        required=True,
        help="Path to a file containing the candidate PR body.",
    )
    p_verify.add_argument(
        "--issue",
        type=int,
        default=None,
        help=(
            "Expected issue number. When given, the body must contain a "
            "Closes/Fixes/Resolves/Refs reference to this number."
        ),
    )

    args = parser.parse_args(argv)

    body = Path(args.body_file).read_text(encoding="utf-8")
    errors = evaluate(body, issue=args.issue)

    for msg in errors:
        print(msg)

    if not errors:
        print("OK: PR body passes all local preflight checks.")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
