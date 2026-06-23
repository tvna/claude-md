#!/usr/bin/env python3
"""Surface a stale branch base at session start / before the first commit.

Refs #1632 (PR #1625 retrospective, Fact 3). ``preflight_branch_base.py`` runs
only at pre-push; after all the work is done; so a branch cut from an old
``main`` was discovered only when the first push failed three pre-push gates at
once, forcing a late rebase. This module shifts that detection LEFT, reusing the
existing primitives rather than re-deriving them:

* ``preflight_main_freshness`` records an ``origin/main`` observation; here it
  writes the SHA to a dedicated stamp (``.git/SESSION_BASE_FRESHNESS``) so the
  ``mcp__github__create_branch`` freshness gate's own stamp semantics are left
  untouched (no regression to that gate).
* ``preflight_branch_base.check_base_freshness`` answers "does HEAD contain a
  given base ref"; here it is applied against the recorded session-start SHA.

Three modes:

* ``session-start``; a SessionStart hook. In a remote session it fetches
  ``origin/main``, records the SHA, and; when HEAD does not yet contain that
  SHA; emits a loud ``additionalContext`` telling the operator to rebase
  BEFORE implementing. Always exits 0; never wedges a session (fail-open).

* hook mode (no subcommand, event JSON on stdin); a PreToolUse ``Bash`` hook.
  It DENIES a ``git commit`` while the branch base is stale (HEAD lacks the
  recorded session-start ``origin/main`` SHA), so the rebase happens before the
  first commit lands rather than at push. It reads only the stamp (no fetch), so
  it adds no per-commit network. After a rebase HEAD contains the SHA and
  commits proceed; genuine mid-session drift is still caught by the pre-push
  ``preflight_branch_base`` gate (defense-in-depth, CLAUDE.md Section 4).

* ``check``; print the staleness verdict and exit 0 (fresh / no stamp) or 1
  (stale). Used to reproduce Fact 3 deterministically.

Fail-open everywhere a guard cannot be evaluated (no stamp, detached HEAD,
non-remote, parse/IO error), so a hook bug never blocks legitimate work; the
pre-push gate is the backstop.

Contract:
- Inputs: the ``session-start`` / ``check`` subcommand, or (no subcommand) a
  PreToolUse event on stdin; ``--remote`` / ``--base-branch`` default to
  ``origin`` / ``main``.
- Outputs: ``session-start`` prints an ``additionalContext`` JSON object when
  the base is stale; hook mode prints a deny decision when committing on a stale
  base; ``check`` prints the verdict. Exit 0 except ``check`` which exits 1 when
  stale.
- Failure policy: fail-open (exit 0, no decision) on any internal error so the
  guard cannot wedge a session; the substantive staleness signal still fails
  loud via the deny / the ``check`` exit code.

Tested by tests/test_preflight_session_base_freshness.py. Refs #1632, #745, #654.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

import preflight_branch_base
import preflight_main_freshness
from _git import run_git
from _hook_runtime import build_deny, run_event_hook

REPO_ROOT = Path(__file__).resolve().parent.parent
STAMP_FILE = REPO_ROOT / ".git" / "SESSION_BASE_FRESHNESS"
_REMOTE_ENV_VAR = "CLAUDE_CODE_REMOTE"

# Mirror preflight_commit_session_branch's commit detector: match a ``git
# commit`` anywhere in the command (commits are chained, e.g. ``git add -A &&
# git commit``), but keep plumbing like ``git commit-tree`` out.
_GIT_COMMIT_RE = re.compile(r"\bgit\s+commit(?![\w-])")

# Runbook for the server-side base-update path (non_fast_forward branches).
_RUNBOOK = "docs/runbooks/remote-session-base-update.md"


def _is_remote() -> bool:
    return os.environ.get(_REMOTE_ENV_VAR, "").lower() == "true"


def _current_branch(repo: Path | None = None) -> str | None:
    """Return the current branch name, or None on failure (detached HEAD, error)."""
    _repo = repo if repo is not None else REPO_ROOT
    try:
        cp = run_git(["symbolic-ref", "--short", "-q", "HEAD"], cwd=_repo)
        return cp.stdout.strip() or None
    except Exception:
        return None


def _force_push_blocked(branch: str | None) -> bool:
    """Return True when the branch is subject to the non_fast_forward ruleset.

    Mirrors .github/rulesets/all-branches.json: ~ALL except ~DEFAULT_BRANCH
    (``main``) and ``refs/heads/dependabot/*``. On these branches git rebase +
    force-push is unavailable; the server-side runbook is the correct path.
    Returns False (fail-open) when branch is None so an unknown branch does not
    change existing behaviour.
    """
    if branch is None:
        return False
    if branch == "main":
        return False
    return not branch.startswith("dependabot/")


def base_is_stale(*, repo: Path | None = None, stamp_path: Path | None = None) -> bool | None:
    """Return True if HEAD lacks the recorded session-start base SHA.

    Returns ``None`` when no stamp exists (nothing recorded yet -> fail-open).
    Reuses ``preflight_branch_base.check_base_freshness`` against the stamped
    SHA; does NOT fetch (the SHA was fetched at session start). ``repo`` /
    ``stamp_path`` resolve to the module globals at CALL time (not def time) so a
    test can monkeypatch them.
    """
    if repo is None:
        repo = REPO_ROOT
    if stamp_path is None:
        stamp_path = STAMP_FILE
    stamp = preflight_main_freshness.read_stamp(stamp_path)
    if stamp is None:
        return None
    result = preflight_branch_base.check_base_freshness(repo=repo, base_ref=stamp.sha)
    return result.status != "pass"


def _build_warning(sha: str, *, force_push_blocked: bool = False) -> str:
    if force_push_blocked:
        remedy = (
            f"Force-push is blocked on this branch (all-branches-no-force-push\n"
            f"ruleset, bypass_actors: []). Use the server-side base-update\n"
            f"runbook instead of git rebase + force-push:\n"
            f"  {_RUNBOOK}\n"
            f"That path needs no local commit, force-push, or GPG."
        )
    else:
        remedy = "  git fetch origin main && git rebase origin/main"
    return (
        f"STALE BRANCH BASE: this branch does not contain origin/main as "
        f"observed at session start (SHA={sha[:12]}). Update the base BEFORE "
        f"implementing so the late-rebase loop from PR #1625 (retro #1632, "
        f"Fact 3) does not recur:\n"
        f"{remedy}\n"
        f"Until you do, a git commit on this branch is blocked by "
        f"scripts/preflight_session_base_freshness.py."
    )


def _build_deny_reason(sha: str, *, force_push_blocked: bool = False) -> str:
    if force_push_blocked:
        remedy = (
            f"Force-push is blocked on this branch (all-branches-no-force-push\n"
            f"ruleset, bypass_actors: []), so git rebase + force-push is not an\n"
            f"option. Use the server-side base-update runbook:\n"
            f"  {_RUNBOOK}\n"
            f"A merge commit that brings origin/main into HEAD satisfies the\n"
            f"same invariant the gate verifies. Refs #1802, #1775."
        )
    else:
        remedy = (
            "Rebase before committing:\n"
            "  git fetch origin main && git rebase origin/main\n\n"
            "After the rebase HEAD contains the base and commits proceed."
        )
    return (
        f"Blocked by scripts/preflight_session_base_freshness.py: this branch "
        f"does not contain origin/main as observed at session start "
        f"(SHA={sha[:12]}), so its base is stale. Committing now reproduces the "
        f"PR #1625 late-rebase loop (retro #1632, Fact 3): the work would only "
        f"fail the pre-push branch-base gate after it is done.\n\n"
        f"{remedy}\n\n"
        f"Refs #1632, #745."
    )


# ---------------------------------------------------------------------------
# session-start mode
# ---------------------------------------------------------------------------
def _emit_context(message: str) -> None:
    print(json.dumps({"hookSpecificOutput": {"additionalContext": message}}))


def cmd_session_start(args: argparse.Namespace) -> int:
    """SessionStart hook: record origin/main and warn on a stale base."""
    if not _is_remote():
        return 0
    try:
        stamp = preflight_main_freshness.fetch_and_record(
            remote=args.remote,
            branch=args.base_branch,
            repo=REPO_ROOT,
            stamp_path=STAMP_FILE,
        )
    except Exception:
        return 0
    try:
        result = preflight_branch_base.check_base_freshness(repo=REPO_ROOT, base_ref=stamp.sha)
    except Exception:
        return 0
    if result.status != "pass":
        branch = _current_branch(REPO_ROOT)
        _emit_context(_build_warning(stamp.sha, force_push_blocked=_force_push_blocked(branch)))
    return 0


# ---------------------------------------------------------------------------
# hook mode (PreToolUse Bash git commit)
# ---------------------------------------------------------------------------
def decide(event: dict[str, Any]) -> dict[str, Any] | None:
    """Return a deny dict when committing on a stale base, else None."""
    if not _is_remote():
        return None
    if event.get("tool_name") != "Bash":
        return None
    command = str((event.get("tool_input") or {}).get("command") or "")
    if not _GIT_COMMIT_RE.search(command):
        return None
    try:
        stamp = preflight_main_freshness.read_stamp(STAMP_FILE)
        if stamp is None:
            return None  # nothing recorded -> fail-open
        result = preflight_branch_base.check_base_freshness(repo=REPO_ROOT, base_ref=stamp.sha)
    except Exception:
        return None
    if result.status == "pass":
        return None
    branch = _current_branch(REPO_ROOT)
    return build_deny(_build_deny_reason(stamp.sha, force_push_blocked=_force_push_blocked(branch)))


# ---------------------------------------------------------------------------
# check mode
# ---------------------------------------------------------------------------
def cmd_check(_args: argparse.Namespace) -> int:
    stale = base_is_stale()
    if stale is None:
        print("OK: no session base stamp recorded (nothing to check).")
        return 0
    if not stale:
        print("OK: branch contains the session-start origin/main base.")
        return 0
    branch = _current_branch(REPO_ROOT)
    if _force_push_blocked(branch):
        print(
            f"FAIL: branch base is stale (HEAD does not contain the session-start "
            f"origin/main). Force-push is blocked on this branch; use the "
            f"server-side base-update runbook: {_RUNBOOK}",
            file=sys.stderr,
        )
    else:
        print(
            "FAIL: branch base is stale (HEAD does not contain the session-start "
            "origin/main). Rebase: git fetch origin main && git rebase origin/main",
            file=sys.stderr,
        )
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd")

    p_ss = sub.add_parser("session-start", help="SessionStart hook: record base and warn if stale.")
    p_ss.add_argument("--remote", default="origin", help="Remote name (default: origin).")
    p_ss.add_argument("--base-branch", default="main", help="Base branch (default: main).")
    p_ss.set_defaults(func=cmd_session_start)

    p_check = sub.add_parser("check", help="Print staleness verdict (exit 0 fresh, 1 stale).")
    p_check.set_defaults(func=cmd_check)

    args = parser.parse_args(argv)
    if args.cmd is None:
        return run_event_hook("preflight_session_base_freshness", decide, auditable=False)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
