#!/usr/bin/env python3
"""SessionStart hook: surface the permitted push target in remote execution sessions.

Refs #785. In remote execution environments (CLAUDE_CODE_REMOTE=true) the
transport layer restricts git pushes to the single branch that was checked
out at session start.  Without this diagnostic the agent has no way to
identify the permitted branch before a failed push attempt returns a bare
HTTP 403 with no branch name.

When the environment is remote:
* Emits an additionalContext notice naming the session push target.
* Writes the branch name to <repo-root>/.git/CLAUDE_SESSION_BRANCH so that
  preflight_push_session_branch.py can validate push refspecs without an
  extra subprocess call.

Fails open (exit 0) on any error so a broken git install never wedges a
session.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
_REMOTE_ENV_VAR = "CLAUDE_CODE_REMOTE"
_SESSION_BRANCH_FILE = REPO_ROOT / ".git" / "CLAUDE_SESSION_BRANCH"


def _current_branch() -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    try:
        result = subprocess.run(  # noqa: S603
            [git, "branch", "--show-current"],
            capture_output=True,
            text=True,
            check=False,
            timeout=10,
        )
        branch = result.stdout.strip()
        return branch if branch else None
    except (OSError, subprocess.SubprocessError):
        return None


def check() -> dict[str, Any] | None:
    """Return additionalContext notice when running in a remote session, else None."""
    if os.environ.get(_REMOTE_ENV_VAR, "").lower() != "true":
        return None

    branch = _current_branch()
    if not branch:
        return None

    with contextlib.suppress(OSError):
        _SESSION_BRANCH_FILE.write_text(branch)

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
