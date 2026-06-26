#!/usr/bin/env python3
"""CI gate: require new/changed runbooks to follow docs/runbooks/TEMPLATE.md.

``docs/runbooks/TEMPLATE.md`` (tracked by #2000) defines a canonical section
skeleton every runbook should carry, in a fixed order, so operators find the
same sections in the same place. This gate enforces that skeleton.

Diff-scoped by design: only runbooks added or modified in the PR are checked,
so the existing back-catalog is grandfathered and backfilled the next time a
document is touched. This mirrors the progressive-backfill approach of
``scripts/scan_doc_graph_registration.py``.

Architecture (mirrors :mod:`scan_doc_graph_registration`): pure functions on
top (:func:`extract_h2_headings`, :func:`check_conformance`,
:func:`parse_waivers`, :func:`get_changed_runbooks`, :func:`run_gate`), a thin
subprocess boundary in :func:`get_changed_runbooks`, and a ``main()``
entrypoint at the bottom.

Contract:
- Inputs: the ``verify`` subcommand; ``--base-ref`` (default: ``BASE_REF`` env
  var, then ``origin/main``); ``--body-file`` (PR body path) or ``PR_BODY``
  env var for waivers; ``--all`` for a report-only full-tree audit.
- Conformance: every canonical section heading in :data:`REQUIRED_SECTIONS`
  must be present as an exact H2 (``## Name``) and the canonical headings that
  are present must appear in canonical relative order. Sections that do not
  apply keep their heading with a one-line reason underneath (per TEMPLATE.md),
  so the heading must still exist.
- Outputs: ``::error file=<path>::`` annotations on stderr for non-conforming
  changed runbooks; ``OK:`` line on success; ``::warning::`` for the report-only
  audit.
- Exit codes: 0 when all changed runbooks conform or are waived (and for the
  report-only ``--all`` audit); 1 when a changed runbook is non-conforming and
  not waived; 64 on an unrecognised subcommand.
- Failure policy: fails loud (exit 1) for non-conforming changed runbooks per
  CLAUDE.md section 4; fails open (exit 0) when the git diff is unavailable so
  the gate skips rather than blocks on a missing diff.

Waiver (plain text in the PR body, mirrors the doc-graph waiver form)::

    runbook-template-waiver: docs/runbooks/example.md; reason

Tested by ``tests/test_scan_runbook_template_drift.py``. Refs #2065.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path

_SCRIPT = "scan_runbook_template_drift"
_RUNBOOK_DIR = "docs/runbooks/"
_RUNBOOK_PARENT = Path("docs/runbooks")
_EXCLUDED = frozenset({"docs/runbooks/README.md", "docs/runbooks/TEMPLATE.md"})

# Canonical section headings, in TEMPLATE.md order.
REQUIRED_SECTIONS: tuple[str, ...] = (
    "Scope",
    "Why",
    "Why not",
    "Procedure",
    "Verification",
    "Pause / Resume",
    "Rollback",
    "References",
)

_H2_RE = re.compile(r"^##[ \t]+(.+?)[ \t]*$", re.MULTILINE)
# Waiver marker: optional leading whitespace, the key, whitespace, the file
# path (stops at whitespace or semicolon), optional `; reason`.
_WAIVER_RE = re.compile(
    r"^\s*runbook-template-waiver:\s*([^\s;]+)",
    re.IGNORECASE | re.MULTILINE,
)


def _strip_fenced_code_blocks(text: str) -> str:
    """Blank out fenced code blocks so their contents are not scanned for headings.

    A Markdown code fence opens and closes with a run of at least three
    backticks (```) or tildes (~~~); a closing fence must use the same
    character that opened the block. Lines such as ``## Procedure`` inside a
    fence are code samples, not document structure, so a runbook that only
    illustrates the section skeleton inside a code block must not be counted as
    conforming. This tracks the open fence character and toggles on a matching
    marker, replacing fenced lines (and the fence lines themselves) with blanks
    so line/heading offsets elsewhere are unaffected.
    """
    out: list[str] = []
    fence: str | None = None  # open fence character ('`' or '~'), or None when outside
    for line in text.splitlines():
        stripped = line.lstrip()
        if stripped[:3] in ("```", "~~~"):
            marker = stripped[0]
            if fence is None:
                fence = marker
            elif fence == marker:
                fence = None
            out.append("")  # drop the fence line itself
            continue
        out.append("" if fence is not None else line)
    return "\n".join(out)


def extract_h2_headings(text: str) -> list[str]:
    """Return the text of every H2 (``## ``) heading, in document order.

    Fenced code blocks are stripped first so a ``## ...`` line inside a code
    sample is not mistaken for a real document heading.
    """
    return [m.group(1).strip() for m in _H2_RE.finditer(_strip_fenced_code_blocks(text))]


def check_conformance(headings: list[str]) -> list[str]:
    """Return a list of problem messages; an empty list means conforming.

    Two checks:

    1. Every canonical section in :data:`REQUIRED_SECTIONS` is present as an
       exact H2 heading.
    2. The canonical headings that ARE present appear in canonical relative
       order (a subsequence of :data:`REQUIRED_SECTIONS`).
    """
    problems: list[str] = []

    for section in REQUIRED_SECTIONS:
        if section not in headings:
            problems.append(f"missing required section: '## {section}'")

    present = [h for h in headings if h in REQUIRED_SECTIONS]
    canonical_order = [s for s in REQUIRED_SECTIONS if s in present]
    if present != canonical_order:
        problems.append(
            "section order does not match TEMPLATE.md order " f"(expected {canonical_order}, found {present})"
        )

    return problems


def parse_waivers(body: str) -> frozenset[str]:
    """Return the set of waived runbook paths extracted from *body*."""
    return frozenset(m.group(1) for m in _WAIVER_RE.finditer(body))


def _is_runbook(path: str) -> bool:
    """True for a runbook .md directly under docs/runbooks/, excluding meta files."""
    p = Path(path)
    return path.startswith(_RUNBOOK_DIR) and p.parent == _RUNBOOK_PARENT and p.suffix == ".md" and path not in _EXCLUDED


def get_changed_runbooks(base_ref: str) -> list[str] | None:
    """Return runbook paths added/modified on HEAD vs *base_ref*, plus staged.

    Unions two sources so the gate fires at commit time (pre-commit hook) as
    well as in CI:

    1. ``git diff --name-only --diff-filter=ACMR <base_ref>...HEAD``; committed
       additions/modifications on the branch since *base_ref*.
    2. ``git diff --cached --name-only --diff-filter=ACMR``; staged changes not
       yet committed.

    Returns ``None`` when the first git call fails (fail-open: the gate skips
    rather than blocks when the diff is unavailable). A failure of the cached
    call is ignored.
    """
    committed = subprocess.run(  # noqa: S603 -- fixed argv, shell=False
        [  # noqa: S607
            "git",
            "diff",
            "--name-only",
            "--diff-filter=ACMR",
            f"{base_ref}...HEAD",
        ],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if committed.returncode != 0:
        return None
    names = {f.strip() for f in committed.stdout.splitlines() if f.strip()}

    cached = subprocess.run(  # noqa: S603 -- fixed argv, shell=False
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],  # noqa: S607
        capture_output=True,
        text=True,
        timeout=30,
    )
    if cached.returncode == 0:
        names |= {f.strip() for f in cached.stdout.splitlines() if f.strip()}

    return sorted(n for n in names if _is_runbook(n))


def run_gate(
    changed: list[str],
    read_text: Callable[[str], str],
    waivers: frozenset[str],
) -> bool:
    """Evaluate each changed runbook against the template skeleton.

    Returns ``True`` when the gate passes (all changed runbooks conform or are
    waived); ``False`` when at least one is non-conforming and not waived.
    """
    if not changed:
        print(f"OK: {_SCRIPT}: no changed runbooks detected.", file=sys.stderr)
        return True

    passed = True
    for path in changed:
        if path in waivers:
            print(
                f"  waived: {path!r} (waiver present in PR body)",
                file=sys.stderr,
            )
            continue
        try:
            text = read_text(path)
        except OSError as exc:
            print(
                f"::warning::{_SCRIPT}: cannot read {path!r}: {exc}",
                file=sys.stderr,
            )
            continue

        problems = check_conformance(extract_h2_headings(text))
        if problems:
            detail = "; ".join(problems)
            print(
                f"::error file={path}::{_SCRIPT}: {path!r} does not follow "
                f"docs/runbooks/TEMPLATE.md: {detail}. Fix the headings, or add "
                f"'runbook-template-waiver: {path}; reason' to the PR body. "
                f"Refs #2065.",
                file=sys.stderr,
            )
            passed = False

    if passed:
        print(f"OK: {_SCRIPT}: all changed runbooks conform.", file=sys.stderr)
    return passed


def _read_text(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def _audit_all() -> int:
    """Report-only full-tree audit: warn on every non-conforming runbook, exit 0."""
    any_problem = False
    for path in sorted(str(p) for p in _RUNBOOK_PARENT.glob("*.md")):
        if path in _EXCLUDED:
            continue
        problems = check_conformance(extract_h2_headings(_read_text(path)))
        if problems:
            any_problem = True
            print(
                f"::warning file={path}::{_SCRIPT}: {'; '.join(problems)}",
                file=sys.stderr,
            )
    if not any_problem:
        print(f"OK: {_SCRIPT}: all runbooks conform.", file=sys.stderr)
    return 0


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    # Check the subcommand before argparse so an unrecognised command returns
    # exit 64 (EX_USAGE) rather than argparse's exit 2.
    command = argv[0] if argv else None
    if command != "verify":
        print(
            f"::error::{_SCRIPT}: unknown subcommand {command!r}; " "expected 'verify'.",
            file=sys.stderr,
        )
        return 64

    parser = argparse.ArgumentParser(description="Require new/changed runbooks to follow docs/runbooks/TEMPLATE.md.")
    parser.add_argument("command", help="Must be 'verify'.")
    parser.add_argument(
        "--base-ref",
        default=os.environ.get("BASE_REF", "origin/main"),
        help="Git ref to diff HEAD against (default: BASE_REF env or origin/main).",
    )
    parser.add_argument(
        "--body-file",
        default=None,
        help="Path to a file containing the PR body (alternative to PR_BODY env var).",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Report-only audit over every runbook (always exit 0).",
    )
    args = parser.parse_args(argv)

    if args.all:
        return _audit_all()

    body = ""
    if args.body_file:
        try:
            body = Path(args.body_file).read_text(encoding="utf-8")
        except OSError as exc:
            print(
                f"::warning::{_SCRIPT}: cannot read PR body file " f"{args.body_file!r}: {exc}",
                file=sys.stderr,
            )
    else:
        body = os.environ.get("PR_BODY", "")

    waivers = parse_waivers(body)
    changed = get_changed_runbooks(args.base_ref)
    if changed is None:
        print(
            f"::warning::{_SCRIPT}: git diff failed; skipping check.",
            file=sys.stderr,
        )
        return 0

    return 0 if run_gate(changed, _read_text, waivers) else 1


if __name__ == "__main__":
    raise SystemExit(main())
