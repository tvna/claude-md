"""Tests for the Claude hook configuration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_preflight

ROOT = Path(__file__).resolve().parents[1]
CLAUDE_SETTINGS = ROOT / ".claude" / "settings.json"
CORE_HOOK_EVENTS = {"SessionStart", "PreToolUse", "PostToolUse"}


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


def _repo_script_from_command(command: str) -> str:
    for token in command.split():
        if token.startswith("scripts/"):
            return token
    return command.split()[-1]


def test_claude_settings_json_is_valid() -> None:
    data = _load_settings()
    hooks = data.get("hooks")
    assert isinstance(hooks, dict)
    assert set(hooks) >= CORE_HOOK_EVENTS
    unexpected = set(hooks) - CORE_HOOK_EVENTS - {"sessionStart"}
    assert not unexpected


def test_claude_post_tool_use_starts_ci_monitor_after_mcp_pr_create() -> None:
    data = _load_settings()
    post_tool_use = _hook_groups(data, "PostToolUse")

    assert post_tool_use == [
        {
            "matcher": "Write",
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 scripts/plan_approval_gate.py",
                }
            ],
        },
        {
            "matcher": "mcp__github__(add_issue_comment|add_reply_to_pull_request_comment)",
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 scripts/gate_issue_close_comment.py --record",
                }
            ],
        },
        {
            "matcher": "mcp__github__create_pull_request",
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 scripts/post_pr_create_ci_monitor.py",
                },
                {
                    "type": "command",
                    "command": "python3 scripts/check_pr_mergeability.py",
                },
            ],
        },
        {
            "matcher": "mcp__github__update_pull_request_branch",
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 scripts/check_pr_mergeability.py",
                },
            ],
        },
        {
            "matcher": "mcp__codex_apps__github\\._create_pull_request",
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 scripts/post_pr_create_ci_monitor.py",
                },
                {
                    "type": "command",
                    "command": "python3 scripts/check_pr_mergeability.py",
                },
            ],
        },
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
            if group.get("_apm_source") == "superpowers" and "command" in group:
                commands.append(group["command"])
                continue
            handlers = group["hooks"]
            assert isinstance(handlers, list)
            for handler in handlers:
                assert isinstance(handler, dict)
                command = handler["command"]
                assert isinstance(command, str)
                commands.append(command)

    for command in commands:
        if "CLAUDE_PLUGIN_ROOT" in command or command == "./hooks/run-hook.cmd session-start":
            continue
        path = _repo_script_from_command(command)
        assert (ROOT / path).exists()


def test_claude_superpowers_hooks_are_apm_managed() -> None:
    data = _load_settings()
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


def test_claude_session_start_surfaces_hooks_path_gap() -> None:
    """SessionStart must include check_hooks_path.py to surface missing core.hooksPath.

    Refs #760. Without core.hooksPath=.githooks the pre-push stale-base gate
    is silently skipped for Claude Code sessions too, not just Codex worktrees.
    """
    data = _load_settings()
    hooks = data["hooks"]
    assert isinstance(hooks, dict)
    session_start = hooks["SessionStart"]
    assert isinstance(session_start, list)

    commands: list[str] = []
    for group in session_start:
        assert isinstance(group, dict)
        if group.get("_apm_source") == "superpowers":
            continue
        for handler in group.get("hooks", []):
            if isinstance(handler, dict):
                cmd = handler.get("command", "")
                if isinstance(cmd, str):
                    commands.append(cmd)

    assert any("check_hooks_path.py" in c for c in commands), (
        "SessionStart does not include check_hooks_path.py"
    )


def test_claude_pre_tool_use_covers_codex_github_connector_tools() -> None:
    """Codex GitHub connector PR/issue writes are gated in the Claude config too.

    Refs #740. The fix is applied to both agent configs (defense in depth):
    regardless of which harness surfaces a
    ``mcp__codex_apps__github._<verb>`` tool name, the title/body preflights
    must fire before the write reaches GitHub. This test fails if the
    connector create/update PR tool names are dropped from the matcher
    surface. The Codex-only footer hook is intentionally absent here, matching
    the existing Claude config which never binds it.
    """
    data = _load_settings()
    pre_tool_use = _hook_groups(data, "PreToolUse")

    matcher_to_commands: dict[str, list[str]] = {}
    for group in pre_tool_use:
        matcher = group.get("matcher")
        handlers = group.get("hooks")
        if not isinstance(matcher, str) or not isinstance(handlers, list):
            continue
        commands = matcher_to_commands.setdefault(matcher, [])
        for handler in handlers:
            assert isinstance(handler, dict)
            command = handler["command"]
            assert isinstance(command, str)
            commands.append(command)

    title_body_matcher = (
        "mcp__codex_apps__github\\._(create_issue|create_pull_request|update_pull_request)"
    )
    pr_matcher = "mcp__codex_apps__github\\._(create_pull_request|update_pull_request)"

    assert title_body_matcher in matcher_to_commands
    assert pr_matcher in matcher_to_commands

    title_body_cmds = matcher_to_commands[title_body_matcher]
    assert "python3 scripts/preflight_title_policy.py" in title_body_cmds
    assert "python3 scripts/preflight_non_ascii.py" in title_body_cmds

    pr_cmds = matcher_to_commands[pr_matcher]
    assert "python3 scripts/preflight_pr_body_required_sections.py" in pr_cmds
    assert "python3 scripts/preflight_pr_template_shape.py" in pr_cmds
    assert "python3 scripts/pr_body_close_keyword_gate.py" in pr_cmds
    assert "python3 scripts/preflight_branch_base.py verify" in pr_cmds


def test_claude_pr_write_hooks_include_base_freshness_gate() -> None:
    data = _load_settings()
    pre_tool_use = _hook_groups(data, "PreToolUse")

    matching = [
        group
        for group in pre_tool_use
        if group.get("matcher") == "mcp__github__(create_pull_request|update_pull_request)"
    ]
    assert matching
    assert any(
        isinstance(handlers := group.get("hooks"), list)
        and any(
            isinstance(handler, dict)
            and handler.get("command")
            == "python3 scripts/preflight_branch_base.py verify"
            for handler in handlers
        )
        for group in matching
    )


def test_claude_hook_commands_do_not_use_claude_project_dir() -> None:
    """No hook command in .claude/settings.json should reference $CLAUDE_PROJECT_DIR.

    Refs #783. $CLAUDE_PROJECT_DIR is not set in the FleetView remote-execution
    environment. A command containing it expands to an invalid path and the hook
    fails silently instead of denying the tool call -- the exact gap that allowed
    a behind-branch PR to be created despite the stale-base PreToolUse gate.
    """
    data = _load_settings()
    hooks = data["hooks"]
    assert isinstance(hooks, dict)

    for event, groups in hooks.items():
        assert isinstance(groups, list)
        for group in groups:
            assert isinstance(group, dict)
            if group.get("_apm_source") == "superpowers":
                continue
            for handler in group.get("hooks", []):
                if isinstance(handler, dict):
                    command = handler.get("command", "")
                    assert "$CLAUDE_PROJECT_DIR" not in command, (
                        f"{event} hook command uses $CLAUDE_PROJECT_DIR (unset in FleetView): {command!r}"
                    )
