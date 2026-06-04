"""Tests for ``scripts/preflight_hook_event_keys.py``.

Refs #1030. The gate rejects non-PascalCase hook event keys (such as the
camelCase ``sessionStart`` that previously shipped) in the agent hook
configs, shifting detection to commit time.
"""

from __future__ import annotations

import json
from pathlib import Path

import preflight_hook_event_keys as gate
import pytest

pytestmark = pytest.mark.shard_preflight

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_repository_hook_configs_pass_the_gate() -> None:
    """The checked-in configs must satisfy the gate (exit 0)."""
    assert gate.main([]) == 0


def test_gate_targets_the_agent_hook_configs() -> None:
    assert gate.HOOK_CONFIG_FILES == (
        ".claude/settings.json",
        ".codex/hooks.json",
        ".devin/hooks.v1.json",
        ".devcontainer/config/claude/settings.json",
    )
    for rel in gate.HOOK_CONFIG_FILES:
        assert (REPO_ROOT / rel).exists()


def test_offending_event_keys_flags_camelcase() -> None:
    hooks: dict[str, list[object]] = {"SessionStart": [], "sessionStart": [], "PreToolUse": []}
    assert gate.offending_event_keys(hooks) == ["sessionStart"]


def test_offending_event_keys_accepts_known_pascalcase_events() -> None:
    hooks: dict[str, list[object]] = {
        "SessionStart": [],
        "PreToolUse": [],
        "PostToolUse": [],
        "UserPromptSubmit": [],
    }
    assert gate.offending_event_keys(hooks) == []


def test_offending_event_keys_ignores_non_dict() -> None:
    assert gate.offending_event_keys([]) == []
    assert gate.offending_event_keys(None) == []


def test_check_file_reports_camelcase_violation(tmp_path: Path) -> None:
    bad = tmp_path / "hooks.json"
    bad.write_text(json.dumps({"hooks": {"sessionStart": []}}), encoding="utf-8")
    messages = gate.check_file(bad)
    assert len(messages) == 1
    assert "sessionStart" in messages[0]
    assert "PascalCase" in messages[0]


def test_check_file_passes_pascalcase(tmp_path: Path) -> None:
    good = tmp_path / "hooks.json"
    good.write_text(json.dumps({"hooks": {"SessionStart": []}}), encoding="utf-8")
    assert gate.check_file(good) == []
