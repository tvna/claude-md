"""Tests for the Codex hook configuration.

Refs #606.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from gen_agent_hooks import unwrap_command

pytestmark = pytest.mark.shard_preflight

ROOT = Path(__file__).resolve().parents[1]
CODEX_HOOKS = ROOT / ".codex" / "hooks.json"


def _unwrap_groups(groups: list[dict[str, object]]) -> list[dict[str, object]]:
    """Return *groups* with every hook command stripped of the CWD wrapper.

    The configs are generated from ``scripts/agent_hooks_source.json`` with a
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


PERMISSION_REQUEST_PLAN = ROOT / "docs" / "prd" / "codex-permission-request-policy-gate.md"
DOCS_INDEX = ROOT / "docs" / "INDEX.md"
CORE_HOOK_EVENTS = {"SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse"}


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
    unexpected = set(hooks) - CORE_HOOK_EVENTS
    assert not unexpected


def test_codex_hooks_use_pascalcase_event_keys() -> None:
    """Hook event keys must be PascalCase; camelCase keys never fire.

    Refs #1030. Codex matches lifecycle hook events case-sensitively in
    PascalCase, so a camelCase key such as ``sessionStart`` is dead config.
    A stray ``sessionStart`` duplicate previously shipped next to the real
    ``SessionStart`` array; this guards its reintroduction.
    """
    data = _load_hooks()
    hooks = data["hooks"]
    assert isinstance(hooks, dict)
    assert "sessionStart" not in hooks
    for key in hooks:
        assert isinstance(key, str)
        assert key[0].isupper(), f"hook event key must be PascalCase: {key!r}"


def test_all_codex_hook_commands_point_to_repo_files() -> None:
    data = _load_hooks()
    commands = [entry["command"] for entry in _command_entries(data)]
    assert commands
    for command in commands:
        assert isinstance(command, str)
        if "CLAUDE_PLUGIN_ROOT" in command:
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

    assert "sessionStart" not in hooks, (
        "camelCase sessionStart is not a recognized Codex hook event "
        "(events are PascalCase); the superpowers session-start hook lives "
        "in the SessionStart array only (Refs #1030)"
    )


def test_codex_user_prompt_submit_registers_context7_gate() -> None:
    data = _load_hooks()
    hooks = data["hooks"]
    assert isinstance(hooks, dict)
    user_prompt_submit = hooks["UserPromptSubmit"]
    assert isinstance(user_prompt_submit, list)

    assert _unwrap_groups(user_prompt_submit) == [
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
            commands.append(unwrap_command(command))

    assert (
        "^mcp__github__(issue_write|add_issue_comment|create_pull_request|update_pull_request|add_reply_to_pull_request_comment|pull_request_review_write|add_comment_to_pending_review|sub_issue_write)$"
        in matchers
    )
    assert (
        "^mcp__github__(issue_write|add_issue_comment|create_pull_request|update_pull_request|add_reply_to_pull_request_comment|pull_request_review_write|add_comment_to_pending_review)$"
        in matchers
    )
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
            commands.append(unwrap_command(command))

    title_body_matcher = "^mcp__codex_apps__github\\._(create_issue|create_pull_request|update_pull_request)$"
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
            and unwrap_command(str(handler.get("command", ""))) == "python3 scripts/preflight_branch_base.py verify"
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
            commands.append(unwrap_command(command))

    assert "^mcp__github__create_pull_request$" in matchers
    assert "python3 scripts/post_pr_create_ci_monitor.py" in commands
    assert "python3 scripts/ci_early_status_probe.py" in commands
    # Merge-readiness loop must surface mergeability for every agent (Refs #1361).
    assert "python3 scripts/check_pr_mergeability.py" in commands


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
            commands.append(unwrap_command(command))

    assert (
        connector_matcher in matcher_to_commands
    ), "PostToolUse has no entry for the Codex connector create_pull_request path"
    assert "python3 scripts/post_pr_create_ci_monitor.py" in matcher_to_commands[connector_matcher]
    assert "python3 scripts/ci_early_status_probe.py" in matcher_to_commands[connector_matcher]
    # Merge-readiness loop must surface mergeability for every agent (Refs #1361).
    assert "python3 scripts/check_pr_mergeability.py" in matcher_to_commands[connector_matcher]


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
                    commands.append(unwrap_command(cmd))

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
