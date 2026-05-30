#!/usr/bin/env python3
"""PreToolUse hook: run prek and single-commit preflight before git push.

Refs #901. Closes the two missing-deterministic-gate repairs from the
PR #898 retrospective:

  Repair 1 -- trailing newline absent in ``translations.json``:
    ``prek``/``end-of-file-fixer`` would have caught it; prek was not
    run locally before the first push.

  Repair 2 -- two-commit branch squash-collapsed at merge:
    ``preflight_pr_single_commit`` would have caught it; the pre-push
    hook was not installed locally (requires ``git config
    core.hooksPath .githooks`` or ``pre-commit install --hook-type
    pre-push``).

Both gates already run in CI (``portable-pr-policy.yml``) and via
``.githooks/pre-push`` when ``core.hooksPath`` is configured.  This
script extends the Claude / Codex PreToolUse Bash layer (same mechanism
as ``preflight_push_base.py``) so both checks also fire in web sessions
where the local git hook is absent.

Architecture mirrors ``preflight_push_base.py``:

* Pure ``decide()`` surface plus a thin ``main()`` entry.
* Fail-open on infrastructure errors (``uv`` absent, subprocess crash,
  timeout) so a broken environment never wedges a push.  CI is the
  backstop in those cases.
* Fail-closed when prek exits non-zero (fixable issues found; commit
  the auto-fixes then re-push) or when the single-commit check fails
  (squash before push).
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
_TIMEOUT_PREK: int = 60
_TIMEOUT_SINGLE_COMMIT: int = 15
_Runner = Callable[..., subprocess.CompletedProcess[str]]


def _deny(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


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
        return _deny(
            "Blocked by scripts/preflight_push_prek.py: prek found "
            "issues that must be staged and committed before push.\n\n"
            f"{detail}\n\n"
            "Repair: commit the prek-fixed files, then re-run the push. Refs #901."
        )
    return None


def _run_single_commit(*, runner: _Runner = subprocess.run) -> dict[str, Any] | None:
    """Run ``preflight_pr_single_commit.py``; return deny dict if it fails."""
    script = REPO_ROOT / "scripts" / "preflight_pr_single_commit.py"
    try:
        result = runner(
            [sys.executable, str(script)],
            capture_output=True,
            text=True,
            timeout=_TIMEOUT_SINGLE_COMMIT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        print(
            f"::warning::preflight_push_prek: single-commit check error: {exc}",
            file=sys.stderr,
        )
        return None

    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        return _deny(
            "Blocked by scripts/preflight_push_prek.py: single-commit "
            "check failed.\n\n"
            f"{detail}\n\n"
            "Repair: squash to one commit before push (`git rebase -i origin/main`). "
            "Refs #901 / #492."
        )
    return None


def decide(
    event: dict[str, Any],
    *,
    runner: _Runner = subprocess.run,
) -> dict[str, Any] | None:
    """Return a deny dict if a pre-push check fails, or None to allow.

    Checks run in order: prek first (file-level issues), then single-commit
    (branch shape). The first failure short-circuits so the deny message
    stays focused on the most immediate repair.
    """
    if event.get("tool_name") != "Bash":
        return None
    command = str((event.get("tool_input") or {}).get("command") or "")
    if not _GIT_PUSH_RE.search(command):
        return None

    deny = _run_prek(runner=runner)
    if deny is not None:
        return deny

    return _run_single_commit(runner=runner)


def main(argv: list[str] | None = None) -> int:
    """CLI entry. Configuration is via stdin JSON (PreToolUse hook event)."""
    del argv
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(f"::error::preflight_push_prek: malformed stdin JSON: {exc}", file=sys.stderr)
        return 0
    if not isinstance(event, dict):
        return 0
    output = decide(event)
    if output is not None:
        sys.stdout.write(json.dumps(output))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
