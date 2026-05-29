"""Tests for the Claude hook configuration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_preflight

ROOT = Path(__file__).resolve().parents[1]
CLAUDE_SETTINGS = ROOT / ".claude" / "settings.json"


def _load_settings() -> dict[str, object]:
    data = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _hook_groups(data: dict[str, object], name: str) -> list[dict[str, object]]:
    hooks = data["hooks"]
    assert isinstance(hooks, dict)
    groups = hooks[name]
    assert isinstance(groups, list)
    out: list[dict[str, object]] = []
    for group in groups:
        assert isinstance(group, dict)
        out.append(group)
    return out


def test_claude_settings_json_is_valid() -> None:
    data = _load_settings()
    hooks = data.get("hooks")
    assert isinstance(hooks, dict)
    assert set(hooks) == {"SessionStart", "PreToolUse", "PostToolUse"}


def test_claude_post_tool_use_starts_ci_monitor_after_mcp_pr_create() -> None:
    data = _load_settings()
    post_tool_use = _hook_groups(data, "PostToolUse")

    assert post_tool_use == [
        {
            "matcher": "mcp__github__create_pull_request",
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 $CLAUDE_PROJECT_DIR/scripts/post_pr_create_ci_monitor.py",
                }
            ],
        }
    ]


def test_all_claude_hook_commands_point_to_repo_files() -> None:
    data = _load_settings()
    hooks = data["hooks"]
    assert isinstance(hooks, dict)

    commands: list[str] = []
    for groups in hooks.values():
        assert isinstance(groups, list)
        for group in groups:
            assert isinstance(group, dict)
            handlers = group["hooks"]
            assert isinstance(handlers, list)
            for handler in handlers:
                assert isinstance(handler, dict)
                command = handler["command"]
                assert isinstance(command, str)
                commands.append(command)

    for command in commands:
        path = command.split()[-1].removeprefix("$CLAUDE_PROJECT_DIR/")
        assert (ROOT / path).exists()
