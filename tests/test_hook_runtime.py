"""Tests for ``scripts/_hook_runtime.py``.

Verifies the shared PreToolUse/PostToolUse I/O plumbing byte-for-byte:

- ``read_event`` parses valid JSON, treats empty/whitespace stdin as ``{}``,
  and fails open (returns ``None`` + ``::error::`` line) on malformed JSON.
- ``emit_decision`` writes compact JSON for a decision and nothing for ``None``.
- The stream functions read ``sys.stdin``/write ``sys.stdout``/``sys.stderr`` at
  call time, so monkeypatching those streams works (the contract the migrated
  gates' tests rely on).

Refs #1005.
"""

from __future__ import annotations

import io
import json

import _hook_runtime as hr
import pytest

pytestmark = pytest.mark.shard_preflight


class TestReadEvent:
    def test_parses_valid_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = {"tool_name": "Bash", "tool_input": {"command": "ls"}}
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        assert hr.read_event("demo_gate") == payload

    def test_empty_stdin_yields_empty_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert hr.read_event("demo_gate") == {}

    def test_whitespace_stdin_yields_empty_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("   \n\t "))
        assert hr.read_event("demo_gate") == {}

    def test_malformed_json_fails_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))
        monkeypatch.setattr("sys.stderr", stderr_buf)
        assert hr.read_event("demo_gate") is None
        err = stderr_buf.getvalue()
        assert err.startswith("::error::demo_gate: malformed stdin JSON: ")
        assert err.endswith("\n")

    def test_script_name_is_interpolated(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdin", io.StringIO("not json"))
        monkeypatch.setattr("sys.stderr", stderr_buf)
        hr.read_event("other_gate")
        assert "::error::other_gate: malformed stdin JSON:" in stderr_buf.getvalue()


class TestEmitDecision:
    def test_none_writes_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        hr.emit_decision(None)
        assert stdout_buf.getvalue() == ""

    def test_decision_is_compact_json(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        decision = {"permissionDecision": "deny", "decisionReason": "nope"}
        hr.emit_decision(decision)
        assert stdout_buf.getvalue() == json.dumps(decision)

    def test_output_matches_legacy_inline_form(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # The pre-refactor tail was ``sys.stdout.write(json.dumps(decision))``.
        decision = {"permissionDecision": "deny", "decisionReason": "x\ny"}
        legacy = json.dumps(decision)
        stdout_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        hr.emit_decision(decision)
        assert stdout_buf.getvalue() == legacy
