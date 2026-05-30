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
PERMISSION_REQUEST_PLAN = ROOT / "docs" / "prd" / "codex-permission-request-policy-gate.md"
DOCS_INDEX = ROOT / "docs" / "INDEX.md"
CORE_HOOK_EVENTS = {"SessionStart", "PreToolUse", "PostToolUse"}
UNSUPPORTED_DEVCONTAINER_HOOK_FRAGMENTS = (
    "CLAUDE_PLUGIN_ROOT",
    "./hooks/run-hook.cmd",
)


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
        path = _repo_script_from_command(command)
        assert not path.startswith("/")
        assert (ROOT / path).exists()


def test_codex_session_start_hooks_are_runnable_in_devcontainer() -> None:
    data = _load_hooks()
    commands: list[str] = []
    for entry in _command_entries(data):
        command = entry["command"]
        assert isinstance(command, str)
        commands.append(command)

    assert not [
        command
        for command in commands
        if any(fragment in command for fragment in UNSUPPORTED_DEVCONTAINER_HOOK_FRAGMENTS)
    ]


def test_codex_session_start_uses_repo_managed_hooks_only() -> None:
    data = _load_hooks()
    hooks = data["hooks"]
    assert isinstance(hooks, dict)

    session_start = hooks["SessionStart"]
    assert isinstance(session_start, list)
    assert session_start

    assert "sessionStart" not in hooks
    assert not any(isinstance(group, dict) and group.get("_apm_source") == "superpowers" for group in session_start)


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


def test_codex_pre_tool_use_covers_codex_github_connector_tools() -> None:
    """Codex GitHub connector PR/issue writes are gated before submission.

    Refs #740. The connector exposes create/update PR and create issue as
    ``mcp__codex_apps__github._<verb>`` rather than ``mcp__github__<verb>``;
    without a matcher for that shape the title/body preflights only fire
    after the PR/issue already reached GitHub. This test fails if the
    connector create/update PR tool names are dropped from the matcher
    surface.
    """
    data = _load_hooks()
    hooks = data["hooks"]
    assert isinstance(hooks, dict)
    pre_tool_use = hooks["PreToolUse"]
    assert isinstance(pre_tool_use, list)

    matcher_to_commands: dict[str, list[str]] = {}
    for group in pre_tool_use:
        assert isinstance(group, dict)
        matcher = group["matcher"]
        handlers = group["hooks"]
        assert isinstance(matcher, str)
        assert isinstance(handlers, list)
        commands = matcher_to_commands.setdefault(matcher, [])
        for handler in handlers:
            command = handler["command"]
            assert isinstance(command, str)
            commands.append(command)

    title_body_matcher = (
        "^mcp__codex_apps__github\\._(create_issue|create_pull_request|update_pull_request)$"
    )
    pr_matcher = "^mcp__codex_apps__github\\._(create_pull_request|update_pull_request)$"

    assert title_body_matcher in matcher_to_commands
    assert pr_matcher in matcher_to_commands

    # Title + non-ASCII + footer guard the connector title/body surface.
    assert "python3 scripts/preflight_title_policy.py" in matcher_to_commands[title_body_matcher]
    assert "python3 scripts/preflight_non_ascii.py" in matcher_to_commands[title_body_matcher]
    assert "python3 scripts/preflight_codex_github_footer.py" in matcher_to_commands[title_body_matcher]

    # PR body shape/section/link gates guard connector PR writes.
    assert "python3 scripts/preflight_pr_body_required_sections.py" in matcher_to_commands[pr_matcher]
    assert "python3 scripts/preflight_pr_template_shape.py" in matcher_to_commands[pr_matcher]
    assert "python3 scripts/pr_body_close_keyword_gate.py" in matcher_to_commands[pr_matcher]
    assert "python3 scripts/preflight_branch_base.py verify" in matcher_to_commands[pr_matcher]


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


def test_codex_post_tool_use_starts_ci_monitor_after_codex_connector_pr_create() -> None:
    """Codex connector PR creation must trigger the same CI monitor/probe as the legacy path.

    Refs #760. The PostToolUse section previously only matched
    ``mcp__github__create_pull_request``, so Codex connector PRs silently
    skipped the polling monitor and early status probe. This test fails if the
    connector path is dropped.
    """
    data = _load_hooks()
    hooks = data["hooks"]
    assert isinstance(hooks, dict)
    post_tool_use = hooks["PostToolUse"]
    assert isinstance(post_tool_use, list)

    connector_matcher = "^mcp__codex_apps__github\\._create_pull_request$"

    matcher_to_commands: dict[str, list[str]] = {}
    for group in post_tool_use:
        assert isinstance(group, dict)
        matcher = group["matcher"]
        handlers = group["hooks"]
        assert isinstance(matcher, str)
        assert isinstance(handlers, list)
        commands = matcher_to_commands.setdefault(matcher, [])
        for handler in handlers:
            command = handler["command"]
            assert isinstance(command, str)
            commands.append(command)

    assert connector_matcher in matcher_to_commands, (
        "PostToolUse has no entry for the Codex connector create_pull_request path"
    )
    assert "python3 scripts/post_pr_create_ci_monitor.py" in matcher_to_commands[connector_matcher]
    assert "python3 scripts/ci_early_status_probe.py" in matcher_to_commands[connector_matcher]


def test_codex_session_start_surfaces_hooks_path_gap() -> None:
    """SessionStart must include a check_hooks_path hook to surface missing core.hooksPath.

    Refs #760. Without core.hooksPath=.githooks the pre-push stale-base gate
    is silently skipped for Codex worktrees.
    """
    data = _load_hooks()
    hooks = data["hooks"]
    assert isinstance(hooks, dict)
    session_start = hooks["SessionStart"]
    assert isinstance(session_start, list)

    commands: list[str] = []
    for group in session_start:
        assert isinstance(group, dict)
        if group.get("_apm_source") == "superpowers":
            continue
        handlers = group.get("hooks", [])
        assert isinstance(handlers, list)
        for handler in handlers:
            if isinstance(handler, dict):
                cmd = handler.get("command", "")
                if isinstance(cmd, str):
                    commands.append(cmd)

    assert "python3 scripts/check_hooks_path.py" in commands, (
        "SessionStart does not include check_hooks_path.py; "
        "missing core.hooksPath will not be surfaced at session start"
    )


def test_codex_permission_request_policy_plan_is_documented() -> None:
    body = PERMISSION_REQUEST_PLAN.read_text(encoding="utf-8")

    required_phrases = [
        "Refs #711",
        "Refs #617",
        "Refs #604",
        "Codex-specific entry point",
        "shared repository policy predicate",
        "Claude parity",
        "allow, deny, and no-decision",
        "malformed JSON",
        "unsupported payload",
        "must not update `.codex/hooks.json`",
        "rollback command",
        "targeted verification",
    ]
    for phrase in required_phrases:
        assert phrase in body

    index = DOCS_INDEX.read_text(encoding="utf-8")
    assert "codex-permission-request-policy-gate.md" in index
