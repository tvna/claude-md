"""Tests for the UserPromptSubmit context7 reminder hook.

Refs #1213.
"""

from __future__ import annotations

import importlib.util
import io
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_preflight

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

_SPEC = importlib.util.spec_from_file_location(
    "prompt_context7_gate", REPO_ROOT / "scripts" / "prompt_context7_gate.py"
)
assert _SPEC and _SPEC.loader
subject = importlib.util.module_from_spec(_SPEC)
sys.modules["prompt_context7_gate"] = subject
_SPEC.loader.exec_module(subject)


def test_decide_adds_context_for_primary_source_prompt() -> None:
    decision = subject.decide(
        {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "一次情報を探す必要があるので React の公式 docs を確認して",
        }
    )

    assert decision == {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": subject.CONTEXT7_REMINDER,
        }
    }


def test_decide_adds_context_for_context7_prompt() -> None:
    decision = subject.decide(
        {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "Use context7 for the pytest fixture docs.",
        }
    )

    assert decision is not None
    assert decision["hookSpecificOutput"]["additionalContext"] == subject.CONTEXT7_REMINDER


def test_decide_adds_context_for_japanese_primary_source_typo() -> None:
    decision = subject.decide(
        {
            "hook_event_name": "UserPromptSubmit",
            "prompt": "一時情報が必要なら公式資料を確認して",
        }
    )

    assert decision is not None


def test_decide_stays_silent_for_unrelated_prompt() -> None:
    assert subject.decide({"hook_event_name": "UserPromptSubmit", "prompt": "Run the tests."}) is None


def test_decide_stays_silent_for_other_hook_event() -> None:
    assert subject.decide({"hook_event_name": "SessionStart", "prompt": "official docs"}) is None


def test_main_emits_json_for_matching_prompt(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    event = {
        "hook_event_name": "UserPromptSubmit",
        "prompt": "Look up the latest official API docs for FastAPI.",
    }
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))

    assert subject.main([]) == 0

    stdout = capsys.readouterr().out
    assert json.loads(stdout) == {
        "hookSpecificOutput": {
            "hookEventName": "UserPromptSubmit",
            "additionalContext": subject.CONTEXT7_REMINDER,
        }
    }


def test_main_fails_open_on_malformed_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))

    assert subject.main([]) == 0

    captured = capsys.readouterr()
    assert captured.out == ""
    assert "malformed stdin JSON" in captured.err
