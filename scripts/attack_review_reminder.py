#!/usr/bin/env python3
"""Assemble the quarterly ATT&CK coverage review reminder comment.

Replaces the inline awk/grep/cat logic in
``.github/workflows/attack-coverage-review-reminder.yml``: it extracts the
canonical review-comment template block from the cadence runbook, verifies the
expected number of ``### `` H3 sections, prepends a dated header, writes the
assembled comment to a file, and appends a preview to the GitHub step summary.

Usage::

    python3 scripts/attack_review_reminder.py assemble \\
        --runbook docs/runbooks/attack-coverage-review-cadence.md \\
        --out /tmp/review-comment.md \\
        --summary-file "$GITHUB_STEP_SUMMARY" \\
        --repo owner/repo \\
        --run-url https://github.com/owner/repo/actions/runs/123

Exit codes:
    0  Comment assembled and written.
    1  Template markers missing, empty block, or unexpected H3 count.
    2  Usage error.

Refs #184.
"""

from __future__ import annotations

import argparse
import sys
from datetime import UTC, datetime
from pathlib import Path

BEGIN_MARKER = "<!-- attack-coverage-review-template:begin -->"
END_MARKER = "<!-- attack-coverage-review-template:end -->"
EXPECTED_H3 = 7


def extract_template_block(
    runbook_text: str,
    *,
    begin_marker: str = BEGIN_MARKER,
    end_marker: str = END_MARKER,
) -> str:
    """Return the marker-delimited template block, including both marker lines.

    Mirrors the workflow's ``awk '/begin/,/end/'`` range expression: capture
    starts on the line containing ``begin_marker`` and ends on the first
    subsequent line containing ``end_marker`` (both inclusive).

    Raises ValueError when the begin marker is absent or the end marker is
    absent after the begin marker (mirrors the workflow's empty-extraction
    guard: missing markers yield no template).
    """
    lines = runbook_text.splitlines()
    captured: list[str] = []
    capturing = False
    closed = False
    for line in lines:
        if not capturing:
            if begin_marker in line:
                capturing = True
                captured.append(line)
            continue
        captured.append(line)
        if end_marker in line:
            closed = True
            break

    if not capturing:
        raise ValueError(f"begin marker not found: {begin_marker!r}")
    if not closed:
        raise ValueError(f"end marker not found after begin marker: {end_marker!r}")
    return "\n".join(captured) + "\n"


def count_h3(template_text: str) -> int:
    """Count lines that begin a level-3 markdown heading (``### `` at line start)."""
    return sum(1 for line in template_text.splitlines() if line.startswith("### "))


def build_comment(
    *,
    template_text: str,
    run_date: str,
    repo: str,
    runbook_path: str,
    run_url: str,
) -> str:
    """Return the assembled review-reminder comment markdown."""
    header = "\n".join(
        [
            f"## ATT&CK coverage review reminder; {run_date}",
            "",
            "Quarterly review reminder for the MITRE ATT&CK coverage tracker.",
            f"Runbook: [`{runbook_path}`](https://github.com/{repo}/blob/main/{runbook_path}).",
            f"Workflow run: {run_url}.",
            "Refs #184.",
            "",
            "Edit this comment in place to fill in each section below.",
            "",
        ]
    )
    return f"{header}\n{template_text}"


def _append_summary(summary_file: str, comment: str) -> None:
    """Append a fenced preview of the assembled comment to the step summary file."""
    block = "\n".join(
        [
            "### Assembled review reminder comment",
            "",
            "```markdown",
            comment.rstrip("\n"),
            "```",
            "",
        ]
    )
    with Path(summary_file).open("a", encoding="utf-8") as fh:
        fh.write(block)


def _cmd_assemble(args: argparse.Namespace) -> int:
    runbook_path = args.runbook
    try:
        runbook_text = Path(runbook_path).read_text(encoding="utf-8")
    except OSError as exc:
        print(f"::error::Could not read runbook {runbook_path}: {exc}", file=sys.stderr)
        return 1

    try:
        template_text = extract_template_block(runbook_text)
    except ValueError as exc:
        print(
            f"::error::Could not extract template block from {runbook_path}: {exc}",
            file=sys.stderr,
        )
        return 1

    h3 = count_h3(template_text)
    if h3 != args.expected_h3:
        print(
            f"::error::Extracted template has {h3} H3 sections; expected {args.expected_h3}. Refusing to post.",
            file=sys.stderr,
        )
        return 1

    run_date = args.run_date or datetime.now(UTC).strftime("%Y-%m-%d")
    comment = build_comment(
        template_text=template_text,
        run_date=run_date,
        repo=args.repo,
        runbook_path=runbook_path,
        run_url=args.run_url,
    )

    Path(args.out).write_text(comment, encoding="utf-8")
    if args.summary_file:
        _append_summary(args.summary_file, comment)
    print(f"Assembled review reminder comment -> {args.out}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Assemble the ATT&CK coverage review reminder comment.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    assemble_p = sub.add_parser("assemble", help="Extract the template and assemble the dated comment")
    assemble_p.add_argument("--runbook", required=True, help="Path to the cadence runbook")
    assemble_p.add_argument("--out", required=True, help="Output path for the assembled comment")
    assemble_p.add_argument("--summary-file", default=None, dest="summary_file", help="GITHUB_STEP_SUMMARY path")
    assemble_p.add_argument("--repo", required=True, help="Repository in owner/repo format")
    assemble_p.add_argument("--run-url", required=True, dest="run_url", help="Workflow run URL")
    assemble_p.add_argument("--run-date", default=None, dest="run_date", help="UTC date (YYYY-MM-DD); defaults to today")
    assemble_p.add_argument(
        "--expected-h3",
        type=int,
        default=EXPECTED_H3,
        dest="expected_h3",
        help="Required number of H3 sections in the template",
    )

    args = parser.parse_args(argv)

    if args.cmd == "assemble":
        return _cmd_assemble(args)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
