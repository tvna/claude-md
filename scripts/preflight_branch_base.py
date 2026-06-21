#!/usr/bin/env python3
"""Fail before PR publication when the branch is behind its base branch.

Refs #745. This is the local counterpart to GitHub's
``This branch is out-of-date with the base branch`` banner. Hooks run it
before PR create/update and before push so stale-base repair happens before a
review loop or replacement PR starts.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from _git import run_git as _run_git

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class BranchBaseResult:
    """Result of checking whether HEAD contains the base ref."""

    status: str  # "pass" | "fail"
    detail: str


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


def check_base_freshness(*, repo: Path, base_ref: str) -> BranchBaseResult:
    """Return pass iff ``base_ref`` is an ancestor of ``HEAD``."""
    rev_parse = run_git(repo, ["rev-parse", "--verify", base_ref])
    if rev_parse.returncode != 0:
        detail = (rev_parse.stderr or rev_parse.stdout).strip()
        return BranchBaseResult(status="fail", detail=f"base ref {base_ref!r} is not available: {detail}")

    completed = run_git(repo, ["merge-base", "--is-ancestor", base_ref, "HEAD"])
    if completed.returncode == 0:
        return BranchBaseResult(status="pass", detail=f"HEAD contains {base_ref}")
    if completed.returncode == 1:
        return BranchBaseResult(status="fail", detail=f"HEAD does not contain {base_ref}")
    detail = (completed.stderr or completed.stdout).strip()
    return BranchBaseResult(status="fail", detail=f"merge-base check failed: {detail}")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify", help="Check that HEAD contains the latest base branch.")
    verify.add_argument("--repo-root", default=str(REPO_ROOT), help="Repository root to check.")
    verify.add_argument("--remote", default="origin", help="Remote that owns the base branch.")
    verify.add_argument("--base-branch", default="main", help="Base branch name on the remote.")
    verify.add_argument("--base-ref", help="Local ref to check when --skip-fetch is used.")
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
        result = check_base_freshness(repo=repo, base_ref=base_ref)
    except RuntimeError as exc:
        print(f"::error::branch base preflight failed: {exc}", file=sys.stderr)
        return 1

    if result.status == "pass":
        print(f"OK: branch contains base ({result.detail})")
        return 0

    print("::error::This branch is out-of-date with the base branch.", file=sys.stderr)
    print(f"reason: {result.detail}", file=sys.stderr)
    print(f"repair: git fetch {args.remote} {args.base_branch}", file=sys.stderr)
    print(
        "repair: git merge FETCH_HEAD --no-edit  "
        "# use merge, not rebase -- rebase rewrites SHAs and conflicts with "
        "force-push restrictions on already-published branches (Refs #1854)",
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
