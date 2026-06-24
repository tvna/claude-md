"""Tests for the Claude hook configuration."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from gen_agent_hooks import unwrap_command

pytestmark = pytest.mark.shard_preflight

ROOT = Path(__file__).resolve().parents[1]
CLAUDE_SETTINGS = ROOT / ".claude" / "settings.json"


def _unwrap_groups(groups: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return *groups* with every hook command stripped of the CWD wrapper.

    ``.claude/settings.json`` is generated from
    ``scripts/agent_hooks_source.json`` with a
    ``cd "$(git rev-parse --show-toplevel)" && `` prefix injected into each
    repo-script command. Tests assert against the clean repo-relative
    commands, so the wrapper is peeled back here before structural comparison.
    """
    out: list[dict[str, object]] = []
    for group in groups:
        clone = json.loads(json.dumps(group))
        for handler in clone.get("hooks", []):
            command = handler.get("command")
            if isinstance(command, str):
                handler["command"] = unwrap_command(command)
        out.append(clone)
    return out


CORE_HOOK_EVENTS = {"SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse"}
# Claude-only events with no Codex/Devin counterpart (outside the
# scan_hook_coverage_drift parity scope). Stop hosts the decision-handoff
# nudge toward AskUserQuestion (#1044).
OPTIONAL_HOOK_EVENTS = {"Stop"}


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
    unexpected = set(hooks) - CORE_HOOK_EVENTS - OPTIONAL_HOOK_EVENTS
    assert not unexpected


def test_stop_hook_registers_decision_handoff_gate() -> None:
    """The Stop event wires the Claude-only AskUserQuestion nudge (#1044)."""
    data = _load_settings()
    commands: list[str] = []
    for group in _hook_groups(data, "Stop"):
        hooks = group["hooks"]
        assert isinstance(hooks, list)
        for hook in hooks:
            assert isinstance(hook, dict)
            command = hook.get("command")
            if isinstance(command, str):
                commands.append(unwrap_command(command))
    assert any("gate_decision_handoff_askuserquestion.py" in cmd for cmd in commands)


def test_stop_hook_registers_new_session_handoff_prompt() -> None:
    """Stop wires the Claude-only paste-ready handoff nudge (#1334)."""
    data = _load_settings()
    commands: list[str] = []
    for group in _hook_groups(data, "Stop"):
        hooks = group["hooks"]
        assert isinstance(hooks, list)
        for hook in hooks:
            assert isinstance(hook, dict)
            command = hook.get("command")
            if isinstance(command, str):
                commands.append(unwrap_command(command))
    assert any("stop_new_session_handoff_prompt.py" in cmd for cmd in commands)


def test_claude_hooks_use_pascalcase_event_keys() -> None:
    """Hook event keys must be PascalCase; camelCase keys never fire.

    Refs #1030. Claude Code matches lifecycle hook events case-sensitively
    in PascalCase, so a camelCase key such as ``sessionStart`` is dead
    config. A stray ``sessionStart`` duplicate previously shipped next to
    the real ``SessionStart`` array; this guards its reintroduction.
    """
    data = _load_settings()
    hooks = data["hooks"]
    assert isinstance(hooks, dict)
    assert "sessionStart" not in hooks
    for key in hooks:
        assert isinstance(key, str)
        assert key[0].isupper(), f"hook event key must be PascalCase: {key!r}"


def test_claude_post_tool_use_starts_ci_monitor_after_mcp_pr_create() -> None:
    data = _load_settings()
    post_tool_use = _hook_groups(data, "PostToolUse")

    assert _unwrap_groups(post_tool_use) == [
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
                    "command": "python3 scripts/post_pr_create_body_fix.py",
                },
            ],
        },
        {
            "matcher": "mcp__github__create_pull_request",
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 scripts/session_resource_report.py checkpoint",
                },
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
            "matcher": "Bash",
            "hooks": [
                {
                    "type": "command",
                    "if": "Bash(*git push*)",
                    "command": "python3 scripts/check_pr_mergeability.py git-push",
                    "statusMessage": "Checking post-push PR mergeability",
                },
            ],
        },
        {
            "matcher": "mcp__github__merge_pull_request",
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 scripts/post_merge_retro_append.py",
                },
                {
                    "type": "command",
                    "command": "python3 scripts/post_merge_new_session_prompt.py",
                },
            ],
        },
        {
            "matcher": "mcp__codex_apps__github\\._create_pull_request",
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 scripts/session_resource_report.py checkpoint",
                },
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
            handlers = group["hooks"]
            assert isinstance(handlers, list)
            for handler in handlers:
                assert isinstance(handler, dict)
                command = handler["command"]
                assert isinstance(command, str)
                commands.append(unwrap_command(command))

    for command in commands:
        if "CLAUDE_PLUGIN_ROOT" in command:
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

    assert "sessionStart" not in hooks, (
        "camelCase sessionStart is not a recognized Claude Code hook event "
        "(events are PascalCase); the superpowers session-start hook lives "
        "in the SessionStart array only (Refs #1030)"
    )


def test_claude_user_prompt_submit_registers_context7_gate() -> None:
    data = _load_settings()
    assert _unwrap_groups(_hook_groups(data, "UserPromptSubmit")) == [
        {
            "hooks": [
                {
                    "type": "command",
                    "command": "python3 scripts/prompt_context7_gate.py",
                }
            ],
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

    assert any("check_hooks_path.py" in c for c in commands), "SessionStart does not include check_hooks_path.py"


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
            commands.append(unwrap_command(command))

    title_body_matcher = "mcp__codex_apps__github\\._(create_issue|create_pull_request|update_pull_request)"
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
            and unwrap_command(str(handler.get("command", ""))) == "python3 scripts/preflight_branch_base.py verify"
            for handler in handlers
        )
        for group in matching
    )


def test_claude_hook_commands_do_not_use_claude_project_dir() -> None:
    """No hook command in .claude/settings.json should reference $CLAUDE_PROJECT_DIR.

    Refs #783. $CLAUDE_PROJECT_DIR is not set in the FleetView remote-execution
    environment. A command containing it expands to an invalid path and the hook
    fails silently instead of denying the tool call; the exact gap that allowed
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
                    assert (
                        "$CLAUDE_PROJECT_DIR" not in command
                    ), f"{event} hook command uses $CLAUDE_PROJECT_DIR (unset in FleetView): {command!r}"
