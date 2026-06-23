#!/usr/bin/env python3
"""Stop hook: nudge delegated decisions toward the AskUserQuestion tool.

When the agent ends its turn by handing a decision back to the user in
free-form chat; outside plan mode and without having used the
structured single-select question tool; this hook returns a Stop
``decision: block`` with a reason telling the agent to re-present the
choice through that tool so the options are inspectable rather than
buried in prose.

This is the hook home for the behaviour that must NOT live in the
universal instruction text: naming a concrete, harness-specific tool
(AskUserQuestion) belongs in a Claude-only hook, not in
``.apm/instructions/master.instructions.md`` (which compiles to
``CLAUDE.md`` and ``AGENTS.md`` for agents that have no such tool). The
hook is therefore registered only under ``.claude/settings.json`` and is
intentionally absent from ``.codex/hooks.json`` /
``.devin/hooks.v1.json``. The ``Stop`` event is outside the
``scan_hook_coverage_drift`` parity scope (which compares only
SessionStart / PreToolUse / PostToolUse), so this asymmetry is by design.

A hook cannot force a tool call; the only available lever is to block the
stop and feed a reason back to the agent, which then re-emits. Detection
is therefore a best-effort heuristic and is deliberately conservative to
limit false positives:

* ``stop_hook_active`` true -> no-op. The harness sets this when the stop
  is already a continuation triggered by a prior block, so re-blocking
  would loop.
* The final assistant turn already used ``AskUserQuestion`` -> no-op
  (the goal is met).
* The final assistant turn used ``ExitPlanMode`` -> no-op. A Stop hook
  cannot read the plan-mode flag directly; the presence of an
  ExitPlanMode call is the closest transcript proxy for the plan-mode
  handoff path, which the owner scoped out ("outside plan mode").
* Otherwise block only when the last assistant text block both contains
  a question mark AND signals a *choice* (a choice cue word or an
  enumerated option list of two or more items). Plain yes/no
  clarifications are intentionally NOT matched, to keep friction low;
  widen :data:`CHOICE_CUES` or the enumeration rule if that proves too
  narrow.

Fails open per CLAUDE.md section 4: any missing field, unreadable
transcript, or parse error exits 0 with no output. A hook bug must never
wedge the session.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

from _hook_runtime import emit_decision, read_event

_SCRIPT_NAME = "gate_decision_handoff_askuserquestion"

# Tool whose use in the final turn means the goal is already met.
_STRUCTURED_QUESTION_TOOL = "AskUserQuestion"
# Tool whose use marks the plan-mode handoff path, scoped out by the owner.
_PLAN_MODE_TOOL = "ExitPlanMode"

# Choice-cue substrings (matched case-insensitively). A delegated
# decision is signalled by offering a choice, which these words mark.
# Kept narrow on purpose; plain politeness ("...しますか?") is excluded so
# every routine question does not trip the gate.
CHOICE_CUES: tuple[str, ...] = (
    "どちら",
    "どれ",
    "いずれ",
    "選択",
    "選んで",
    "which",
    "prefer",
    "option",
    "choose",
)

# An option line: a bullet, a numbered item, or a lettered item (A./A)).
_OPTION_LINE_RE = re.compile(r"^\s*(?:[-*]|\d+[.)]|[A-Za-z][.)])\s+\S")

_BLOCK_REASON = (
    "A decision was delegated to the user in chat outside plan mode "
    "without using the AskUserQuestion tool. Re-present this decision "
    "with AskUserQuestion (structured single-select options) so the "
    "choice and its options are inspectable, instead of free-form prose."
)


def _content_blocks(entry: object) -> list[dict[str, Any]]:
    """Return the list of content blocks for a transcript entry, or []."""
    if not isinstance(entry, dict):
        return []
    message = entry.get("message")
    if not isinstance(message, dict):
        return []
    content = message.get("content")
    if isinstance(content, list):
        return [block for block in content if isinstance(block, dict)]
    return []


def _entry_role(entry: object) -> str:
    """Return the role of a transcript entry ('user' / 'assistant' / '')."""
    if not isinstance(entry, dict):
        return ""
    message = entry.get("message")
    if isinstance(message, dict):
        role = message.get("role")
        if isinstance(role, str):
            return role
    entry_type = entry.get("type")
    return entry_type if isinstance(entry_type, str) else ""


def final_assistant_turn(entries: list[Any]) -> list[Any]:
    """Return the assistant entries that follow the last user message.

    The "turn" is everything the assistant emitted since the user last
    spoke. An empty list means no assistant output to judge.
    """
    last_user = -1
    for idx, entry in enumerate(entries):
        if _entry_role(entry) == "user":
            last_user = idx
    return [entry for entry in entries[last_user + 1 :] if _entry_role(entry) == "assistant"]


def turn_used_tool(turn: list[Any], tool_name: str) -> bool:
    """Return True when any block in *turn* is a tool_use of *tool_name*."""
    for entry in turn:
        for block in _content_blocks(entry):
            if block.get("type") == "tool_use" and block.get("name") == tool_name:
                return True
    return False


def last_text_block(turn: list[Any]) -> str:
    """Return the text of the last text block in *turn*, or ''."""
    text = ""
    for entry in turn:
        for block in _content_blocks(entry):
            if block.get("type") == "text" and isinstance(block.get("text"), str):
                text = block["text"]
    return text


def _enumerated_option_count(text: str) -> int:
    return sum(1 for line in text.splitlines() if _OPTION_LINE_RE.match(line))


def delegates_decision(text: str) -> bool:
    """Heuristic: does *text* hand a choice back to the user?

    Requires a question mark AND a choice signal (a cue word or an
    enumerated list of two or more options). Conservative by design.
    """
    if not text:
        return False
    if "?" not in text and "？" not in text:
        return False
    lowered = text.lower()
    if any(cue in lowered for cue in CHOICE_CUES):
        return True
    return _enumerated_option_count(text) >= 2


def evaluate(event: dict[str, Any], entries: list[Any]) -> dict[str, Any] | None:
    """Return a Stop block decision, or None to let the stop proceed."""
    if event.get("hook_event_name") not in (None, "Stop"):
        return None
    if event.get("stop_hook_active"):
        return None
    turn = final_assistant_turn(entries)
    if not turn:
        return None
    if turn_used_tool(turn, _STRUCTURED_QUESTION_TOOL):
        return None
    if turn_used_tool(turn, _PLAN_MODE_TOOL):
        return None
    if not delegates_decision(last_text_block(turn)):
        return None
    return {"decision": "block", "reason": _BLOCK_REASON}


def load_transcript(path_value: object) -> list[Any]:
    """Read a JSONL transcript into a list of entries; [] on any failure."""
    if not isinstance(path_value, str) or not path_value:
        return []
    path = Path(path_value)
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    entries: list[Any] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def main() -> int:
    event = read_event(_SCRIPT_NAME)
    if event is None:
        return 0
    try:
        entries = load_transcript(event.get("transcript_path"))
        decision = evaluate(event, entries)
    except Exception as exc:  # fail open: never wedge the session on a hook bug
        print(f"::error::{_SCRIPT_NAME}: {exc}", file=sys.stderr)
        return 0
    emit_decision(decision, _SCRIPT_NAME)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
