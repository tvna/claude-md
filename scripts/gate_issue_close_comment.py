#!/usr/bin/env python3
"""PreToolUse gate and PostToolUse recorder for issue-close comment enforcement.

**PreToolUse gate** (default mode)
-----------------------------------
Registered on ``mcp__github__issue_write``.  When the tool input contains
``state: "closed"``, checks whether a comment was posted to the same issue
number in the current session by inspecting a tmp-file tracker.

- Comment recorded → allow (no output; the tool call proceeds normally).
- No comment recorded → deny with a redirect message instructing the agent
  to post a closing comment first.
- Parse error / unexpected exception → fail-open (exit 0).

**PostToolUse recorder** (``--record`` mode)
---------------------------------------------
Registered on ``mcp__github__add_issue_comment`` and
``mcp__github__add_reply_to_pull_request_comment``.  Reads the tool input
from stdin, extracts ``issue_number``, and writes a marker file under
``/tmp/claude-issue-comments/`` so the gate can verify it later.

Fail-open on all errors; a recorder bug must never wedge the session.
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


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _marker_path(issue_number: int | str) -> Path:
    return _COMMENT_DIR / str(issue_number)


# ---------------------------------------------------------------------------
# Gate (PreToolUse)
# ---------------------------------------------------------------------------


def _extract_close_target(
    tool_name: str,
    tool_input: dict[str, Any],
) -> int | None:
    """Return *issue_number* if this is a close action, else ``None``."""
    if tool_name != _TARGET_TOOL:
        return None
    if tool_input.get("state") != _CLOSE_STATE:
        return None
    raw = tool_input.get("issue_number")
    if isinstance(raw, int) and raw > 0:
        return raw
    if isinstance(raw, str) and raw.isdecimal():
        return int(raw)
    return None


def decide(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:
    """Return a hook decision dict, or ``None`` when no action is needed.

    Returns a ``permissionDecision: deny`` dict when a close is attempted
    without a prior session comment, or ``None`` to allow.
    """
    issue_number = _extract_close_target(tool_name, tool_input)
    if issue_number is None:
        return None

    if _marker_path(issue_number).exists():
        return None

    return {
        "permissionDecision": "deny",
        "decisionReason": (
            f"GATE DENY: issue #{issue_number} has no closing comment recorded "
            "in this session.  Post a comment explaining the closure reason "
            "via mcp__github__add_issue_comment before calling issue_write with "
            "state: closed.  The comment will be tracked automatically."
        ),
    }


def run_gate() -> int:
    event = read_event("gate_issue_close_comment")
    if event is None or not isinstance(event, dict):
        return 0

    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    emit_decision(decide(tool_name, tool_input))
    return 0


# ---------------------------------------------------------------------------
# Recorder (PostToolUse)
# ---------------------------------------------------------------------------


def _extract_issue_number(tool_input: dict[str, Any]) -> int | None:
    raw = tool_input.get("issue_number")
    if isinstance(raw, int) and raw > 0:
        return raw
    if isinstance(raw, str) and raw.isdecimal():
        return int(raw)
    return None


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
