#!/usr/bin/env python3
"""PostToolUse hook: prompt for plan approval after /tmp/claude-plans/*.md is written.

Emits a ``blockingPrompt`` asking the operator to approve the plan or
request changes, whenever a Write tool call targets a ``.md`` file
under ``/tmp/claude-plans/``. All other tool calls are a no-op.

Fails open per CLAUDE.md Sec.4: any parse error emits ``::error::``
to stderr and exits 0. A hook bug must not block the session.
"""

from __future__ import annotations

import json
import sys
from typing import Any

_PLAN_DIR = "/tmp/claude-plans/"  # noqa: S108


def _is_plan_write(tool_name: str, tool_input: dict[str, Any]) -> bool:
    if tool_name != "Write":
        return False
    path = str(tool_input.get("file_path", ""))
    return path.startswith(_PLAN_DIR) and path.endswith(".md")


def build_blocking_prompt(file_path: str) -> str:
    return (
        f"計画ファイル {file_path} が作成されました。\n\n"
        "承認する場合は「承認」、変更が必要な場合は変更内容を入力してください。"
    )


def decide(event: dict[str, Any]) -> dict[str, Any] | None:
    tool_name = event.get("tool_name", "")
    tool_input = event.get("tool_input", {})
    if not isinstance(tool_input, dict):
        return None
    if not _is_plan_write(tool_name, tool_input):
        return None
    file_path = str(tool_input.get("file_path", ""))
    return {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "blockingPrompt": build_blocking_prompt(file_path),
        }
    }


def main() -> int:
    try:
        raw = sys.stdin.read()
        if not raw.strip():
            return 0
        event = json.loads(raw)
        if not isinstance(event, dict):
            print(
                "::error::plan_approval_gate: event must be a JSON object",
                file=sys.stderr,
            )
            return 0
        result = decide(event)
        if result is not None:
            sys.stdout.write(json.dumps(result))
    except (json.JSONDecodeError, ValueError) as exc:
        print(f"::error::plan_approval_gate: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
