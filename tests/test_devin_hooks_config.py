"""Tests for the Devin hook configuration.

Refs #982.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_preflight

ROOT = Path(__file__).resolve().parents[1]
DEVIN_HOOKS = ROOT / ".devin" / "hooks.v1.json"
CODEX_HOOKS = ROOT / ".codex" / "hooks.json"
CORE_HOOK_EVENTS = {"SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse"}


def _load_hooks() -> dict[str, object]:
    data = json.loads(DEVIN_HOOKS.read_text(encoding="utf-8"))
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


def _commands_for_groups(groups: list[dict[str, object]]) -> list[str]:
    commands: list[str] = []
    for group in groups:
        handlers = group["hooks"]
        assert isinstance(handlers, list)
        for handler in handlers:
            assert isinstance(handler, dict)
            command = handler["command"]
            assert isinstance(command, str)
            commands.append(command)
    return commands


def _repo_script_from_command(command: str) -> str:
    for token in command.split():
        if token.startswith("scripts/"):
            return token
    return command.split()[-1]


def _matcher_to_commands(groups: list[dict[str, object]]) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for group in groups:
        matcher = group["matcher"]
        handlers = group["hooks"]
        assert isinstance(matcher, str)
        assert isinstance(handlers, list)
        commands = out.setdefault(matcher, [])
        for handler in handlers:
            assert isinstance(handler, dict)
            command = handler["command"]
            assert isinstance(command, str)
            commands.append(command)
    return out


def test_devin_hooks_json_is_valid() -> None:
    data = _load_hooks()
    hooks = data.get("hooks")
    assert isinstance(hooks, dict)
    assert set(hooks) >= CORE_HOOK_EVENTS
    unexpected = set(hooks) - CORE_HOOK_EVENTS
    assert not unexpected


def test_devin_hooks_use_pascalcase_event_keys() -> None:
    """Hook event keys must be PascalCase; camelCase keys never fire.

    Refs #1030. The Devin adapter mirrors the Claude/Codex hook configs,
    whose lifecycle events are matched case-sensitively in PascalCase, so a
    camelCase key such as ``sessionStart`` is dead config. A stray
    ``sessionStart`` duplicate previously shipped next to the real
    ``SessionStart`` array; this guards its reintroduction.
    """
    data = _load_hooks()
    hooks = data["hooks"]
    assert isinstance(hooks, dict)
    assert "sessionStart" not in hooks
    for key in hooks:
        assert isinstance(key, str)
        assert key[0].isupper(), f"hook event key must be PascalCase: {key!r}"


def test_all_devin_hook_commands_point_to_repo_files() -> None:
    data = _load_hooks()
    commands: list[str] = []
    hooks = data["hooks"]
    assert isinstance(hooks, dict)
    for event_name in hooks:
        assert isinstance(event_name, str)
        commands.extend(_commands_for_groups(_hook_groups(data, event_name)))

    assert commands
    for command in commands:
        if "CLAUDE_PLUGIN_ROOT" in command:
            continue
        path = _repo_script_from_command(command)
        assert not path.startswith("/")
        assert (ROOT / path).exists()


def test_devin_session_start_matches_required_bootstrap_gates() -> None:
    data = _load_hooks()
    commands = _commands_for_groups(_hook_groups(data, "SessionStart"))

    assert "scripts/install-uv.sh" in commands
    assert "python3 scripts/plan_language_context.py" in commands
    assert "python3 scripts/check_hooks_path.py" in commands
    assert "python3 scripts/check_session_branch.py" in commands
    assert "python3 scripts/check_pr_mergeability.py session-start" in commands


def test_devin_user_prompt_submit_registers_context7_gate() -> None:
    data = _load_hooks()
    assert _hook_groups(data, "UserPromptSubmit") == [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 scripts/prompt_context7_gate.py",
                    "statusMessage": "Checking context7 lookup guidance",
                }
            ]
        }
    ]


def test_devin_pre_tool_use_covers_github_write_gates() -> None:
    data = _load_hooks()
    matcher_to_commands = _matcher_to_commands(_hook_groups(data, "PreToolUse"))
    github_write_matcher = (
        "^mcp__github__(issue_write|add_issue_comment|create_pull_request|"
        "update_pull_request|add_reply_to_pull_request_comment|"
        "pull_request_review_write|add_comment_to_pending_review|sub_issue_write)$"
    )
    connector_write_matcher = (
        "^mcp__codex_apps__github\\._"
        "(create_issue|create_pull_request|update_pull_request)$"
    )

    assert github_write_matcher in matcher_to_commands
    assert connector_write_matcher in matcher_to_commands
    assert "python3 scripts/preflight_non_ascii.py" in matcher_to_commands[
        github_write_matcher
    ]
    assert "python3 scripts/preflight_title_policy.py" in matcher_to_commands[
        connector_write_matcher
    ]


def test_devin_post_tool_use_starts_pr_monitoring() -> None:
    data = _load_hooks()
    matcher_to_commands = _matcher_to_commands(_hook_groups(data, "PostToolUse"))
    legacy_pr_create = "^mcp__github__create_pull_request$"
    connector_pr_create = "^mcp__codex_apps__github\\._create_pull_request$"

    assert legacy_pr_create in matcher_to_commands
    assert "python3 scripts/post_pr_create_ci_monitor.py" in matcher_to_commands[
        legacy_pr_create
    ]
    assert connector_pr_create in matcher_to_commands


def test_devin_hooks_match_codex_hooks_exactly() -> None:
    """The Devin adapter must stay byte-for-byte in sync with the Codex config.

    Refs #1030. ``.devin/hooks.v1.json`` mirrors ``.codex/hooks.json`` (see
    docs/standards/devin-apm-compatibility.md). A one-sided edit -- such as
    fixing a bad hook key in one file but not the other -- would silently
    diverge the two adapters. Asserting full equality of the parsed configs
    forces every hook change to land in both files together.
    """
    devin = json.loads(DEVIN_HOOKS.read_text(encoding="utf-8"))
    codex = json.loads(CODEX_HOOKS.read_text(encoding="utf-8"))
    assert devin == codex, (
        ".devin/hooks.v1.json and .codex/hooks.json have diverged; "
        "hook changes must be applied to both adapters together"
    )
