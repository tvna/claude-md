"""Tests for the Codex hook configuration.

Refs #606.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_preflight

ROOT = Path(__file__).resolve().parents[1]
CODEX_HOOKS = ROOT / ".codex" / "hooks.json"
CORE_HOOK_EVENTS = {"SessionStart", "PreToolUse", "PostToolUse"}


def _load_hooks() -> dict[str, object]:
    data = json.loads(CODEX_HOOKS.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _command_entries(data: dict[str, object]) -> list[dict[str, object]]:
    hooks = data["hooks"]
    assert isinstance(hooks, dict)
    entries: list[dict[str, object]] = []
    for groups in hooks.values():
        assert isinstance(groups, list)
        for group in groups:
            assert isinstance(group, dict)
            if group.get("_apm_source") == "superpowers" and "command" in group:
                entries.append(group)
                continue
            handlers = group["hooks"]
            assert isinstance(handlers, list)
            for handler in handlers:
                assert isinstance(handler, dict)
                entries.append(handler)
    return entries


def _repo_script_from_command(command: str) -> str:
    for token in command.split():
        if token.startswith("scripts/"):
            return token
    return command.split()[-1]


def test_codex_hooks_json_is_valid() -> None:
    data = _load_hooks()
    hooks = data.get("hooks")
    assert isinstance(hooks, dict)
    assert set(hooks) >= CORE_HOOK_EVENTS
    unexpected = set(hooks) - CORE_HOOK_EVENTS - {"sessionStart"}
    assert not unexpected


def test_all_codex_hook_commands_point_to_repo_files() -> None:
    data = _load_hooks()
    commands = [entry["command"] for entry in _command_entries(data)]
    assert commands
    for command in commands:
        assert isinstance(command, str)
        if "CLAUDE_PLUGIN_ROOT" in command or command == "./hooks/run-hook.cmd session-start":
            continue
        path = _repo_script_from_command(command)
        assert not path.startswith("/")
        assert (ROOT / path).exists()


def test_codex_superpowers_hooks_are_apm_managed() -> None:
    data = _load_hooks()
    hooks = data["hooks"]
    assert isinstance(hooks, dict)

    session_start = hooks["SessionStart"]
    assert isinstance(session_start, list)
    assert any(
        isinstance(group, dict)
        and group.get("_apm_source") == "superpowers"
        and isinstance(group.get("matcher"), str)
        and "startup" in group["matcher"]
        for group in session_start
    )

    legacy_session_start = hooks.get("sessionStart")
    assert isinstance(legacy_session_start, list)
    assert legacy_session_start == [
        {
            "command": "./hooks/run-hook.cmd session-start",
            "_apm_source": "superpowers",
        }
    ]


def test_codex_pre_tool_use_covers_claude_github_write_hooks() -> None:
    data = _load_hooks()
    hooks = data["hooks"]
    assert isinstance(hooks, dict)
    pre_tool_use = hooks["PreToolUse"]
    assert isinstance(pre_tool_use, list)

    commands: list[str] = []
    matchers: list[str] = []
    for group in pre_tool_use:
        assert isinstance(group, dict)
        matcher = group["matcher"]
        handlers = group["hooks"]
        assert isinstance(matcher, str)
        assert isinstance(handlers, list)
        matchers.append(matcher)
        for handler in handlers:
            command = handler["command"]
            assert isinstance(command, str)
            commands.append(command)

    assert "^mcp__github__(issue_write|add_issue_comment|create_pull_request|update_pull_request|add_reply_to_pull_request_comment|pull_request_review_write|add_comment_to_pending_review|sub_issue_write)$" in matchers
    assert "^mcp__github__(issue_write|add_issue_comment|create_pull_request|update_pull_request|add_reply_to_pull_request_comment|pull_request_review_write|add_comment_to_pending_review)$" in matchers
    assert "python3 scripts/preflight_non_ascii.py" in commands
    assert "python3 scripts/preflight_codex_github_footer.py" in commands
    assert "python3 scripts/pr_body_close_keyword_gate.py" in commands
    assert "python3 scripts/preflight_title_policy.py" in commands
    assert "python3 scripts/preflight_pr_body_required_sections.py" in commands
    assert "python3 scripts/preflight_pr_template_shape.py" in commands
    assert "python3 scripts/preflight_branch_base.py verify" in commands


def test_codex_pr_write_hooks_match_claude_base_freshness_gate() -> None:
    data = _load_hooks()
    hooks = data["hooks"]
    assert isinstance(hooks, dict)
    pre_tool_use = hooks["PreToolUse"]
    assert isinstance(pre_tool_use, list)

    matching = [
        group
        for group in pre_tool_use
        if isinstance(group, dict)
        and group.get("matcher") == "^mcp__github__(create_pull_request|update_pull_request)$"
    ]
    assert matching
    assert any(
        isinstance(handlers := group.get("hooks"), list)
        and any(
            isinstance(handler, dict)
            and handler.get("command") == "python3 scripts/preflight_branch_base.py verify"
            for handler in handlers
        )
        for group in matching
    )


def test_codex_post_tool_use_starts_ci_monitor_after_mcp_pr_create() -> None:
    data = _load_hooks()
    hooks = data["hooks"]
    assert isinstance(hooks, dict)
    post_tool_use = hooks["PostToolUse"]
    assert isinstance(post_tool_use, list)

    commands: list[str] = []
    matchers: list[str] = []
    for group in post_tool_use:
        assert isinstance(group, dict)
        matcher = group["matcher"]
        handlers = group["hooks"]
        assert isinstance(matcher, str)
        assert isinstance(handlers, list)
        matchers.append(matcher)
        for handler in handlers:
            command = handler["command"]
            assert isinstance(command, str)
            commands.append(command)

    assert "^mcp__github__create_pull_request$" in matchers
    assert "python3 scripts/post_pr_create_ci_monitor.py" in commands
    assert "python3 scripts/ci_early_status_probe.py" in commands
