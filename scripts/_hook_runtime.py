"""Shared PreToolUse/PostToolUse hook I/O runtime.

Every client-side gate under ``scripts/`` follows the same wire protocol with
the Claude Code hook harness: the event JSON arrives on stdin, and a decision
payload (or nothing) is written to stdout. Historically each gate's ``main()``
re-implemented that plumbing -- read stdin, parse JSON, emit a
``::error::<gate>: malformed stdin JSON`` line and exit 0 on a parse failure
(fail-open per CLAUDE.md section 4), then serialise the decision with
``json.dumps``. This module owns that plumbing once so each gate keeps only its
own ``decide(...)`` logic and deny-reason builders.

No decision rule lives here: deny-reason text, detection regexes,
classification, and tool-name extraction stay in the individual gates. Only the
stdin -> parse -> stdout contract moves in, byte-for-byte:

- :func:`read_event` reproduces the exact ``::error::<script>: malformed stdin
  JSON: <exc>`` stderr line and the empty-stdin -> ``{}`` behaviour.
- :func:`emit_decision` reproduces ``sys.stdout.write(json.dumps(decision))``
  and the "write nothing when the decision is ``None``" behaviour.

Both functions touch ``sys.stdin``/``sys.stdout``/``sys.stderr`` at call time so
the existing tests that monkeypatch those streams keep working unchanged.

Refs #1005.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Callable, Mapping
from typing import Any

_GATE_MODE_ENV = "CLAUDE_GATE_MODE"
_AUDIT_MODE = "audit"


def _audit_mode_active() -> bool:
    """Return ``True`` when ``CLAUDE_GATE_MODE`` selects audit (record-and-pass).

    Default (unset) and any value other than ``audit`` keep the original
    ``block`` behavior, so audit is a deliberate opt-in set via the Environment
    env vars (Claude Code on the web). Comparison is case-insensitive and
    whitespace-trimmed so ``Audit`` / `` audit `` still match.
    """
    return os.environ.get(_GATE_MODE_ENV, "").strip().lower() == _AUDIT_MODE


def _blocking_reason(decision: Mapping[str, Any]) -> str | None:
    """Return the reason text when *decision* blocks a tool call or stop.

    Recognises every blocking wire shape the client-side gates emit:

    - Stop block:          ``{"decision": "block", "reason": ...}``
    - PreToolUse deny, wrapped (``build_deny``):
      ``{"hookSpecificOutput": {"permissionDecision": "deny",
      "permissionDecisionReason": ...}}``
    - PreToolUse deny, flat (e.g. ``gate_gh_cli`` / ``gate_update_pr_branch``):
      ``{"permissionDecision": "deny", "decisionReason": ...}``

    Returns ``None`` for any non-blocking decision (allow, pass-through, or a
    PostToolUse payload), which audit mode never downgrades.
    """
    if decision.get("decision") == "block":
        return str(decision.get("reason", ""))
    hook_output = decision.get("hookSpecificOutput")
    if isinstance(hook_output, dict) and hook_output.get("permissionDecision") == "deny":
        return str(hook_output.get("permissionDecisionReason", ""))
    if decision.get("permissionDecision") == "deny":
        return str(decision.get("decisionReason", decision.get("permissionDecisionReason", "")))
    return None


def read_event(script_name: str) -> dict[str, Any] | None:
    """Read and parse the hook event JSON from stdin.

    Returns the parsed event dict on success. Empty (or whitespace-only) stdin
    yields an empty dict ``{}`` -- the same off-target pass-through the gates
    relied on. On malformed JSON the function logs

        ``::error::<script_name>: malformed stdin JSON: <exc>``

    to stderr and returns ``None`` so the caller can fail open (``return 0``).
    The ``None`` sentinel is distinct from the falsy-but-valid empty dict, so a
    caller can tell a parse failure apart from an empty event.
    """
    raw = sys.stdin.read()
    try:
        return json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(
            f"::error::{script_name}: malformed stdin JSON: {exc}",
            file=sys.stderr,
        )
        return None


def emit_decision(
    decision: Mapping[str, Any] | None,
    script_name: str | None = None,
    *,
    auditable: bool = True,
) -> None:
    """Write *decision* to stdout as compact JSON, or nothing when ``None``.

    Mirrors the ``if decision is not None: sys.stdout.write(json.dumps(...))``
    tail every gate ended with -- no trailing newline, default ``json.dumps``
    separators -- so the bytes the harness reads are unchanged in the default
    (``block``) mode.

    Audit mode (``CLAUDE_GATE_MODE=audit``): when *auditable* is ``True`` (the
    default, for governance / workflow gates) a *blocking* decision is
    downgraded to pass-through -- nothing is written to stdout, and a single
    ``::warning::<script_name>: [AUDIT] suppressed blocking decision`` line
    naming the suppressed reason is emitted to stderr so the would-be block is
    auditable rather than silently dropped. Security-boundary gates pass
    ``auditable=False`` so the env var can never disable them. Non-blocking
    decisions are emitted unchanged in every mode.
    """
    if decision is None:
        return
    if auditable and _audit_mode_active():
        reason = _blocking_reason(decision)
        if reason is not None:
            label = script_name or "gate"
            print(
                f"::warning::{label}: [AUDIT] suppressed blocking decision "
                f"({_GATE_MODE_ENV}={_AUDIT_MODE}): {reason}",
                file=sys.stderr,
            )
            return
    sys.stdout.write(json.dumps(decision))


def build_deny(reason: str) -> dict[str, Any]:
    """Return the standard PreToolUse deny payload for *reason*.

    Centralises the ``hookSpecificOutput`` / ``permissionDecision="deny"`` dict
    that the client-side gates emit to block a tool call. The literal was copied
    byte-for-byte across gates (e.g. ``preflight_push_base._deny`` and
    ``preflight_push_nonempty._deny`` were identical); this is the single
    definition. The wire shape is unchanged.
    """
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def split_tool_event(event: Mapping[str, Any], script_name: str) -> tuple[str, dict[str, Any]] | None:
    """Return ``(tool_name, tool_input)`` from a PreToolUse *event*, or ``None``.

    On a missing or ill-typed ``tool_name`` / ``tool_input`` shape, emits the
    byte-identical line

        ``::error::<script_name>: event missing tool_name/tool_input``

    to stderr and returns ``None`` so the caller fails open (``return 0`` per
    CLAUDE.md section 4). Reproduces the per-gate guard exactly.
    """
    tool_name = event.get("tool_name")
    tool_input = event.get("tool_input") or {}
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        print(
            f"::error::{script_name}: event missing tool_name/tool_input",
            file=sys.stderr,
        )
        return None
    return tool_name, tool_input


def run_event_hook(
    script_name: str,
    decide: Callable[[dict[str, Any]], Mapping[str, Any] | None],
    *,
    auditable: bool = True,
) -> int:
    """PreToolUse entry point that passes the whole event to *decide*.

    ``read_event`` -> ``decide(event)`` -> ``emit_decision``. Always returns 0
    (fail-open): a malformed-JSON or non-dict event yields no decision (the
    malformed-JSON stderr line is produced by :func:`read_event`). For gates
    whose ``decide`` consumes the raw event (the push/commit family).

    *auditable* is forwarded to :func:`emit_decision`; security-boundary gates
    pass ``auditable=False`` so ``CLAUDE_GATE_MODE=audit`` cannot disable them.
    """
    event = read_event(script_name)
    if event is None or not isinstance(event, dict):
        return 0
    emit_decision(decide(event), script_name, auditable=auditable)
    return 0


def run_tool_hook(
    script_name: str,
    decide: Callable[[str, dict[str, Any]], Mapping[str, Any] | None],
    *,
    auditable: bool = True,
) -> int:
    """PreToolUse entry point that splits the tool fields for *decide*.

    ``read_event`` -> :func:`split_tool_event` ->
    ``decide(tool_name, tool_input)`` -> ``emit_decision``. Always returns 0
    (fail-open): a malformed-JSON, non-dict, or missing-shape event yields no
    decision (the matching stderr line is produced by
    :func:`read_event` / :func:`split_tool_event`). For gates whose ``decide``
    takes ``(tool_name, tool_input)``.

    *auditable* is forwarded to :func:`emit_decision`; security-boundary gates
    pass ``auditable=False`` so ``CLAUDE_GATE_MODE=audit`` cannot disable them.
    """
    event = read_event(script_name)
    if event is None or not isinstance(event, dict):
        return 0
    split = split_tool_event(event, script_name)
    if split is None:
        return 0
    emit_decision(decide(*split), script_name, auditable=auditable)
    return 0
