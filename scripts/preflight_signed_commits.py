#!/usr/bin/env python3
"""Fail the push when an unsigned commit is in the branch range (Option A).

Refs #1959. The pre-push preflight counterpart to the server-side
``required_signatures`` ruleset: it surfaces an unsigned commit *before* the
push leaves the working tree instead of at merge time. ``.githooks/pre-push``
runs ``scripts/preflight_all.py``, which runs this gate (registered in
``scripts/preflight_steps.py``) alongside the other cheap static checks, so the
macOS / codex-desktop broken-signing scenario (PRs #1744 / #1766 / #1767) is
caught locally rather than blocking the merge after a review loop has started.

Range under inspection
----------------------
The branch's own commits: ``<base>..HEAD`` where ``base`` is the first of
``origin/main`` then ``main`` that resolves. That mirrors the set a push of the
current branch publishes without needing the pre-push stdin refspec (a preflight
step has no access to it). When no base ref resolves (a detached or
freshly-initialised repo), the gate falls back to inspecting only ``HEAD`` and
says so, so it still does something rather than silently passing.

Signature rule lives in ``_commit_signatures``: only git's ``%G?`` code ``N``
(no signature present) is unsigned; ``E`` / ``U`` (signed but unverifiable
locally) are NOT flagged, so a contributor without the signer's public key does
not trip on someone else's signed commit. A deliberately unsigned commit can
carry the ``unsigned-ack`` marker in its message to opt in.

Exit codes:
* ``0``; every inspected commit is signed (or acked), or the range is empty.
* ``1``; at least one inspected commit is unsigned, or git failed (fail loud
  per CLAUDE.md section 4; a verification gate that cannot read the range must
  not pass silently).

Tested by ``tests/test_preflight_signed_commits.py``. Refs #1959.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from _commit_signatures import CommitSignature, list_signatures, resolve_base, select_unsigned

REPO_ROOT = Path(__file__).resolve().parent.parent

# Base refs tried in order to bound the range to the branch's own commits.
_BASE_CANDIDATES = ("origin/main", "main")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="Fail when an unsigned commit is in the branch range.")
    verify.add_argument("--repo-root", default=str(REPO_ROOT), help="Repository root to inspect.")
    return parser


def _print_failure(unsigned: list[CommitSignature], *, range_label: str) -> None:
    print(
        f"::error::Unsigned commit(s) in {range_label}; this repository requires "
        "signed commits (the main-protection ruleset enforces required_signatures, "
        "so an unsigned commit blocks the merge).",
        file=sys.stderr,
    )
    for commit in unsigned:
        print(f"  {commit.sha[:12]} {commit.subject}", file=sys.stderr)
    print(
        "repair: fix your signing setup, then re-sign the range, e.g.\n"
        "  git rebase --exec 'git commit --amend --no-edit -S' "
        f"{_BASE_CANDIDATES[0]}\n"
        "  (verify your config first: git config commit.gpgsign should be true "
        "and user.signingkey / gpg.format must resolve a working key)\n"
        "If an unsigned commit is genuinely intended and reviewed, add an "
        "'unsigned-ack' line to its message to opt in.",
        file=sys.stderr,
    )


def cmd_verify(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root)
    base = resolve_base(repo, _BASE_CANDIDATES)
    if base is not None:
        rev_args = [f"{base}..HEAD"]
        range_label = f"{base}..HEAD"
    else:
        # No base ref to diff against (detached / fresh repo). Inspect HEAD
        # alone so the gate still checks the tip rather than passing silently.
        rev_args = ["--max-count=1", "HEAD"]
        range_label = "HEAD"
        print(
            "note: no base ref (origin/main, main) resolved; inspecting HEAD only.",
            file=sys.stderr,
        )

    try:
        records = list_signatures(repo, rev_args)
    except RuntimeError as exc:
        print(f"::error::signed-commits preflight failed: {exc}", file=sys.stderr)
        return 1

    unsigned = select_unsigned(records)
    if unsigned:
        _print_failure(unsigned, range_label=range_label)
        return 1

    print(f"OK: all commits in {range_label} are signed ({len(records)} inspected)")
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "verify":
        return cmd_verify(args)
    raise AssertionError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
