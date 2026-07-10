#!/usr/bin/env python3
"""PreToolUse dispatcher: run every ``git push`` client-side gate in one process.

Refs #2410 (child of the FTA/FMEA tracking issue #2408). A single ``git push``
Bash call previously spawned one PreToolUse process per push-specific gate
(``preflight_push_unsigned_commits`` -> ``preflight_push_base`` ->
``preflight_push_session_branch`` -> ``preflight_push_nonempty``), each with its
own registration in ``scripts/agent_hooks_source.json`` and its own ``git push``
detection regex. That one-check-one-process-one-registration shape generated the
drift classes the FTA/FMEA record files:

* F7 (the wiring single-point-of-failure): four separate registrations to keep
  in step per agent target.
* F10 (three divergent push-detection regexes): ``preflight_push_prek.py`` (since
  deleted with #901) lacked the ``rtk`` prefix the wired gates carry.

This dispatcher collapses the wiring without touching any check's semantics. It
owns the SINGLE ``git push`` detection entry (the ``rtk``-optional
:data:`_GIT_PUSH_RE`, identical to the regex every remaining push gate already
uses) and then calls the existing pure ``decide()`` functions in the current
fixed order with first-deny-wins. Each imported ``decide`` still re-derives its
own detection, refspec parsing, and fail-open posture internally, so its deny
text and failure behaviour are preserved BYTE-FOR-BYTE: the dispatcher only
changes how the checks are wired, never what they decide.

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
through (return None); each delegated ``decide`` keeps its own wide fail-open on
infrastructure errors. Always exits 0.

Tested by ``tests/test_preflight_push_dispatch.py``.
"""

from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from typing import Any

import preflight_push_base
import preflight_push_nonempty
import preflight_push_session_branch
import preflight_push_unsigned_commits
from _hook_runtime import run_event_hook

# The single ``git push`` detection entry the dispatcher owns. Optional ``rtk``
# prefix: the rtk auto-rewrite PreToolUse hook rewrites ``git push`` ->
# ``rtk git push`` (Refs #1199), so the gate must fire on both forms. This is the
# identical regex every remaining push gate already carries; owning it once here
# is what makes the F10 three-regex drift class structurally impossible.
_GIT_PUSH_RE = re.compile(r"(?m)^\s*(?:rtk\s+)?git\s+push\b")

# Command surface this hook acts on, read by scan_hook_predicate_surface_drift.py
# to verify the Bash(*git push*) if: predicate admits it (a narrower predicate
# would silently skip a command the script handles, the PR #2120 class). Refs #2133.
HOOK_GIT_SUBCOMMANDS = frozenset({"push"})

# The push gates in their fixed evaluation order (the claude registration order
# this dispatcher replaces). first-deny-wins: the first check that returns a deny
# dict short-circuits, so the deny the agent sees is byte-identical to the deny
# that gate emitted when it was a standalone process.
_Check = Callable[[dict[str, Any]], Mapping[str, Any] | None]
_CHECKS: tuple[_Check, ...] = (
    preflight_push_unsigned_commits.decide,
    preflight_push_base.decide,
    preflight_push_session_branch.decide,
    preflight_push_nonempty.decide,
)


def decide(event: dict[str, Any]) -> Mapping[str, Any] | None:
    """Return the first push gate's deny dict, or None to allow the push.

    The dispatcher's single ``_GIT_PUSH_RE`` gate is the sole push-detection
    entry; a non-Bash tool, an empty command, or a non-push command fast-passes
    exactly as each individual gate did. Every delegated ``decide`` is called
    unchanged, so its deny text and fail-open behaviour are preserved.
    """
    if event.get("tool_name") != "Bash":
        return None
    command = str((event.get("tool_input") or {}).get("command") or "")
    if not _GIT_PUSH_RE.search(command):
        return None

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
