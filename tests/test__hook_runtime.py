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


@pytest.fixture(autouse=True)
def _clear_gate_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start every test in the default ``block`` mode regardless of the host env.

    ``CLAUDE_GATE_MODE`` is read from the process environment by
    ``emit_decision``; clearing it here keeps the existing block-mode tests
    deterministic and lets the audit tests opt in explicitly.
    """
    monkeypatch.delenv("CLAUDE_GATE_MODE", raising=False)


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
    out = _fake_stdio(monkeypatch, json.dumps({"tool_name": "Bash", "tool_input": {"command": "x"}}))
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


# ---------------------------------------------------------------------------
# emit_decision audit mode (CLAUDE_GATE_MODE)
# ---------------------------------------------------------------------------

_STOP_BLOCK: dict[str, Any] = {"decision": "block", "reason": "stop blocked"}


def _capture_streams(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[io.StringIO, io.StringIO]:
    """Replace stdout/stderr with StringIO buffers and return ``(out, err)``."""
    out, err = io.StringIO(), io.StringIO()
    monkeypatch.setattr("sys.stdout", out)
    monkeypatch.setattr("sys.stderr", err)
    return out, err


def test_emit_decision_default_blocks(monkeypatch: pytest.MonkeyPatch) -> None:
    # No CLAUDE_GATE_MODE -> original block behaviour, byte-for-byte.
    out, err = _capture_streams(monkeypatch)
    hr.emit_decision(_STOP_BLOCK, "mygate")
    assert json.loads(out.getvalue()) == _STOP_BLOCK
    assert err.getvalue() == ""


def test_emit_decision_audit_downgrades_stop_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_GATE_MODE", "audit")
    out, err = _capture_streams(monkeypatch)
    hr.emit_decision(_STOP_BLOCK, "mygate")
    assert out.getvalue() == ""  # downgraded to pass-through
    assert "::warning::mygate: [AUDIT] suppressed blocking decision" in err.getvalue()
    assert "stop blocked" in err.getvalue()


def test_emit_decision_audit_downgrades_pretooluse_deny(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_GATE_MODE", "audit")
    out, err = _capture_streams(monkeypatch)
    hr.emit_decision(hr.build_deny("nope"), "g")
    assert out.getvalue() == ""
    assert "[AUDIT]" in err.getvalue()
    assert "nope" in err.getvalue()


def test_emit_decision_audit_downgrades_flat_deny(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The flat deny shape used by gate_gh_cli / gate_update_pr_branch /
    # gate_mcp_github_uncovered / gate_issue_close_comment is also recognised.
    monkeypatch.setenv("CLAUDE_GATE_MODE", "audit")
    flat = {"permissionDecision": "deny", "decisionReason": "flat reason"}
    out, err = _capture_streams(monkeypatch)
    hr.emit_decision(flat, "g")
    assert out.getvalue() == ""
    assert "[AUDIT]" in err.getvalue()
    assert "flat reason" in err.getvalue()


def test_emit_decision_audit_keeps_non_auditable_blocking(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Security-boundary gates pass auditable=False -> always block.
    monkeypatch.setenv("CLAUDE_GATE_MODE", "audit")
    out, err = _capture_streams(monkeypatch)
    hr.emit_decision(hr.build_deny("critical"), "secgate", auditable=False)
    decision = json.loads(out.getvalue())
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert err.getvalue() == ""


def test_emit_decision_audit_passes_non_blocking_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # An allow / non-blocking decision is emitted unchanged even in audit mode.
    monkeypatch.setenv("CLAUDE_GATE_MODE", "audit")
    allow = {"hookSpecificOutput": {"permissionDecision": "allow"}}
    out, err = _capture_streams(monkeypatch)
    hr.emit_decision(allow, "g")
    assert json.loads(out.getvalue()) == allow
    assert err.getvalue() == ""


def test_emit_decision_audit_default_label_without_script_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_GATE_MODE", "audit")
    out, err = _capture_streams(monkeypatch)
    hr.emit_decision(_STOP_BLOCK)
    assert out.getvalue() == ""
    assert "::warning::gate: [AUDIT]" in err.getvalue()


@pytest.mark.parametrize("value", ["audit", "AUDIT", " Audit "])
def test_audit_mode_active_true(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("CLAUDE_GATE_MODE", value)
    assert hr._audit_mode_active() is True


@pytest.mark.parametrize("value", ["", "block", "BLOCK", "off", "1", "audited"])
def test_audit_mode_active_false(monkeypatch: pytest.MonkeyPatch, value: str) -> None:
    monkeypatch.setenv("CLAUDE_GATE_MODE", value)
    assert hr._audit_mode_active() is False


def test_run_tool_hook_auditable_false_blocks_under_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_GATE_MODE", "audit")
    out, _err = _capture_streams(monkeypatch)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {}})))
    rc = hr.run_tool_hook("secgate", lambda tn, ti: hr.build_deny("x"), auditable=False)
    assert rc == 0
    assert json.loads(out.getvalue())["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_run_event_hook_audit_uses_script_name_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_GATE_MODE", "audit")
    out, err = _capture_streams(monkeypatch)
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"tool_name": "Bash", "tool_input": {}})))
    rc = hr.run_event_hook("mygate", lambda ev: hr.build_deny("z"))
    assert rc == 0
    assert out.getvalue() == ""  # auditable default -> downgraded
    assert "::warning::mygate: [AUDIT]" in err.getvalue()
