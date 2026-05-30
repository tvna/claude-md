#!/usr/bin/env python3
"""SessionStart hook: ensure core.hooksPath is configured to .githooks.

Refs #956, #760. The pre-push hook at .githooks/pre-push runs the stale-base
and preflight checks before a push leaves the worktree, but Git only honours
it when core.hooksPath is pointed at .githooks.  Without that config the hook
is silently skipped, allowing stale-base branches to reach GitHub.

This script auto-configures core.hooksPath when it is missing or wrong, and
emits an informational additionalContext message so the operator knows what
changed.  If the git config write fails, it falls back to a warning with the
manual fix command.  Fails open (exit 0) on any error so a broken git install
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


def _git_config_set(key: str, value: str) -> bool:
    """Run `git config <key> <value>`; return True on success."""
    git = shutil.which("git")
    if git is None:
        return False
    result = subprocess.run(  # noqa: S603 -- argv built from shutil.which + caller-controlled literals
        [git, "config", key, value],
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode == 0


def check() -> dict[str, Any] | None:
    """Auto-configure core.hooksPath if needed; return hook output dict or None."""
    current = _git_config("core.hooksPath")
    if current == _EXPECTED:
        return None

    detail = "core.hooksPath was not set" if current is None else f"core.hooksPath was '{current}'"

    if _git_config_set("core.hooksPath", _EXPECTED):
        message = (
            f"core.hooksPath: {detail}, auto-configured to '{_EXPECTED}'. "
            f"The pre-push hook at {_HOOKS_FILE} is now active."
        )
    else:
        message = (
            f"WARNING: {detail}. Could not auto-configure core.hooksPath. "
            f"Fix manually: git config core.hooksPath {_EXPECTED}"
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
