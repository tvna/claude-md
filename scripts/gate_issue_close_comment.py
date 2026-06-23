#!/usr/bin/env python3
"""PreToolUse gate and PostToolUse recorder for issue-close comment enforcement.

**PreToolUse gate** (default mode)
-----------------------------------
Registered on ``mcp__github__issue_write``.  When the tool input contains
``state: "closed"``, checks whether a comment was posted to the same issue
number in the current session by inspecting a tmp-file tracker.

- Comment recorded -> allow (no output; the tool call proceeds normally).
- No comment recorded -> deny with a redirect message instructing the agent
  to post a closing comment first.
- ``state: "closed"`` but the issue number cannot be resolved to a positive
  integer -> deny (fail-closed, #1389): the closing-comment precondition
  cannot be verified, so an unverifiable close must not slip through
  (assume-breach).
- Malformed / non-object event -> deny (fail-closed, #1389). This hook binds
  only to ``mcp__github__issue_write``, so denying on an unparseable event
  blocks at most a single issue_write call, never unrelated tools; a
  fail-closed default here cannot "block all legitimate work".

Off-target calls (any tool other than ``issue_write``, or ``issue_write``
without ``state: "closed"``) always pass through untouched; the gate only
acts on a positively identified close attempt.

**PostToolUse recorder** (``--record`` mode)
---------------------------------------------
Registered on ``mcp__github__add_issue_comment`` and
``mcp__github__add_reply_to_pull_request_comment``.  Reads the tool input
from stdin, extracts ``issue_number``, and writes a marker file under
``/tmp/claude-issue-comments/`` so the gate can verify it later.

The recorder fails open on all errors: it issues no permission decision (it
only writes a marker file), so a recorder hiccup can never wedge the session.
The fail-closed posture above applies to the PreToolUse *gate*, which is the
control that could otherwise let an unverified close through.
"""

from __future__ import annotations

import argparse
import contextlib
from pathlib import Path
from typing import Any

from _hook_runtime import emit_decision, read_event

_TARGET_TOOL = "mcp__github__issue_write"
_CLOSE_STATE = "closed"
_COMMENT_DIR = Path("/tmp/claude-issue-comments")  # noqa: S108

_UNPARSEABLE_REASON = (
    "GATE DENY (fail-closed): the issue_write event could not be parsed, so "
    "the closing-comment precondition cannot be verified. An unverifiable "
    "close is denied (assume-breach). Retry with a well-formed call; if you "
    "intend to close an issue, post a closing comment via "
    "mcp__github__add_issue_comment first."
)

_UNRESOLVED_REASON = (
    "GATE DENY (fail-closed): issue_write requests state=closed but its "
    "issue_number could not be resolved to a positive integer, so the "
    "closing-comment precondition cannot be verified. Provide a valid "
    "issue_number and post a closing comment via "
    "mcp__github__add_issue_comment before closing."
)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _marker_path(issue_number: int | str) -> Path:
    return _COMMENT_DIR / str(issue_number)


def _deny(reason: str) -> dict[str, Any]:
    """Return the flat PreToolUse deny payload this gate emits."""
    return {"permissionDecision": "deny", "decisionReason": reason}


def _coerce_issue_number(raw: Any) -> int | None:
    """Return a positive issue number from *raw*, or ``None`` if unresolved.

    ``bool`` is rejected explicitly (``True``/``False`` are ``int`` instances
    in Python but never valid issue numbers).
    """
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int) and raw > 0:
        return raw
    if isinstance(raw, str) and raw.isdecimal() and int(raw) > 0:
        return int(raw)
    return None


# ---------------------------------------------------------------------------
# Gate (PreToolUse)
# ---------------------------------------------------------------------------


def _is_close_action(tool_name: str, tool_input: dict[str, Any]) -> bool:
    """Return ``True`` when this is an ``issue_write`` close attempt."""
    return tool_name == _TARGET_TOOL and tool_input.get("state") == _CLOSE_STATE


def decide(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:
    """Return a hook decision dict, or ``None`` when the call may proceed.

    - Off-target (not an ``issue_write`` close): ``None`` (pass through).
    - Close with a resolvable number and a recorded comment: ``None``.
    - Close with a resolvable number but no recorded comment: deny.
    - Close whose ``issue_number`` cannot be resolved: deny (fail-closed,
      #1389); the comment precondition cannot be checked, so the close is
      refused rather than allowed through.
    """
    if not _is_close_action(tool_name, tool_input):
        return None

    issue_number = _coerce_issue_number(tool_input.get("issue_number"))
    if issue_number is None:
        return _deny(_UNRESOLVED_REASON)

    if _marker_path(issue_number).exists():
        return None

    return _deny(
        f"GATE DENY: issue #{issue_number} has no closing comment recorded "
        "in this session.  Post a comment explaining the closure reason "
        "via mcp__github__add_issue_comment before calling issue_write with "
        "state: closed.  The comment will be tracked automatically."
    )


def run_gate() -> int:
    event = read_event("gate_issue_close_comment")
    if event is None or not isinstance(event, dict):
        # Fail-closed (#1389): a malformed or non-object event means the
        # closing-comment precondition cannot be verified. This hook is bound
        # to mcp__github__issue_write only, so denying here blocks at most a
        # single issue_write call, never unrelated tools.
        emit_decision(_deny(_UNPARSEABLE_REASON), "gate_issue_close_comment")
        return 0

    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        # No usable tool_input: there is no `state: closed` to act on, so this
        # is not an identifiable close attempt -> pass through (not a gap; the
        # gate only fires on a positively identified close).
        tool_input = {}

    emit_decision(decide(tool_name, tool_input), "gate_issue_close_comment")
    return 0


# ---------------------------------------------------------------------------
# Recorder (PostToolUse)
# ---------------------------------------------------------------------------


def _extract_issue_number(tool_input: dict[str, Any]) -> int | None:
    return _coerce_issue_number(tool_input.get("issue_number"))


def record(tool_input: dict[str, Any]) -> bool:
    """Write a marker file for *issue_number* extracted from *tool_input*.

    Returns ``True`` on success, ``False`` when the issue number is absent.
    """
    issue_number = _extract_issue_number(tool_input)
    if issue_number is None:
        return False
    _COMMENT_DIR.mkdir(parents=True, exist_ok=True)
    _marker_path(issue_number).touch()
    return True


def run_record() -> int:
    event = read_event("gate_issue_close_comment")
    if event is None or not isinstance(event, dict):
        return 0

    tool_input = event.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return 0

    with contextlib.suppress(OSError):
        record(tool_input)
    return 0


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Issue-close comment gate and recorder.",
        add_help=True,
    )
    parser.add_argument(
        "--record",
        action="store_true",
        help="PostToolUse recorder mode: mark an issue as commented.",
    )
    args = parser.parse_args(argv)
    if args.record:
        return run_record()
    return run_gate()


if __name__ == "__main__":
    raise SystemExit(main())
