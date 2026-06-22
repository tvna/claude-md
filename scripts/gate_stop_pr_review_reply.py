#!/usr/bin/env python3
"""Stop hook: block the turn until every review-comment webhook has a reply.

When this session receives a pull request review-comment webhook (delivered
as a ``<github-webhook-activity>`` user message), the agent must post at
least one GitHub reply tool call before ending its turn. This hook scans
the session transcript for such webhooks and blocks the Stop event when
any have no subsequent reply tool call.

Why a Stop hook rather than instruction text
--------------------------------------------
This enforcement belongs in the harness, not in universal instruction
text (``master.instructions.md``), for two reasons:

1. ``mcp__github__add_reply_to_pull_request_comment`` and its siblings are
   Claude Code-only affordances. Naming them in universal text (which
   compiles to ``CLAUDE.md`` and ``AGENTS.md``) would pollute agents that
   have no such tools.
2. A Stop hook is deterministic: it fails when the condition is not met
   rather than relying on the agent to recall and act on a text rule.

Claude-only gate: the hook is registered only in ``.claude/settings.json``
and is intentionally absent from ``.codex/hooks.json`` / ``.devin/hooks.v1.json``.
The ``Stop`` event is outside ``scan_hook_coverage_drift`` parity scope
(which compares only SessionStart / PreToolUse / PostToolUse), so the
asymmetry is by design.

Detection heuristic (fail-open, no network calls)
-------------------------------------------------
* ``stop_hook_active`` true -> no-op (avoid re-blocking loops).
* User messages carrying ``<github-webhook-activity>`` content that contains
  one of the :data:`REVIEW_MARKERS` strings are classified as review-comment
  webhook events. This is conservative: CI and push events lack these markers.
* A subsequent (later in transcript) assistant tool_use call with a name in
  :data:`REPLY_TOOLS` counts as "addressed". The earliest such call satisfies
  the check; N webhooks need not each have an exactly paired reply call -- one
  reply call in scope clears all webhooks seen before it.
* Any missing field, unreadable transcript, or exception exits 0 (fail open).
  A gate bug must never wedge the session (CLAUDE.md section 4).

Tested by ``tests/test_gate_stop_pr_review_reply.py``. Refs #1768.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from _hook_runtime import emit_decision, read_event

_SCRIPT_NAME = "gate_stop_pr_review_reply"

# Substrings that identify a pull-request review-comment webhook event.
# Intentionally specific to review event types; CI and push webhooks lack them.
# Two marker sets cover the same events on different surfaces:
#   - API-style (underscore): raw GitHub webhook payload field names, present
#     when the system embeds the raw payload body.
#   - System-description prefix: the Claude Code system injects an exact header
#     "The following is a GitHub review[...] left on the PR." before the
#     user-authored comment body. Matching this full prefix (not a short
#     substring like "review comment") avoids false positives when the
#     user-authored comment body happens to mention review-related words.
# Both sets must be present so the gate fires on either format. Refs #1860.
REVIEW_MARKERS: tuple[str, ...] = (
    "REVIEW_COMMENT",
    "review_comment",
    "changes_requested",
    "Changes requested",
    "pull_request_review",
    "The following is a GitHub review",  # matches system description header
)

# Tool names that count as posting a reply to a review thread.
REPLY_TOOLS: frozenset[str] = frozenset(
    {
        "mcp__github__add_reply_to_pull_request_comment",
        "mcp__github__add_comment_to_pending_review",
        "mcp__github__pull_request_review_write",
    }
)

_BLOCK_REASON = (
    "GATE BLOCK: this session received a pull request review-comment webhook "
    "that has no subsequent reply via a GitHub comment tool "
    "(mcp__github__add_reply_to_pull_request_comment or equivalent). "
    "For every open review thread contributing to or causing a merge block, "
    "post a reply before ending the turn -- regardless of whether the outcome "
    "is a code fix, a won't-fix decision, or an acknowledgement. "
    "A reply citing the fix commit SHA (when applicable) or stating the "
    "disposition closes the review loop visibly; without it, the reviewer "
    "cannot tell the comment was seen. Address all such threads, then end "
    "the turn. Refs #1768."
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


def _entry_text(entry: object) -> str:
    """Return the full text content of a transcript entry."""
    if not isinstance(entry, dict):
        return ""
    message = entry.get("message")
    if not isinstance(message, dict):
        return ""
    content = message.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                text = block.get("text")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(parts)
    return ""


def is_review_webhook(entry: object) -> bool:
    """Return True if *entry* is a user message containing a review-comment webhook."""
    if _entry_role(entry) != "user":
        return False
    text = _entry_text(entry)
    if "<github-webhook-activity>" not in text:
        return False
    return any(marker in text for marker in REVIEW_MARKERS)


def has_reply_tool_call(entries: list[Any], after_idx: int) -> bool:
    """Return True if a reply tool was called in *entries* after *after_idx*."""
    for entry in entries[after_idx + 1 :]:
        for block in _content_blocks(entry):
            if block.get("type") == "tool_use" and block.get("name") in REPLY_TOOLS:
                return True
    return False


def find_unaddressed_review_webhooks(entries: list[Any]) -> list[int]:
    """Return indices of review webhook events with no subsequent reply tool call."""
    return [
        idx
        for idx, entry in enumerate(entries)
        if is_review_webhook(entry) and not has_reply_tool_call(entries, idx)
    ]


def evaluate(event: dict[str, Any], entries: list[Any]) -> dict[str, Any] | None:
    """Return a Stop block decision, or None to let the stop proceed."""
    if event.get("hook_event_name") not in (None, "Stop"):
        return None
    if event.get("stop_hook_active"):
        return None
    if not find_unaddressed_review_webhooks(entries):
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
