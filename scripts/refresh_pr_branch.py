#!/usr/bin/env python3
"""Deterministically bring a behind, conflict-free PR branch up to date.

A feature branch that falls behind its base (a sibling PR merged into
``main``) becomes ``mergeable_state=behind`` and cannot merge under the
``strict_required_status_checks_policy`` ruleset. The two obvious recoveries
are both blocked here:

- rebase + force-push is denied by the ``non_fast_forward`` ruleset
  (``all-branches.json``, ``bypass_actors: []``); and
- ``mcp__github__update_pull_request_branch`` is denied by
  ``scripts/gate_update_pr_branch.py`` (it does a server-side merge).

This helper implements the sanctioned deterministic path for the
*behind, conflict-free* case: it merges the latest base into the branch
locally and pushes that merge as a plain fast-forward of the branch ref
(no force-push, no update-branch API). The branch's final squash-merge
flattens the extra merge commit, so the clean-linear-history guarantee is
preserved at the point that matters. When the merge would conflict it makes
no change and points at the replacement-branch runbook instead.

See ``docs/runbooks/refresh-behind-pr.md``. Refs #1361 (R2).

Exit codes:
  0  branch already up to date, or merged (and pushed when --push) cleanly.
  2  the merge would conflict -- use the replacement-branch runbook.
  3  precondition failed (dirty worktree, on base branch, git error).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _git import run_git

_CONFLICT_EXIT = 2
_PRECONDITION_EXIT = 3


def current_branch(cwd: Path | str | None = None) -> str | None:
    """Return the current branch name, or None when detached/unknown.

    Uses ``git symbolic-ref`` so a detached HEAD (which ``rev-parse
    --abbrev-ref`` reports as the literal ``HEAD``) is correctly None.
    """
    cp = run_git(["symbolic-ref", "--short", "-q", "HEAD"], cwd=cwd)
    if cp.returncode != 0:
        return None
    name = cp.stdout.strip()
    return name or None


def worktree_dirty(cwd: Path | str | None = None) -> bool:
    """Return True when the worktree has staged or unstaged changes."""
    cp = run_git(["status", "--porcelain"], cwd=cwd)
    return bool(cp.stdout.strip())


def behind_count(remote: str, base: str, cwd: Path | str | None = None) -> int:
    """Return how many commits ``<remote>/<base>`` is ahead of HEAD.

    Returns -1 when the count cannot be computed (e.g. the ref is missing).
    """
    ref = f"{remote}/{base}"
    cp = run_git(["rev-list", "--count", f"HEAD..{ref}"], cwd=cwd)
    if cp.returncode != 0:
        return -1
    text = cp.stdout.strip()
    return int(text) if text.isdigit() else -1


def merge_would_conflict(remote: str, base: str, cwd: Path | str | None = None) -> bool | None:
    """Return True/False whether merging ``<remote>/<base>`` conflicts.

    Uses ``git merge-tree --write-tree`` (git >= 2.38), which exits 0 for a
    clean merge and 1 for conflicts without touching the worktree. Returns
    None on any other exit code (the caller treats that as an error).
    """
    ref = f"{remote}/{base}"
    cp = run_git(["merge-tree", "--write-tree", "HEAD", ref], cwd=cwd)
    if cp.returncode == 0:
        return False
    if cp.returncode == 1:
        return True
    return None


def refresh(
    *,
    base: str = "main",
    remote: str = "origin",
    cwd: Path | str | None = None,
    do_fetch: bool = True,
    do_push: bool = False,
    dry_run: bool = False,
) -> tuple[int, str]:
    """Bring the current branch up to date with ``<remote>/<base>``.

    Returns ``(exit_code, message)``. See the module docstring for the exit
    code contract. Never force-pushes and never calls update-branch.
    """
    branch = current_branch(cwd=cwd)
    if branch is None:
        return _PRECONDITION_EXIT, "Cannot refresh: HEAD is detached or branch is unknown."
    if branch == base:
        return _PRECONDITION_EXIT, f"Cannot refresh: already on base branch '{base}'."
    if worktree_dirty(cwd=cwd):
        return _PRECONDITION_EXIT, (
            "Cannot refresh: worktree has uncommitted changes. Commit or stash them first."
        )

    if do_fetch:
        cp = run_git(["fetch", remote, base], cwd=cwd)
        if cp.returncode != 0:
            return _PRECONDITION_EXIT, (
                f"Cannot refresh: 'git fetch {remote} {base}' failed: {cp.stderr.strip()}"
            )

    count = behind_count(remote, base, cwd=cwd)
    if count < 0:
        return _PRECONDITION_EXIT, (
            f"Cannot refresh: could not compute commits behind '{remote}/{base}' "
            f"(is the ref fetched?)."
        )
    if count == 0:
        return 0, f"Branch '{branch}' is already up to date with '{remote}/{base}'."

    conflict = merge_would_conflict(remote, base, cwd=cwd)
    if conflict is None:
        return _PRECONDITION_EXIT, (
            "Cannot refresh: 'git merge-tree' could not evaluate the merge."
        )
    if conflict:
        return _CONFLICT_EXIT, (
            f"Branch '{branch}' is behind '{remote}/{base}' by {count} commit(s) and "
            f"the merge CONFLICTS. Do not merge. Use the replacement-branch path: "
            f"docs/runbooks/update-pr-branch-recovery.md"
        )

    if dry_run:
        push_note = " then 'git push'" if do_push else ""
        return 0, (
            f"[dry-run] Branch '{branch}' is behind '{remote}/{base}' by {count} "
            f"commit(s), conflict-free. Would run 'git merge --no-edit {remote}/{base}'"
            f"{push_note}."
        )

    cp = run_git(["merge", "--no-edit", f"{remote}/{base}"], cwd=cwd)
    if cp.returncode != 0:
        return _PRECONDITION_EXIT, (
            f"Cannot refresh: 'git merge --no-edit {remote}/{base}' failed unexpectedly "
            f"after a clean merge-tree probe: {cp.stderr.strip()}"
        )

    if do_push:
        push = run_git(["push"], cwd=cwd)
        if push.returncode != 0:
            return _PRECONDITION_EXIT, (
                f"Merged '{remote}/{base}' into '{branch}' but 'git push' failed "
                f"(NOT retried with --force; that is blocked by the non_fast_forward "
                f"ruleset): {push.stderr.strip()}"
            )
        return 0, (
            f"Merged '{remote}/{base}' into '{branch}' ({count} commit(s)) and pushed. "
            f"The branch is now up to date; the squash-merge will flatten the merge commit."
        )

    return 0, (
        f"Merged '{remote}/{base}' into '{branch}' ({count} commit(s)). Run 'git push' "
        f"to update the PR (plain push -- do NOT force-push)."
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="main", help="base branch (default: main)")
    parser.add_argument("--remote", default="origin", help="remote name (default: origin)")
    parser.add_argument("--push", action="store_true", help="git push after a clean merge")
    parser.add_argument("--no-fetch", action="store_true", help="skip 'git fetch'")
    parser.add_argument("--dry-run", action="store_true", help="report actions without merging")
    args = parser.parse_args(argv)

    code, message = refresh(
        base=args.base,
        remote=args.remote,
        do_fetch=not args.no_fetch,
        do_push=args.push,
        dry_run=args.dry_run,
    )
    stream = sys.stdout if code == 0 else sys.stderr
    print(message, file=stream)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
