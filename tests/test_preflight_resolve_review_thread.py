"""Tests for ``scripts/preflight_resolve_review_thread.py``.

Verifies that the gate unconditionally allows mcp__github__resolve_review_thread
(pass-through gate with no deny logic). Refs #887, #1932.
"""

from __future__ import annotations

import io
import json

import preflight_resolve_review_thread as prt
import pytest

pytestmark = pytest.mark.shard_preflight


class TestMain:
    def _run(self, payload: object, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        prt.main()
        return stdout_buf.getvalue(), stderr_buf.getvalue()

    def test_resolve_thread_produces_no_deny(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout, _ = self._run(
            {"tool_name": "mcp__github__resolve_review_thread", "tool_input": {"threadId": "T_123"}},
            monkeypatch,
        )
        assert stdout == ""

    def test_other_tool_produces_no_deny(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout, _ = self._run(
            {"tool_name": "mcp__github__create_pull_request", "tool_input": {}},
            monkeypatch,
        )
        assert stdout == ""

    def test_empty_stdin_is_handled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        result = prt.main()
        assert result == 0
        assert stdout_buf.getvalue() == ""

    def test_returns_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout, _ = self._run(
            {"tool_name": "mcp__github__resolve_review_thread", "tool_input": {}},
            monkeypatch,
        )
        assert stdout == ""

    def test_malformed_json_is_handled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("not valid json {"))
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        result = prt.main()
        assert result == 0
        assert stdout_buf.getvalue() == ""

    def test_emit_decision_exception_is_handled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"tool_name": "x"})))
        monkeypatch.setattr(prt, "emit_decision", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        result = prt.main()
        assert result == 0
        assert "boom" in stderr_buf.getvalue()
