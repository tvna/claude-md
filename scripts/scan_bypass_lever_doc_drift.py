#!/usr/bin/env python3
"""Detect drift between the pre-push hook's bypass levers and its runbook.

Refs #2152 (retrospective for PR #2134 / issue #2133). The local pre-push hook
``.githooks/pre-push`` exposes a small family of emergency-bypass environment
levers named ``PREFLIGHT_SKIP*`` (today ``PREFLIGHT_SKIP``, ``PREFLIGHT_SKIP_ALL``,
``PREFLIGHT_SKIP_STEPS``). The runbook ``docs/runbooks/preflight.md`` documents
that exact escape-hatch surface in its "Emergency bypass" prose. The two files
are edited independently and nothing required them to move together.

PR #2120 / PR #2134 hit exactly this drift class. Narrowing ``PREFLIGHT_SKIP=1``
to skip only ``prek`` and introducing ``PREFLIGHT_SKIP_ALL=1`` as the full
bypass changed the hook's lever surface, but the runbook kept advertising
``PREFLIGHT_SKIP=1`` as a FULL bypass and never named the new
``PREFLIGHT_SKIP_ALL`` lever. The documented escape hatch no longer matched the
code; no deterministic gate caught it, a reviewer did (fixed in commit ed187e9).

The invariant this gate enforces: **the set of ``PREFLIGHT_SKIP*`` bypass lever
names referenced in the pre-push hook must equal the set named in the runbook.**
When a lever is added, removed, or renamed in the hook without a co-update of
the runbook that names it (or vice versa), the gate fails loudly and names the
missing levers and the file to fix.

Scope is deliberately the lever *name* set only, mirroring how
``scan_doc_workflow_refs.py`` gates only the unambiguous path-form subset of
workflow references. A pure semantics change that renames no lever (a lever
keeps its name but changes meaning) is out of scope and stays a review concern;
the realistic drift class that PR #2134 hit (a lever added without its doc) is
covered with no false-positive risk, because a lever name either appears in the
runbook or it does not.

Comparison model
----------------
Both files are read as text and scanned for the ``PREFLIGHT_SKIP[A-Z_]*`` token
family with a word boundary, so ``PREFLIGHT_SKIP`` is matched as its own lever
and not as a prefix of ``PREFLIGHT_SKIP_ALL`` (an underscore is a word
character, so ``\\bPREFLIGHT_SKIP\\b`` does not match inside the longer token).
The two resulting name sets must be equal; any symmetric difference is drift.

Exit codes:
* ``0``; the hook lever set equals the runbook lever set.
* ``1``; at least one lever is named in one file but not the other.

Contract:
- Inputs: the ``verify`` subcommand; ``--hook`` (default ``.githooks/pre-push``)
  and ``--runbook`` (default ``docs/runbooks/preflight.md``). No stdin, no env
  input, no network.
- Outputs: ``::error file=<path>::`` annotations on stderr, one per drifted
  lever, naming the file to fix; an ``OK:`` line on success; exit 0 when the
  sets are equal, exit 1 otherwise.
- Failure policy: fails loud per CLAUDE.md section 4; a missing source file is
  reported and exits 1 rather than passing silently, because a vanished hook or
  runbook is itself drift the gate must surface.

Tested by ``tests/test_scan_bypass_lever_doc_drift.py`` and
``tests/test_workflow_cli_contracts.py``. Refs #2152, #2133, #2120.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
HOOK_PATH = REPO_ROOT / ".githooks" / "pre-push"
RUNBOOK_PATH = REPO_ROOT / "docs" / "runbooks" / "preflight.md"

_SCRIPT = "scan_bypass_lever_doc_drift"

# The bypass-lever environment-variable family. The trailing ``[A-Z0-9_]*`` lets
# the longest token win (``PREFLIGHT_SKIP_ALL`` over a bare ``PREFLIGHT_SKIP``)
# and includes digits so a future digit-suffixed lever such as
# ``PREFLIGHT_SKIP2`` or ``PREFLIGHT_SKIP_STEPS2`` is captured as its own token
# instead of collapsing onto the bare prefix already in the runbook (which would
# report false parity and defeat the added-lever check). The closing ``\b`` pins
# the match to a full shell-identifier token.
_LEVER_RE = re.compile(r"\bPREFLIGHT_SKIP[A-Z0-9_]*\b")


def extract_levers(text: str) -> frozenset[str]:
    """Return the set of ``PREFLIGHT_SKIP*`` lever names found in *text*."""
    return frozenset(_LEVER_RE.findall(text))


def _read(path: Path) -> str | None:
    """Return the text of *path*, or None when it cannot be read."""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def find_drift(hook_levers: frozenset[str], doc_levers: frozenset[str]) -> list[str]:
    """Return one human-readable problem per drifted lever, or [] when in parity.

    A lever in the hook but absent from the runbook is the PR #2134 class (a
    documented escape hatch left stale); the fix is to name it in the runbook. A
    lever in the runbook but absent from the hook is a removed/renamed lever that
    the docs still advertise; the fix is to update the runbook to the current
    surface.
    """
    runbook_rel = RUNBOOK_PATH.relative_to(REPO_ROOT)
    hook_rel = HOOK_PATH.relative_to(REPO_ROOT)
    problems: list[str] = []
    for lever in sorted(hook_levers - doc_levers):
        problems.append(
            f"::error file={runbook_rel}::{_SCRIPT}: the pre-push hook exposes "
            f"bypass lever {lever!r} but {runbook_rel} does not name it. A change "
            f"to the documented escape-hatch surface must co-update its runbook "
            f"(the PR #2134 drift class). Document {lever!r} in the 'Emergency "
            f"bypass' section. Refs #2152."
        )
    for lever in sorted(doc_levers - hook_levers):
        problems.append(
            f"::error file={runbook_rel}::{_SCRIPT}: {runbook_rel} documents "
            f"bypass lever {lever!r} but the pre-push hook no longer references "
            f"it. Remove the stale lever from the runbook or restore it in "
            f"{hook_rel}. Refs #2152."
        )
    return problems


def cmd_verify(args: argparse.Namespace) -> int:
    hook_path = Path(args.hook)
    runbook_path = Path(args.runbook)

    hook_text = _read(hook_path)
    if hook_text is None:
        print(
            f"::error file={hook_path}::{_SCRIPT}: cannot read pre-push hook "
            f"{hook_path!r}; the bypass-lever source of truth is missing.",
            file=sys.stderr,
        )
        return 1
    runbook_text = _read(runbook_path)
    if runbook_text is None:
        print(
            f"::error file={runbook_path}::{_SCRIPT}: cannot read runbook "
            f"{runbook_path!r}; the documented escape-hatch surface is missing.",
            file=sys.stderr,
        )
        return 1

    hook_levers = extract_levers(hook_text)
    doc_levers = extract_levers(runbook_text)

    if not hook_levers:
        # No levers in the hook is itself a surprise worth surfacing: the gate
        # exists because the hook is the lever source of truth.
        print(
            f"::warning::{_SCRIPT}: no PREFLIGHT_SKIP* lever found in "
            f"{hook_path!r}; nothing to compare.",
            file=sys.stderr,
        )

    problems = find_drift(hook_levers, doc_levers)
    for message in problems:
        print(message, file=sys.stderr)
    if problems:
        return 1
    print(
        f"OK: {_SCRIPT}: pre-push hook and runbook agree on bypass levers "
        f"({', '.join(sorted(hook_levers))})."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Detect drift between the pre-push hook's PREFLIGHT_SKIP* bypass "
            "levers and the runbook that documents them."
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    verify = sub.add_parser("verify", help="Run the bypass-lever drift check.")
    verify.add_argument(
        "--hook",
        default=str(HOOK_PATH),
        help="Path to the pre-push hook (default: %(default)s).",
    )
    verify.add_argument(
        "--runbook",
        default=str(RUNBOOK_PATH),
        help="Path to the preflight runbook (default: %(default)s).",
    )
    verify.set_defaults(func=cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
