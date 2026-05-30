#!/usr/bin/env python3
"""PreToolUse hook: block Bash ``git push`` when branch is behind its base.

Reads a PreToolUse event from stdin. Fast-passes any Bash command that
does not look like a ``git push``. When a push is detected, delegates to
``preflight_branch_base.py verify`` to confirm the branch contains the
latest origin/main.

Fail-open: any hook error exits 0 so a script bug never wedges a push.

Refs #856.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

_GIT_PUSH_RE = re.compile(r"(?m)^\s*git\s+push\b")
_Runner = Callable[..., subprocess.CompletedProcess[str]]


def _deny(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def decide(
    event: dict[str, Any],
    *,
    runner: _Runner = subprocess.run,
) -> dict[str, Any] | None:
    """Return a deny dict if a git push is blocked, or None to allow."""
    if event.get("tool_name") != "Bash":
        return None
    command = str((event.get("tool_input") or {}).get("command") or "")
    if not _GIT_PUSH_RE.search(command):
        return None

    script = REPO_ROOT / "scripts" / "preflight_branch_base.py"
    try:
        result = runner(
            [sys.executable, str(script), "verify"],
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"::warning::preflight_push_base: hook error: {exc}", file=sys.stderr)
        return None

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        return _deny(
            "Blocked by scripts/preflight_push_base.py "
            "(client-side preflight): "
            "the branch is out-of-date with the base branch.\n\n"
            f"{detail}\n\n"
            "Repair: `git fetch origin main && git rebase origin/main`, "
            "then re-run the push. Refs #856."
        )
    return None


def main(argv: list[str] | None = None) -> int:
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(f"::error::preflight_push_base: malformed stdin JSON: {exc}", file=sys.stderr)
        return 0
    if not isinstance(event, dict):
        return 0
    output = decide(event)
    if output is not None:
        sys.stdout.write(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
