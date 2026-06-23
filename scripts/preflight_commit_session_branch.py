#!/usr/bin/env python3
"""PreToolUse hook: block git commit onto a non-session branch in remote sessions.

Refs #1181, #785. In remote execution environments (CLAUDE_CODE_REMOTE=true)
the transport layer only permits pushes to the single branch that was
checked out at session start (recorded in .git/CLAUDE_SESSION_BRANCH by
check_session_branch.py). ``preflight_push_session_branch.py`` already
enforces that at push time; but that is the *last* moment the constraint
surfaces, after commits have already been stacked.

The PR #1174 retrospective (#1181) traced a real failure to exactly that
gap: an unrelated issue's commit was stacked onto an existing PR branch,
and the single-branch limit was only discovered when the separated push
was refused. The retrospective classified this as an *unclear agent
process*: "No gate stops an agent from committing one issue's work onto
another issue's branch; the session-branch gate only surfaces the
constraint at push time, after the commit is already stacked."

This hook closes that gap by shifting the same constraint left to commit
time. It intercepts every Bash ``git commit`` command and denies it when
the currently checked-out branch is not in the authorized branch set, so
the limit is known *before* commits are stacked rather than at push. The
check is a conjunction (member of the set AND not a protected branch), not
a single equality, so paired work and post-merge follow-up branches stay
continuable (Refs #1513).

Fail-open: any hook error, an empty authorized set, detached HEAD, or a
non-remote environment exits without a decision so the commit proceeds and
the push-time gate (plus CI) acts as backstop.

Architecture mirrors preflight_push_session_branch.py:
* Pure decide() surface plus a thin main() entry.
* No subprocess: the current branch is read from .git/HEAD and the
  authorized set from .git/CLAUDE_SESSION_BRANCH, so the decision is
  unit-testable without touching a live repository.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from _hook_runtime import build_deny, run_event_hook
from _session_branches import is_authorized, read_authorized_set

REPO_ROOT = Path(__file__).resolve().parent.parent
_SESSION_BRANCH_FILE = REPO_ROOT / ".git" / "CLAUDE_SESSION_BRANCH"
_HEAD_FILE = REPO_ROOT / ".git" / "HEAD"
_REMOTE_ENV_VAR = "CLAUDE_CODE_REMOTE"

# Detect a ``git commit`` invocation anywhere in the command (commits are
# routinely chained, e.g. ``git add -A && git commit -m ...``). The negative
# lookahead keeps ``git commit-tree`` and similar plumbing out.
_GIT_COMMIT_RE = re.compile(r"\bgit\s+commit(?![\w-])")

_HEAD_REF_PREFIX = "ref: refs/heads/"


def _read_authorized_branches() -> set[str]:
    return read_authorized_set(_SESSION_BRANCH_FILE)


def _current_branch() -> str | None:
    """Return the checked-out branch from .git/HEAD, or None.

    Returns None on a detached HEAD (no ``ref:`` prefix) or any read error so
    the caller fails open.
    """
    try:
        head = _HEAD_FILE.read_text().strip()
    except OSError:
        return None
    if not head.startswith(_HEAD_REF_PREFIX):
        return None  # detached HEAD; fail-open
    branch = head[len(_HEAD_REF_PREFIX):].strip()
    return branch or None


def decide(event: dict[str, Any]) -> dict[str, Any] | None:
    """Return a deny dict when committing onto a non-session branch, else None."""
    if os.environ.get(_REMOTE_ENV_VAR, "").lower() != "true":
        return None

    if event.get("tool_name") != "Bash":
        return None

    command = str((event.get("tool_input") or {}).get("command") or "")
    if not _GIT_COMMIT_RE.search(command):
        return None

    authorized = _read_authorized_branches()
    if not authorized:
        return None  # fail-open: no session branch recorded yet

    current_branch = _current_branch()
    if not current_branch:
        return None  # detached HEAD / unknown; fail-open

    if is_authorized(current_branch, authorized):
        return None

    authorized_list = ", ".join(sorted(authorized))
    target_hint = sorted(authorized)[0]
    return build_deny(
        f"Blocked by scripts/preflight_commit_session_branch.py: "
        f"this remote session can only push to an authorized branch "
        f"({authorized_list}), but you are about to commit on '{current_branch}'. "
        f"A commit made here cannot be pushed and would strand the work "
        f"(the push-time gate would refuse it).\n\n"
        f"Do one of the following before committing:\n"
        f"  - Switch back to an authorized branch: git switch {target_hint}\n"
        f"  - Or move the work onto it (e.g. git stash, switch, stash pop).\n\n"
        f"Never stack an unrelated issue's commit on the session branch: open a "
        f"separate issue and handle it in its own session. To authorize a new "
        f"branch, start a new remote session on it.\n\n"
        f"Refs #1513, #1181, #785."
    )


def main(argv: list[str] | None = None) -> int:
    del argv
    return run_event_hook("preflight_commit_session_branch", decide, auditable=False)


if __name__ == "__main__":
    raise SystemExit(main())
