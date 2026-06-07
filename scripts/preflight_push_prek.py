#!/usr/bin/env python3
"""PreToolUse hook: run prek before git push.

Refs #901. Closes the missing-deterministic-gate repair from the
PR #898 retrospective:

  Repair 1 -- trailing newline absent in ``translations.json``:
    ``prek``/``end-of-file-fixer`` would have caught it; prek was not
    run locally before the first push.

prek already runs in CI (``portable-pr-policy.yml``) and via
``.githooks/pre-push`` when ``core.hooksPath`` is configured.  This
script extends the Claude / Codex PreToolUse Bash layer (same mechanism
as ``preflight_push_base.py``) so the check also fires in web sessions
where the local git hook is absent.

Architecture mirrors ``preflight_push_base.py``:

* Pure ``decide()`` surface plus a thin ``main()`` entry.
* Fail-open on infrastructure errors (``uv`` absent, subprocess crash,
  timeout) so a broken environment never wedges a push.  CI is the
  backstop in those cases.
* Fail-closed when prek exits non-zero (fixable issues found; commit
  the auto-fixes then re-push).
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
_GIT_PUSH_RE = re.compile(r"(?m)^\s*git\s+push\b")
_TIMEOUT_PREK: int = 60
_Runner = Callable[..., subprocess.CompletedProcess[str]]


def _run_prek(*, runner: _Runner = subprocess.run) -> dict[str, Any] | None:
    """Run ``uv tool run prek run --all-files``; return deny dict if it finds issues.

    Fail-open on ``OSError``/``SubprocessError`` (uv not installed, timeout,
    etc.) so a missing toolchain never blocks a push -- CI is the backstop.
    """
    try:
        result = runner(
            ["uv", "tool", "run", "prek", "run", "--all-files"],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_PREK,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(f"::warning::preflight_push_prek: prek invocation error: {exc}", file=sys.stderr)
        return None

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        return build_deny(
            "Blocked by scripts/preflight_push_prek.py: prek found "
            "issues that must be staged and committed before push.\n\n"
            f"{detail}\n\n"
            "Repair: commit the prek-fixed files, then re-run the push. Refs #901."
        )
    return None


def decide(
    event: dict[str, Any],
    *,
    runner: _Runner = subprocess.run,
) -> dict[str, Any] | None:
    """Return a deny dict if the prek pre-push check fails, or None to allow."""
    if event.get("tool_name") != "Bash":
        return None
    command = str((event.get("tool_input") or {}).get("command") or "")
    if not _GIT_PUSH_RE.search(command):
        return None

    return _run_prek(runner=runner)


def main(argv: list[str] | None = None) -> int:
    """CLI entry. Configuration is via stdin JSON (PreToolUse hook event)."""
    del argv
    return run_event_hook("preflight_push_prek", decide)


if __name__ == "__main__":
    raise SystemExit(main())
