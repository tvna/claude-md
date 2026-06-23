#!/usr/bin/env python3
"""SessionStart hook: surface the permitted push target in remote execution sessions.

Refs #785. In remote execution environments (CLAUDE_CODE_REMOTE=true) the
transport layer restricts git pushes to the single branch that was checked
out at session start.  Without this diagnostic the agent has no way to
identify the permitted branch before a failed push attempt returns a bare
HTTP 403 with no branch name.

When the environment is remote:
* Emits an additionalContext notice naming the session push target.
* Repairs the seed's trailing newline before appending, so "the lock file
  ends with a newline" is a writer-enforced invariant; the write-side half
  of the defense against the concatenation corruption that wedged the gate
  (Refs #1522). append_branch covers the append path; this covers the
  dedup early-return path it cannot reach.
* Appends the branch name to <repo-root>/.git/CLAUDE_SESSION_BRANCH so that
  preflight_push_session_branch.py can validate push refspecs without an
  extra subprocess call. Appending (rather than overwriting) lets a second
  session in the same container; paired work or a post-merge follow-up --
  authorize its branch without clobbering the partner's entry (Refs #1513).

Fails open (exit 0) on any error so a broken git install never wedges a
session.
"""

from __future__ import annotations

import contextlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from _git import run_git
from _session_branches import append_branch

REPO_ROOT = Path(__file__).resolve().parent.parent
_REMOTE_ENV_VAR = "CLAUDE_CODE_REMOTE"
_SESSION_BRANCH_FILE = REPO_ROOT / ".git" / "CLAUDE_SESSION_BRANCH"


def _ensure_seed_trailing_newline(path: Path) -> None:
    """Repair a session-branch seed that lacks a trailing newline.

    Write-side half of the double defense against the lock-corruption that
    blocked the gate (Refs #1522). The SessionStart seed written by the
    remote harness may lack a trailing newline. ``append_branch`` inserts a
    separator on the append path, but when the current branch is already a
    member it dedup-returns without touching the file, so a malformed seed
    survives and the next session's append concatenates onto it; the exact
    failure that wedged ``preflight_*_session_branch``.

    Normalizing the seed here makes "the lock file ends with a newline" a
    writer-enforced invariant, independent of ``append_branch`` whose
    contract is unchanged. Fails open (never raises): a broken read/write
    must not wedge a session.
    """
    try:
        existing = path.read_text(encoding="utf-8")
    except OSError:
        return
    if not existing or existing.endswith("\n"):
        return
    with contextlib.suppress(OSError):
        path.write_text(existing + "\n", encoding="utf-8")


def _current_branch() -> str | None:
    try:
        result = run_git(["branch", "--show-current"], timeout=10)
        branch = result.stdout.strip()
        return branch if branch else None
    except (OSError, subprocess.SubprocessError, RuntimeError):
        return None


def check() -> dict[str, Any] | None:
    """Return additionalContext notice when running in a remote session, else None."""
    if os.environ.get(_REMOTE_ENV_VAR, "").lower() != "true":
        return None

    branch = _current_branch()
    if not branch:
        return None

    _ensure_seed_trailing_newline(_SESSION_BRANCH_FILE)
    append_branch(_SESSION_BRANCH_FILE, branch)

    message = (
        f"Session push target: '{branch}'. "
        "All git pushes in this remote session must target this branch on the remote. "
        f"When pushing from a different local branch use: "
        f"git push origin <local-branch>:{branch}"
    )
    return {
        "hookSpecificOutput": {
            "additionalContext": message,
        }
    }


def main() -> None:
    try:
        output = check()
    except Exception:
        sys.exit(0)

    if output is not None:
        print(json.dumps(output))


if __name__ == "__main__":
    main()
