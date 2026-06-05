"""Unit tests for the shared PreToolUse hook runtime helpers.

Refs #1240. Covers ``build_deny`` / ``split_tool_event`` / ``run_event_hook``
/ ``run_tool_hook`` -- the helpers that absorbed the per-gate ``main()`` and
deny-payload boilerplate. Testing them directly keeps the moved fail-open and
missing-shape branches covered now that they no longer live in each gate.
"""

from __future__ import annotations

import io
import json
from typing import Any

import _hook_runtime as hr
import pytest

pytestmark = pytest.mark.shard_preflight


def _fake_stdio(monkeypatch: pytest.MonkeyPatch, raw: str) -> list[str]:
    """Pipe *raw* to stdin and capture stdout writes into the returned list."""
    out: list[str] = []
    monkeypatch.setattr("sys.stdin", io.StringIO(raw))
    monkeypatch.setattr(
        "sys.stdout",
        type("FakeOut", (), {"write": lambda self, s: out.append(s)})(),
    )
    return out


# ---------------------------------------------------------------------------
# build_deny
# ---------------------------------------------------------------------------


def test_build_deny_shape() -> None:
    assert hr.build_deny("because") == {
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": "because",
        }
    }


# ---------------------------------------------------------------------------
# split_tool_event
# ---------------------------------------------------------------------------


def test_split_tool_event_returns_pair() -> None:
    event = {"tool_name": "Bash", "tool_input": {"command": "ls"}}
    assert hr.split_tool_event(event, "gate") == ("Bash", {"command": "ls"})


def test_split_tool_event_missing_input_defaults_empty() -> None:
    # A missing tool_input collapses to {} -- the per-gate ``or {}`` behaviour.
    assert hr.split_tool_event({"tool_name": "Bash"}, "gate") == ("Bash", {})


@pytest.mark.parametrize(
    "event",
    [
        {"tool_input": {"command": "ls"}},  # tool_name missing
        {"tool_name": 5, "tool_input": {}},  # tool_name not a str
        {"tool_name": "Bash", "tool_input": "x"},  # tool_input not a dict
    ],
)
def test_split_tool_event_bad_shape_returns_none_and_logs(
    event: dict[str, Any], capsys: pytest.CaptureFixture[str]
) -> None:
    assert hr.split_tool_event(event, "mygate") is None
    assert capsys.readouterr().err == "::error::mygate: event missing tool_name/tool_input\n"


# ---------------------------------------------------------------------------
# run_event_hook
# ---------------------------------------------------------------------------


def test_run_event_hook_emits_decision(monkeypatch: pytest.MonkeyPatch) -> None:
    out = _fake_stdio(monkeypatch, json.dumps({"tool_name": "Bash", "tool_input": {}}))
    rc = hr.run_event_hook("gate", lambda ev: hr.build_deny("no"))
    assert rc == 0
    assert json.loads("".join(out))["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_run_event_hook_none_decision_writes_nothing(monkeypatch: pytest.MonkeyPatch) -> None:
    out = _fake_stdio(monkeypatch, json.dumps({"tool_name": "Bash", "tool_input": {}}))
    rc = hr.run_event_hook("gate", lambda ev: None)
    assert rc == 0
    assert out == []


def test_run_event_hook_malformed_json_fails_open(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("{bad"))
    called = False

    def decide(ev: dict[str, Any]) -> dict[str, Any] | None:
        nonlocal called
        called = True
        return None

    rc = hr.run_event_hook("gate", decide)
    assert rc == 0
    assert called is False  # never reached -- read_event returned None
    assert "malformed stdin JSON" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# run_tool_hook
# ---------------------------------------------------------------------------


def test_run_tool_hook_passes_split_fields(monkeypatch: pytest.MonkeyPatch) -> None:
    out = _fake_stdio(
        monkeypatch, json.dumps({"tool_name": "Bash", "tool_input": {"command": "x"}})
    )
    seen: list[tuple[str, dict[str, Any]]] = []

    def decide(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:
        seen.append((tool_name, tool_input))
        return hr.build_deny("blocked")

    rc = hr.run_tool_hook("gate", decide)
    assert rc == 0
    assert seen == [("Bash", {"command": "x"})]
    assert json.loads("".join(out))["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_run_tool_hook_bad_shape_fails_open(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    _fake_stdio(monkeypatch, json.dumps({"tool_input": {}}))  # tool_name missing
    called = False

    def decide(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any] | None:
        nonlocal called
        called = True
        return None

    rc = hr.run_tool_hook("gate", decide)
    assert rc == 0
    assert called is False
    assert "event missing tool_name/tool_input" in capsys.readouterr().err


def test_run_tool_hook_malformed_json_fails_open(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("{bad"))
    rc = hr.run_tool_hook("gate", lambda tn, ti: hr.build_deny("x"))
    assert rc == 0
    assert "malformed stdin JSON" in capsys.readouterr().err
