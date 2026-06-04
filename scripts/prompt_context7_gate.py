"""UserPromptSubmit hook: remind agents to prefer context7 for docs lookups.

Refs #1213. This hook is intentionally local and deterministic: it does not
call context7 itself, and it never blocks prompts. It only adds concise context
when the submitted prompt appears to require primary-source library or API
documentation.
"""

from __future__ import annotations

import re
import sys
from collections.abc import Mapping
from typing import Any

from _hook_runtime import emit_decision, read_event

CONTEXT7_REMINDER = (
    "Primary-source documentation lookup appears relevant. Prefer context7 for "
    "library/API documentation before broader model-side search; fall back to "
    "official web search when context7 is unavailable, stale, or out of scope."
)

_LOOKUP_TERMS = re.compile(
    r"(?i)\b("
    r"context7|primary[- ]source|official docs?|documentation|docs?|api|sdk|"
    r"library|libraries|framework|latest docs?|up-to-date|version-specific"
    r")\b|一次情報|一時情報|公式資料|公式ドキュメント|公式docs|最新ドキュメント"
)


def _prompt_text(event: Mapping[str, Any]) -> str:
    prompt = event.get("prompt")
    return prompt if isinstance(prompt, str) else ""


def should_remind(event: Mapping[str, Any]) -> bool:
    """Return whether *event* should receive the context7 reminder."""
    if event.get("hook_event_name") != "UserPromptSubmit":
        return False
    prompt = _prompt_text(event)
    return bool(prompt and _LOOKUP_TERMS.search(prompt))


def decide(event: Mapping[str, Any]) -> dict[str, Any] | None:
    """Build the hook decision for a UserPromptSubmit event."""
    if not should_remind(event):
        return None
    return {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": CONTEXT7_REMINDER,
        }
    }


def main(argv: list[str] | None = None) -> int:
    """Read hook JSON from stdin and emit optional additional context."""
    del argv
    event = read_event("prompt_context7_gate")
    if event is None:
        return 0
    emit_decision(decide(event))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
