"""Tests for ``scripts/scan_hook_coverage_drift.py``.

Refs #615. Verifies that the drift gate correctly detects when a Claude
hook script is absent from Codex coverage and passes when all hooks are
covered or allowlisted.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import scan_hook_coverage_drift as shcd

pytestmark = pytest.mark.shard_preflight

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# collect_claude_hooks
# ---------------------------------------------------------------------------


def _make_claude_settings(hooks: dict) -> dict:
    return {"hooks": hooks}


def _make_codex_hooks(hooks: dict) -> dict:
    return {"hooks": hooks}


def _claude_group(command: str, matcher: str | None = None) -> dict:
    group: dict = {"hooks": [{"type": "command", "command": command}]}
    if matcher is not None:
        group["matcher"] = matcher
    return group


def _codex_group(command: str, matcher: str | None = None) -> dict:
    group: dict = {"hooks": [{"type": "command", "command": command}]}
    if matcher is not None:
        group["matcher"] = matcher
    return group


def test_collect_claude_hooks_extracts_script_references() -> None:
    settings = _make_claude_settings(
        {
            "SessionStart": [_claude_group("python3 scripts/plan_language_context.py")],
            "PreToolUse": [],
            "PostToolUse": [],
        }
    )
    hooks = shcd.collect_claude_hooks(settings)
    assert shcd.HookEntry(event="SessionStart", script="plan_language_context") in hooks


def test_collect_claude_hooks_skips_non_script_commands() -> None:
    settings = _make_claude_settings(
        {
            "SessionStart": [_claude_group("scripts/install-uv.sh")],
            "PreToolUse": [],
            "PostToolUse": [],
        }
    )
    hooks = shcd.collect_claude_hooks(settings)
    assert not hooks


def test_collect_claude_hooks_skips_superpowers() -> None:
    settings = _make_claude_settings(
        {
            "SessionStart": [
                {
                    "matcher": "startup",
                    "hooks": [{"type": "command", "command": "scripts/some_apm.py"}],
                    "_apm_source": "superpowers",
                }
            ],
            "PreToolUse": [],
            "PostToolUse": [],
        }
    )
    hooks = shcd.collect_claude_hooks(settings)
    assert not hooks


def test_collect_claude_hooks_multiple_events() -> None:
    settings = _make_claude_settings(
        {
            "SessionStart": [_claude_group("python3 scripts/plan_language_context.py")],
            "PreToolUse": [_claude_group("python3 scripts/preflight_non_ascii.py")],
            "PostToolUse": [_claude_group("python3 scripts/plan_approval_gate.py")],
        }
    )
    hooks = shcd.collect_claude_hooks(settings)
    assert shcd.HookEntry(event="SessionStart", script="plan_language_context") in hooks
    assert shcd.HookEntry(event="PreToolUse", script="preflight_non_ascii") in hooks
    assert shcd.HookEntry(event="PostToolUse", script="plan_approval_gate") in hooks


# ---------------------------------------------------------------------------
# collect_codex_hooks
# ---------------------------------------------------------------------------


def test_collect_codex_hooks_extracts_script_references() -> None:
    data = _make_codex_hooks(
        {
            "SessionStart": [_codex_group("python3 scripts/plan_language_context.py")],
            "PreToolUse": [],
            "PostToolUse": [],
        }
    )
    hooks = shcd.collect_codex_hooks(data)
    assert shcd.HookEntry(event="SessionStart", script="plan_language_context") in hooks


# ---------------------------------------------------------------------------
# find_drift
# ---------------------------------------------------------------------------


def test_find_drift_empty_when_fully_covered() -> None:
    claude = {shcd.HookEntry(event="SessionStart", script="plan_language_context")}
    codex = {shcd.HookEntry(event="SessionStart", script="plan_language_context")}
    assert shcd.find_drift(claude, codex, {}) == []


def test_find_drift_detects_missing_hook() -> None:
    claude = {shcd.HookEntry(event="PreToolUse", script="preflight_non_ascii")}
    codex: set[shcd.HookEntry] = set()
    missing = shcd.find_drift(claude, codex, {})
    assert len(missing) == 1
    assert missing[0].script == "preflight_non_ascii"


def test_find_drift_allowlist_suppresses_missing() -> None:
    claude = {shcd.HookEntry(event="PostToolUse", script="plan_approval_gate")}
    codex: set[shcd.HookEntry] = set()
    allowlist = {"plan_approval_gate": "No Codex Write tool equivalent."}
    assert shcd.find_drift(claude, codex, allowlist) == []


def test_find_drift_codex_script_in_different_event_is_still_missing() -> None:
    """Coverage in a different event does not count as coverage."""
    claude = {shcd.HookEntry(event="PreToolUse", script="preflight_non_ascii")}
    codex = {shcd.HookEntry(event="PostToolUse", script="preflight_non_ascii")}
    missing = shcd.find_drift(claude, codex, {})
    assert len(missing) == 1


def test_find_drift_codex_extra_hooks_are_ignored() -> None:
    claude: set[shcd.HookEntry] = set()
    codex = {shcd.HookEntry(event="PreToolUse", script="preflight_codex_github_footer")}
    assert shcd.find_drift(claude, codex, {}) == []


# ---------------------------------------------------------------------------
# cmd_verify via fixtures
# ---------------------------------------------------------------------------


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def test_cmd_verify_passes_on_full_coverage(tmp_path: Path) -> None:
    claude_path = tmp_path / "settings.json"
    codex_path = tmp_path / "hooks.json"
    _write_json(
        claude_path,
        _make_claude_settings(
            {
                "SessionStart": [_claude_group("python3 scripts/plan_language_context.py")],
                "PreToolUse": [],
                "PostToolUse": [],
            }
        ),
    )
    _write_json(
        codex_path,
        _make_codex_hooks(
            {
                "SessionStart": [_codex_group("python3 scripts/plan_language_context.py")],
                "PreToolUse": [],
                "PostToolUse": [],
            }
        ),
    )

    rc = shcd.main(["verify", "--claude", str(claude_path), "--codex", str(codex_path)])
    assert rc == 0


def test_cmd_verify_fails_on_missing_hook(tmp_path: Path) -> None:
    claude_path = tmp_path / "settings.json"
    codex_path = tmp_path / "hooks.json"
    _write_json(
        claude_path,
        _make_claude_settings(
            {
                "SessionStart": [],
                "PreToolUse": [
                    _claude_group(
                        "python3 scripts/preflight_non_ascii.py",
                        matcher="^mcp__github__create_pull_request$",
                    )
                ],
                "PostToolUse": [],
            }
        ),
    )
    _write_json(
        codex_path,
        _make_codex_hooks({"SessionStart": [], "PreToolUse": [], "PostToolUse": []}),
    )

    rc = shcd.main(["verify", "--claude", str(claude_path), "--codex", str(codex_path)])
    assert rc == 1


def test_cmd_verify_passes_with_allowlisted_gap(tmp_path: Path) -> None:
    claude_path = tmp_path / "settings.json"
    codex_path = tmp_path / "hooks.json"
    _write_json(
        claude_path,
        _make_claude_settings(
            {
                "SessionStart": [],
                "PreToolUse": [],
                "PostToolUse": [_claude_group("python3 scripts/plan_approval_gate.py")],
            }
        ),
    )
    _write_json(
        codex_path,
        _make_codex_hooks({"SessionStart": [], "PreToolUse": [], "PostToolUse": []}),
    )

    rc = shcd.main(["verify", "--claude", str(claude_path), "--codex", str(codex_path)])
    assert rc == 0


# ---------------------------------------------------------------------------
# Real config files
# ---------------------------------------------------------------------------


def test_real_config_files_pass_drift_check() -> None:
    """Current .claude/settings.json and .codex/hooks.json must pass the gate."""
    rc = shcd.main(
        [
            "verify",
            "--claude",
            str(REPO_ROOT / ".claude" / "settings.json"),
            "--codex",
            str(REPO_ROOT / ".codex" / "hooks.json"),
        ]
    )
    assert rc == 0


# ---------------------------------------------------------------------------
# _collect_hooks() defensive isinstance guards
# ---------------------------------------------------------------------------


def test_collect_claude_hooks_non_dict_hooks_section() -> None:
    settings: dict[str, object] = {"hooks": "not-a-dict"}
    assert shcd.collect_claude_hooks(settings) == set()


def test_collect_claude_hooks_non_list_event_groups() -> None:
    settings: dict[str, object] = {"hooks": {"SessionStart": "not-a-list", "PreToolUse": [], "PostToolUse": []}}
    assert shcd.collect_claude_hooks(settings) == set()


def test_collect_claude_hooks_non_dict_group_entry() -> None:
    settings: dict[str, object] = {"hooks": {"SessionStart": ["not-a-dict"], "PreToolUse": [], "PostToolUse": []}}
    assert shcd.collect_claude_hooks(settings) == set()


def test_collect_claude_hooks_non_list_handlers() -> None:
    settings: dict[str, object] = {
        "hooks": {
            "SessionStart": [{"hooks": "not-a-list"}],
            "PreToolUse": [],
            "PostToolUse": [],
        }
    }
    assert shcd.collect_claude_hooks(settings) == set()


def test_collect_claude_hooks_non_dict_handler_entry() -> None:
    settings: dict[str, object] = {
        "hooks": {
            "SessionStart": [{"hooks": ["not-a-dict"]}],
            "PreToolUse": [],
            "PostToolUse": [],
        }
    }
    assert shcd.collect_claude_hooks(settings) == set()


def test_collect_claude_hooks_non_str_command() -> None:
    settings: dict[str, object] = {
        "hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": 123}]}],
            "PreToolUse": [],
            "PostToolUse": [],
        }
    }
    assert shcd.collect_claude_hooks(settings) == set()


def test_main_block_exits_via_runpy(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy
    import sys

    monkeypatch.setattr(sys, "argv", ["scan_hook_coverage_drift", "--help"])
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("scan_hook_coverage_drift", run_name="__main__")
    assert exc_info.value.code == 0
