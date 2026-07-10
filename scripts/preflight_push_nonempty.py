#!/usr/bin/env python3
"""PreToolUse hook: block git push when HEAD equals the base tip (nothing new).

Refs #1130. Retrospective for PR #1128 found a silent-commit-then-push-stale-HEAD
failure mode: a chained ``git add && git commit -q && git push`` aborted at the
quiet commit (a pre-commit hook rejected it, but ``-q`` swallowed the output),
so the subsequent push shipped the unchanged base commit; i.e. main's state
WITHOUT the intended fix; to the session branch. ``preflight_push_base.py``
checks that HEAD *contains* the base, but not that HEAD has advanced *beyond*
it, so the empty push slipped through.

This hook closes that gap deterministically: when a ``git push`` is detected and
the local ``HEAD`` resolves to the very same commit as the base tip
(``origin/main``), there is no new work to push, so the push is denied. The
loud denial points the agent back to inspecting ``git log -1``; exactly the
manual save that caught the original incident.

Fail-open: any hook error, a missing base ref, or a delete / dry-run push exits
0 so a script bug never wedges a legitimate push. CI is the backstop.

Architecture mirrors preflight_push_base.py: a pure decide() library imported
and dispatched by scripts/preflight_push_dispatch.py (the consolidated push hook,
Refs #2410); this module has no main() entry of its own. Its runner is injected
so git calls are unit-testable without a real repo.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from _git import run_git
from _hook_runtime import build_deny

REPO_ROOT = Path(__file__).resolve().parent.parent

# The base branch every session branch is cut from in this repo.
BASE_REF = "origin/main"

# Optional ``rtk`` prefix: the rtk auto-rewrite PreToolUse hook rewrites
# ``git push`` -> ``rtk git push`` (Refs #1199), so the gate must fire on both.
_GIT_PUSH_RE = re.compile(r"(?m)^\s*(?:rtk\s+)?git\s+push\b")

# Command surface this hook acts on, read by scan_hook_predicate_surface_drift.py
# to verify the Bash(*git push*) if: predicate admits it (a narrower predicate
# would silently skip a command the script handles, the PR #2120 class). Refs #2133.
HOOK_GIT_SUBCOMMANDS = frozenset({"push"})
# Pushes that do not ship HEAD: a deletion moves no commit, and a dry-run must
# never be blocked. Either makes the HEAD-vs-base comparison irrelevant.
_SKIP_FLAG_RE = re.compile(r"(?<!\S)(?:--delete|-d|--dry-run|-n)(?!\S)")

_Runner = Callable[[list[str]], subprocess.CompletedProcess[str]]


def _default_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
    return run_git(args, cwd=REPO_ROOT, timeout=30)


def _resolve(runner: _Runner, ref: str) -> str | None:
    """Return the full SHA *ref* resolves to, or None when it cannot resolve."""
    try:
        result = runner(["rev-parse", "--verify", "--quiet", ref])
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    sha = (result.stdout or "").strip()
    return sha or None


def decide(
    event: dict[str, Any],
    *,
    runner: _Runner = _default_runner,
) -> dict[str, Any] | None:
    """Return a deny dict when HEAD equals the base tip, or None to allow."""
    if event.get("tool_name") != "Bash":
        return None
    command = str((event.get("tool_input") or {}).get("command") or "")
    if not _GIT_PUSH_RE.search(command):
        return None
    if _SKIP_FLAG_RE.search(command):
        return None  # delete / dry-run pushes do not ship HEAD; fail-open

    head = _resolve(runner, "HEAD")
    base = _resolve(runner, BASE_REF)
    if head is None or base is None:
        return None  # fail-open: cannot resolve one side, leave it to CI
    if head != base:
        return None

    return build_deny(
        "Blocked by scripts/preflight_push_nonempty.py "
        "(client-side preflight): local HEAD is the same commit as the base "
        f"tip ({BASE_REF}), so this push ships no new work.\n\n"
        "This is the silent-commit-then-stale-HEAD failure mode from #1128: a "
        "commit likely aborted (a rejected pre-commit hook, or a `-q` commit "
        "whose failure was swallowed) and HEAD never advanced.\n\n"
        "Repair: run `git log -1` to confirm your intended commit is present; "
        "re-run the commit verbosely (without `-q`) and check its exit code, "
        "then push as a separate step. Refs #1130."
    )
