#!/usr/bin/env python3
"""Fail before push when the test-merge of HEAD with the live base overflows
the ``docs/INDEX.md`` navigation budget.

Refs #2012. The working-tree budget gate
(``scan_docs_inventory.verify_index_budget``) measures the branch's own
``docs/INDEX.md`` only. When an independent docs PR adds an INDEX row to the base
branch concurrently, each side can stay under ``MAX_INDEX_BYTES`` while their
additive merge result crosses it; the overflow then surfaces only in the
merge-commit CI run (the PR #2007 class), never in branch preflight. Both
``origin/main`` (40109 B) and the PR branch (40622 B) were under the 40960-byte
budget alone, but their merge was 41122 B.

This gate brings that measurement forward: it fetches the live base, computes the
test-merge tree of HEAD with it WITHOUT touching the working tree
(``git merge-tree --write-tree``), and reads the merged ``docs/INDEX.md`` byte
size straight from that tree. Over budget fails here, at branch preflight, instead
of at merge time.

The budget constant is imported from :mod:`scan_docs_inventory` so
``MAX_INDEX_BYTES`` stays single-sourced: this gate never bumps it (D3 forbids a
bump; the per-lane split tracked in #2005 is the remediation).

Contract:
    Input: the local git repository (``--head-ref``, default ``HEAD``), the live
        base branch fetched from ``--remote``/``--base-branch`` (or a local
        ``--base-ref`` with ``--skip-fetch``), and
        ``scan_docs_inventory.MAX_INDEX_BYTES``.
    Output: exit 0 when the merged ``docs/INDEX.md`` is within budget, is absent
        from the merge result, or the merge conflicts so the result cannot be
        measured (the base-staleness failure is owned by
        ``preflight_branch_base``); exit 1 when it exceeds the budget or git
        fails. Diagnostics are ``::error::`` / ``::warning::`` lines on stderr.
    Side effects: a ``git fetch`` of the base branch (network) unless
        ``--skip-fetch``. No working-tree or index mutation;
        ``merge-tree --write-tree`` writes only loose objects.

Tested by ``tests/test_preflight_merge_index_budget.py``.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from _git import run_git as _run_git
from scan_docs_inventory import INDEX_PATH, MAX_INDEX_BYTES

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class MergeBudgetResult:
    """Outcome of measuring the merged ``docs/INDEX.md`` against the budget."""

    status: str  # "pass" | "fail" | "conflict"
    detail: str
    size: int | None = None


def run_git(repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
    """Run git with captured output under *repo*."""
    return _run_git(args, cwd=repo)


def fetch_base(repo: Path, *, remote: str, base_branch: str) -> str:
    """Fetch the live base branch and return the ref that names it."""
    completed = run_git(repo, ["fetch", "--quiet", remote, base_branch])
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout).strip()
        raise RuntimeError(f"git fetch {remote} {base_branch} failed: {detail}")
    return "FETCH_HEAD"


def evaluate(
    repo: Path,
    *,
    base_ref: str,
    head_ref: str = "HEAD",
    index_path: Path = INDEX_PATH,
    max_bytes: int | None = None,
) -> MergeBudgetResult:
    """Measure ``index_path`` in the test-merge of *head_ref* with *base_ref*.

    Uses ``git merge-tree --write-tree`` to produce the merged tree without
    touching the working tree or index, then ``git cat-file -s`` to read the
    merged blob size. A conflicting merge cannot be measured faithfully (the tree
    carries conflict stages), so it returns ``conflict`` and defers to the
    base-freshness gate rather than reporting a false budget number. An index
    absent from the merge result is a pass (nothing to budget), mirroring
    ``scan_docs_inventory.verify_index_budget`` on a missing INDEX.
    """
    if max_bytes is None:
        max_bytes = MAX_INDEX_BYTES
    merge = run_git(repo, ["merge-tree", "--write-tree", base_ref, head_ref])
    if merge.returncode not in (0, 1):
        detail = (merge.stderr or merge.stdout).strip()
        raise RuntimeError(f"git merge-tree {base_ref} {head_ref} failed (rc={merge.returncode}): {detail}")

    first_line = merge.stdout.splitlines()[0].strip() if merge.stdout.strip() else ""
    if not first_line:
        raise RuntimeError("git merge-tree produced no tree object id")

    if merge.returncode == 1:
        return MergeBudgetResult(
            status="conflict",
            detail=(
                f"HEAD conflicts with base {base_ref}; cannot measure merged "
                f"{index_path.as_posix()} (resolve base first, see preflight_branch_base)"
            ),
        )

    tree = first_line
    size_proc = run_git(repo, ["cat-file", "-s", f"{tree}:{index_path.as_posix()}"])
    if size_proc.returncode != 0:
        return MergeBudgetResult(
            status="pass",
            detail=f"{index_path.as_posix()} absent from merge result; nothing to budget",
        )

    size = int(size_proc.stdout.strip())
    if size > max_bytes:
        return MergeBudgetResult(
            status="fail",
            detail=(
                f"merged {index_path.as_posix()} is {size} bytes when HEAD is "
                f"test-merged with base {base_ref}, over the {max_bytes}-byte "
                "navigation budget"
            ),
            size=size,
        )
    return MergeBudgetResult(
        status="pass",
        detail=f"merged {index_path.as_posix()} is {size} bytes (<= {max_bytes}) against base {base_ref}",
        size=size,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser(
        "verify",
        help="Check the merged docs/INDEX.md against the navigation budget.",
    )
    verify.add_argument("--repo-root", default=str(REPO_ROOT), help="Repository root to check.")
    verify.add_argument("--remote", default="origin", help="Remote that owns the base branch.")
    verify.add_argument("--base-branch", default="main", help="Base branch name on the remote.")
    verify.add_argument("--head-ref", default="HEAD", help="Branch tip to test-merge against the base.")
    verify.add_argument("--base-ref", help="Local ref to use as base when --skip-fetch is set.")
    verify.add_argument("--skip-fetch", action="store_true", help="Use --base-ref without fetching.")
    return parser


def cmd_verify(args: argparse.Namespace) -> int:
    repo = Path(args.repo_root)
    try:
        base_ref = args.base_ref
        if not args.skip_fetch:
            base_ref = fetch_base(repo, remote=args.remote, base_branch=args.base_branch)
        if not base_ref:
            base_ref = f"{args.remote}/{args.base_branch}"
        result = evaluate(repo, base_ref=base_ref, head_ref=args.head_ref)
    except RuntimeError as exc:
        print(f"::error::merge-time INDEX budget preflight failed: {exc}", file=sys.stderr)
        return 1

    if result.status == "pass":
        print(f"OK: {result.detail}")
        return 0
    if result.status == "conflict":
        print(f"::warning::{result.detail}", file=sys.stderr)
        return 0

    print(
        f"::error file={INDEX_PATH.as_posix()}::{result.detail}; split docs/INDEX.md "
        "into per-lane sub-indexes (docs/standards/documentation-quality.md D3) "
        "rather than raising the budget",
        file=sys.stderr,
    )
    return 1


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "verify":
        return cmd_verify(args)
    raise AssertionError(f"unknown command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
