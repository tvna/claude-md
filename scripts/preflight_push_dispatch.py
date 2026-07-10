#!/usr/bin/env python3
"""PreToolUse dispatcher: run every ``git push`` client-side gate in one process.

Refs #2410 (child of the FTA/FMEA tracking issue #2408). A single ``git push``
Bash call previously spawned one PreToolUse process per push-specific gate
(``preflight_push_unsigned_commits`` -> ``preflight_push_base`` ->
``preflight_push_session_branch`` -> ``preflight_push_nonempty``), each with its
own registration in ``scripts/agent_hooks_source.json``. That
one-check-one-process-one-registration shape generated the drift classes the
FTA/FMEA record files:

* F7 (the wiring single-point-of-failure): four separate registrations to keep
  in step per agent target, collapsed here to one.
* F10 (a divergent push-detection regex): ``preflight_push_prek.py`` (since
  deleted with #901) lacked the ``rtk`` prefix the wired gates carry; deleting
  it removes that divergence at the source.

This dispatcher collapses the wiring WITHOUT touching any check's detection or
decision. It delegates to each existing pure ``decide()`` function in the fixed
order below and returns the first deny (first-deny-wins). Crucially it imposes
NO detection prefilter of its own: each gate keeps its own ``git push``
detection, refspec parsing, and fail-open posture, so every gate fires on
exactly the commands it fired on as a standalone process and its deny text is
preserved BYTE-FOR-BYTE.

The gates are deliberately NOT uniform in detection breadth, which is why a
single shared prefilter here would silently narrow coverage (Codex review on
this PR): ``preflight_push_unsigned_commits`` matches ``git push`` anywhere in
the command and splits at shell command boundaries, so it catches a push
chained after another command (``git commit -m x && git push ...``) or behind an
env assignment (``FOO=1 git push``) in Codex/Devin sessions (Refs #2140); the
other three match only a line-leading ``git push``. Delegating detection keeps
each of those behaviours intact.

Order (the claude registration order the consolidated hook replaces):

1. ``preflight_push_unsigned_commits.decide``: deny a push shipping an
   unsigned commit (remote sessions).
2. ``preflight_push_base.decide``: deny a branch behind its base.
3. ``preflight_push_session_branch.decide``: deny a push to a non-session
   branch (remote sessions).
4. ``preflight_push_nonempty.decide``: deny a push whose HEAD equals the base
   tip (ships no new work).

Security equivalence: the authority for pushes is server-side (rulesets,
transport branch restriction, CI); this local chain is the left-shift layer that
converts would-be red CI runs into pre-push denies. Consolidating the wiring does
not lower its strength. The dispatcher emits through ONE
``emit_decision(..., auditable=False)`` boundary so ``CLAUDE_GATE_MODE=audit``
can never suppress a push deny (the same posture each gate carried individually).

Fail-open: a non-push command, a non-Bash tool, or an empty command passes
through (every delegated ``decide`` returns None); each delegated ``decide`` also
keeps its own wide fail-open on infrastructure errors. Always exits 0.

Tested by ``tests/test_preflight_push_dispatch.py``.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import preflight_push_base
import preflight_push_nonempty
import preflight_push_session_branch
import preflight_push_unsigned_commits
from _hook_runtime import run_event_hook

# Command surface this hook acts on, read by scan_hook_predicate_surface_drift.py
# to verify the Bash(*git push*) if: predicate admits it (a narrower predicate
# would silently skip a command the script handles, the PR #2120 class). Refs #2133.
HOOK_GIT_SUBCOMMANDS = frozenset({"push"})

# The push gates in their fixed evaluation order (the claude registration order
# this dispatcher replaces). first-deny-wins: the first check that returns a deny
# dict short-circuits, so the deny the agent sees is byte-identical to the deny
# that gate emitted when it was a standalone process. Each ``decide`` performs
# its own tool_name and push detection, so the dispatcher adds no prefilter that
# could narrow a gate's coverage.
_Check = Callable[[dict[str, Any]], Mapping[str, Any] | None]
_CHECKS: tuple[_Check, ...] = (
    preflight_push_unsigned_commits.decide,
    preflight_push_base.decide,
    preflight_push_session_branch.decide,
    preflight_push_nonempty.decide,
)


def decide(event: dict[str, Any]) -> Mapping[str, Any] | None:
    """Return the first push gate's deny dict, or None to allow the push.

    Delegates to each gate's own ``decide`` in the fixed order, returning the
    first deny. The dispatcher adds no detection prefilter of its own: each gate
    self-detects (a non-Bash tool, an empty command, or a non-push command makes
    every gate return None), so a gate fires on exactly the commands it fired on
    as a standalone process and its deny text and fail-open posture are
    preserved.
    """
    for check in _CHECKS:
        decision = check(event)
        if decision is not None:
            return decision
    return None


def main(argv: list[str] | None = None) -> int:
    """CLI entry. Configuration is via stdin JSON (PreToolUse hook event).

    ``auditable=False`` so ``CLAUDE_GATE_MODE=audit`` cannot suppress any push
    deny this dispatcher surfaces (each consolidated gate carried the same
    posture).
    """
    del argv
    return run_event_hook("preflight_push_dispatch", decide, auditable=False)


if __name__ == "__main__":
    raise SystemExit(main())
