"""Tests for ``scripts/plan_approval_gate.py`` (PostToolUse hook).

Mirrors the table-driven style of ``tests/test_plan_language_context.py``.
Pure functions get focused unit tests; ``main()`` is exercised by monkeypatching
stdin.

Refs #759.
"""

from __future__ import annotations

import io
import json

import plan_approval_gate as pag
import pytest

pytestmark = pytest.mark.shard_ci_ops


# ---------------------------------------------------------------------------
# _is_plan_write
# ---------------------------------------------------------------------------


class TestIsPlanWrite:
    def test_plan_md_write_returns_true(self) -> None:
        assert pag._is_plan_write("Write", {"file_path": "/tmp/claude-plans/plan.md"})

    def test_non_plan_path_returns_false(self) -> None:
        assert not pag._is_plan_write("Write", {"file_path": "/tmp/foo.md"})

    def test_non_md_extension_returns_false(self) -> None:
        assert not pag._is_plan_write("Write", {"file_path": "/tmp/claude-plans/plan.txt"})

    def test_non_write_tool_returns_false(self) -> None:
        assert not pag._is_plan_write("Read", {"file_path": "/tmp/claude-plans/plan.md"})

    def test_missing_file_path_returns_false(self) -> None:
        assert not pag._is_plan_write("Write", {})


# ---------------------------------------------------------------------------
# decide
# ---------------------------------------------------------------------------


class TestDecide:
    def test_plan_write_emits_blocking_prompt(self) -> None:
        event = {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/claude-plans/plan.md"},
        }
        result = pag.decide(event)
        assert result is not None
        assert result["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
        assert "blockingPrompt" in result["hookSpecificOutput"]
        assert "/tmp/claude-plans/plan.md" in result["hookSpecificOutput"]["blockingPrompt"]

    def test_non_plan_write_returns_none(self) -> None:
        event = {
            "tool_name": "Write",
            "tool_input": {"file_path": "/home/user/foo.md"},
        }
        assert pag.decide(event) is None

    def test_non_write_tool_returns_none(self) -> None:
        event = {
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/claude-plans/plan.md"},
        }
        assert pag.decide(event) is None

    def test_non_dict_tool_input_returns_none(self) -> None:
        event = {"tool_name": "Write", "tool_input": None}
        assert pag.decide(event) is None


# ---------------------------------------------------------------------------
# main (stdin boundary)
# ---------------------------------------------------------------------------


class TestMain:
    def _run(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        payload: str,
    ) -> tuple[int, str, str]:
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        rc = pag.main()
        captured = capsys.readouterr()
        return rc, captured.out, captured.err

    def test_plan_write_emits_json(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        payload = json.dumps({
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": "/tmp/claude-plans/my-plan.md"},
        })
        rc, out, err = self._run(monkeypatch, capsys, payload)
        assert rc == 0
        assert err == ""
        result = json.loads(out)
        assert "blockingPrompt" in result["hookSpecificOutput"]
        assert "/tmp/claude-plans/my-plan.md" in result["hookSpecificOutput"]["blockingPrompt"]

    def test_non_plan_write_emits_nothing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        payload = json.dumps({
            "tool_name": "Write",
            "tool_input": {"file_path": "/home/user/notes.md"},
        })
        rc, out, err = self._run(monkeypatch, capsys, payload)
        assert rc == 0
        assert out == ""
        assert err == ""

    def test_non_write_tool_emits_nothing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        payload = json.dumps({
            "tool_name": "Read",
            "tool_input": {"file_path": "/tmp/claude-plans/plan.md"},
        })
        rc, out, err = self._run(monkeypatch, capsys, payload)
        assert rc == 0
        assert out == ""
        assert err == ""

    def test_empty_stdin_emits_nothing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc, out, err = self._run(monkeypatch, capsys, "")
        assert rc == 0
        assert out == ""
        assert err == ""

    def test_malformed_json_fails_open(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc, out, err = self._run(monkeypatch, capsys, "{invalid json")
        assert rc == 0
        assert out == ""
        assert "::error::" in err
