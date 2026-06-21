#!/usr/bin/env python3
"""PreToolUse hook: block Bash ``git push`` when branch is behind its base.

Reads a PreToolUse event from stdin. Fast-passes any Bash command that
does not look like a ``git push``. When a push is detected, delegates to
``preflight_branch_base.py verify`` to confirm the branch contains the
latest origin/main.

Fail-open: any hook error exits 0 so a script bug never wedges a push.

Refs #856, #1854.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from _hook_runtime import build_deny, run_event_hook

REPO_ROOT = Path(__file__).resolve().parent.parent

# Detect a leading ``git push``, optionally prefixed by ``rtk`` when the rtk
# auto-rewrite PreToolUse hook has rewritten ``git push`` -> ``rtk git push``
# (Refs #1199). Keeping the prefix optional means the gate fires on both forms.
_GIT_PUSH_RE = re.compile(r"(?m)^\s*(?:rtk\s+)?git\s+push\b")
_Runner = Callable[..., subprocess.CompletedProcess[str]]


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
        return build_deny(
            "Blocked by scripts/preflight_push_base.py "
            "(client-side preflight): "
            "the branch is out-of-date with the base branch.\n\n"
            f"{detail}\n\n"
            "Repair: `git fetch origin main && git merge FETCH_HEAD --no-edit`, "
            "then re-run the push. "
            "Use merge (not rebase) to avoid a non-fast-forward conflict "
            "when the branch is already published and force-push is prohibited. "
            "Refs #856, #1854."
        )
    return None


def main(argv: list[str] | None = None) -> int:
    del argv
    return run_event_hook("preflight_push_base", decide, auditable=False)


if __name__ == "__main__":
    raise SystemExit(main())
