#!/usr/bin/env python3
"""Codex PreToolUse hook: require provenance footers on GitHub posts.

The hook is registered only in ``.codex/hooks.json``. It enforces a
Codex-specific footer for GitHub MCP write tools that carry a text
``body`` field, while leaving Claude Code hook behavior unchanged.
Refs #622.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

from body_policy import build_codex_attribution_footer, verify_codex_attribution_footer

_TARGET_TOOLS: frozenset[str] = frozenset(
    {
        "mcp__github__issue_write",
        "mcp__github__add_issue_comment",
        "mcp__github__create_pull_request",
        "mcp__github__update_pull_request",
        "mcp__github__add_reply_to_pull_request_comment",
        "mcp__github__pull_request_review_write",
        "mcp__github__add_comment_to_pending_review",
    }
)
_MODEL_ENV_NAMES: tuple[str, ...] = (
    "CODEX_GITHUB_FOOTER_MODEL",
    "CODEX_MODEL",
    "OPENAI_MODEL",
    "AI_MODEL",
)
_EVENT_MODEL_KEYS: tuple[str, ...] = ("model", "model_name", "ai_model")


def extract_body(tool_input: dict[str, Any]) -> str | None:
    """Return the prose body when the tool input carries one."""
    body = tool_input.get("body")
    if body is None:
        return None
    if not isinstance(body, str):
        return ""
    return body


def _first_string(mapping: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def resolve_model(event: dict[str, Any], environ: dict[str, str] | None = None) -> str | None:
    """Return the Codex model identifier from trusted event/env metadata."""
    model = _first_string(event, _EVENT_MODEL_KEYS)
    if model is not None:
        return model

    metadata = event.get("metadata")
    if isinstance(metadata, dict):
        model = _first_string(metadata, _EVENT_MODEL_KEYS)
        if model is not None:
            return model

    env = os.environ if environ is None else environ
    for name in _MODEL_ENV_NAMES:
        value = env.get(name)
        if value and value.strip():
            return value.strip()
    return None


def build_deny_reason(errors: list[str], model: str | None) -> str:
    """Return the hook denial reason."""
    if model is None:
        return (
            "Blocked by scripts/preflight_codex_github_footer.py: Codex "
            "GitHub post is missing trusted model metadata. Set "
            "CODEX_GITHUB_FOOTER_MODEL to the non-secret model identifier "
            "or provide model metadata in the hook event before retrying."
        )
    try:
        expected = build_codex_attribution_footer(model)
    except ValueError as exc:
        expected = f"<invalid model: {exc}>"
    return (
        "Blocked by scripts/preflight_codex_github_footer.py: Codex "
        "GitHub post body must end with the provenance footer.\n"
        f"Expected final line:\n{expected}\n\n" + "\n".join(errors)
    )


def _deny(reason: str) -> dict[str, Any]:
    return {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }


def decide(
    tool_name: str,
    tool_input: dict[str, Any],
    event: dict[str, Any] | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any] | None:
    """Return the hook output dict, or ``None`` when the call may proceed."""
    if tool_name not in _TARGET_TOOLS:
        return None

    body = extract_body(tool_input)
    if body is None:
        return None

    event_data = {} if event is None else event
    model = resolve_model(event_data, environ)
    if model is None:
        return _deny(build_deny_reason([], None))

    errors = verify_codex_attribution_footer(body, model=model)
    if not errors:
        return None
    return _deny(build_deny_reason(errors, model))


def main(argv: list[str] | None = None) -> int:
    """Read PreToolUse JSON from stdin, write decision JSON to stdout."""
    del argv
    raw = sys.stdin.read()
    try:
        event = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError as exc:
        print(
            f"::error::preflight_codex_github_footer: malformed stdin JSON: {exc}",
            file=sys.stderr,
        )
        return 0

    tool_name = event.get("tool_name")
    tool_input = event.get("tool_input") or {}
    if not isinstance(tool_name, str) or not isinstance(tool_input, dict):
        print(
            "::error::preflight_codex_github_footer: event missing tool_name/tool_input",
            file=sys.stderr,
        )
        return 0

    decision = decide(tool_name, tool_input, event=event)
    if decision is None:
        return 0

    sys.stdout.write(json.dumps(decision))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
