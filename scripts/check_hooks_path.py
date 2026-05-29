#!/usr/bin/env python3
"""SessionStart hook: surface missing core.hooksPath configuration.

Refs #760. The pre-push hook at .githooks/pre-push runs the stale-base and
preflight checks before a push leaves the worktree, but Git only honours it
when core.hooksPath is pointed at .githooks.  Without that config the hook is
silently skipped, allowing stale-base branches to reach GitHub.

This script emits an additionalContext warning when core.hooksPath is not set
to .githooks so the operator notices at session start rather than after a
failed PR review.  Fails open (exit 0) on any error so a broken git install
never wedges a session.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

_EXPECTED = ".githooks"
_HOOKS_FILE = Path(".githooks") / "pre-push"


def _git_config(key: str) -> str | None:
    git = shutil.which("git")
    if git is None:
        return None
    result = subprocess.run(  # noqa: S603 -- git argv is built from shutil.which + parser-controlled key
        [git, "config", "--local", key],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    return result.stdout.strip()


def check() -> dict[str, Any] | None:
    """Return a hook output dict when core.hooksPath is misconfigured, else None."""
    current = _git_config("core.hooksPath")
    if current == _EXPECTED:
        return None

    if current is None:
        detail = "core.hooksPath is not set"
    else:
        detail = f"core.hooksPath is '{current}', expected '{_EXPECTED}'"

    message = (
        f"WARNING: {detail}. The pre-push hook at {_HOOKS_FILE} (stale-base + "
        "preflight checks) will not run before git push. "
        "Fix with: git config core.hooksPath .githooks"
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
