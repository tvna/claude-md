"""Tests for ``scripts/gate_merge_retro_survey_askuserquestion.py``.

Covers:
- Merge with a prior survey marker: allowed (None).
- Merge without a survey marker: denied; reason names the PR and the
  satisfaction-first / scenario-branch flow.
- Non-merge tools: always allowed.
- Float / string / invalid pullNumber coercion.
- Recorder: writes the marker; rejects a missing / invalid PR number.
- Fail-open on malformed or non-dict stdin.
- main() dispatch between gate and recorder.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gate_merge_retro_survey_askuserquestion as gate

pytestmark = pytest.mark.shard_preflight


class TestDecide:
    def test_merge_with_marker_is_allowed(self, tmp_path: Path) -> None:
        marker_dir = tmp_path / "survey"
        marker_dir.mkdir()
        (marker_dir / "42").touch()
        original = gate._MARKER_DIR
        gate._MARKER_DIR = marker_dir
        try:
            result = gate.decide(gate._TARGET_TOOL, {"pullNumber": 42})
        finally:
            gate._MARKER_DIR = original
        assert result is None

    def test_merge_without_marker_is_denied(self, tmp_path: Path) -> None:
        empty = tmp_path / "survey"
        empty.mkdir()
        original = gate._MARKER_DIR
        gate._MARKER_DIR = empty
        try:
            result = gate.decide(gate._TARGET_TOOL, {"pullNumber": 99})
        finally:
            gate._MARKER_DIR = original
        assert result is not None
        assert result["permissionDecision"] == "deny"
        reason = result["decisionReason"]
        assert "99" in reason
        assert "AskUserQuestion" in reason
        assert "SATISFACTION first" in reason
        assert "--record 99" in reason

    def test_other_tool_is_allowed(self) -> None:
        assert gate.decide("mcp__github__pull_request_read", {"pullNumber": 5}) is None

    def test_string_pull_number_is_denied(self, tmp_path: Path) -> None:
        empty = tmp_path / "survey"
        empty.mkdir()
        original = gate._MARKER_DIR
        gate._MARKER_DIR = empty
        try:
            result = gate.decide(gate._TARGET_TOOL, {"pullNumber": "77"})
        finally:
            gate._MARKER_DIR = original
        assert result is not None
        assert result["permissionDecision"] == "deny"

    def test_float_pull_number_is_coerced(self, tmp_path: Path) -> None:
        marker_dir = tmp_path / "survey"
        marker_dir.mkdir()
        (marker_dir / "8").touch()
        original = gate._MARKER_DIR
        gate._MARKER_DIR = marker_dir
        try:
            result = gate.decide(gate._TARGET_TOOL, {"pullNumber": 8.0})
        finally:
            gate._MARKER_DIR = original
        assert result is None

    def test_missing_pull_number_is_allowed(self) -> None:
        assert gate.decide(gate._TARGET_TOOL, {}) is None

    def test_bool_pull_number_is_rejected(self) -> None:
        # bool is an int subclass; it must not be treated as a PR number.
        assert gate.decide(gate._TARGET_TOOL, {"pullNumber": True}) is None


class TestRecord:
    def test_record_creates_marker(self, tmp_path: Path) -> None:
        marker_dir = tmp_path / "survey"
        original = gate._MARKER_DIR
        gate._MARKER_DIR = marker_dir
        try:
            assert gate.record(55) is True
        finally:
            gate._MARKER_DIR = original
        assert (marker_dir / "55").exists()


class TestRunGate:
    def test_malformed_stdin_is_fail_open(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("not json {{{"))
        assert gate.run_gate() == 0
        assert capsys.readouterr().out == ""

    def test_empty_stdin_is_fail_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert gate.run_gate() == 0

    def test_non_dict_event_is_fail_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO('"a-string"'))
        assert gate.run_gate() == 0

    def test_non_string_tool_name_is_fail_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = json.dumps({"tool_name": 123, "tool_input": {"pullNumber": 1}})
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        assert gate.run_gate() == 0

    def test_non_dict_tool_input_is_coerced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # tool_input is a list; the gate coerces it to {} -> no pullNumber -> allow.
        payload = json.dumps({"tool_name": gate._TARGET_TOOL, "tool_input": ["bad"]})
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        assert gate.run_gate() == 0

    def test_decide_exception_is_fail_open(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def _boom(_tool: str, _input: dict[str, object]) -> dict[str, object]:
            raise RuntimeError("kaboom")

        monkeypatch.setattr(gate, "decide", _boom)
        payload = json.dumps({"tool_name": gate._TARGET_TOOL, "tool_input": {"pullNumber": 3}})
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        assert gate.run_gate() == 0
        assert "kaboom" in capsys.readouterr().err

    def test_deny_written_to_stdout(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path
    ) -> None:
        empty = tmp_path / "survey"
        empty.mkdir()
        original = gate._MARKER_DIR
        gate._MARKER_DIR = empty
        payload = json.dumps(
            {"tool_name": gate._TARGET_TOOL, "tool_input": {"pullNumber": 7}}
        )
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        try:
            assert gate.run_gate() == 0
        finally:
            gate._MARKER_DIR = original
        parsed = json.loads(capsys.readouterr().out)
        assert parsed["permissionDecision"] == "deny"


class TestRunRecord:
    def test_records_pr_number(self, tmp_path: Path) -> None:
        marker_dir = tmp_path / "survey"
        original = gate._MARKER_DIR
        gate._MARKER_DIR = marker_dir
        try:
            assert gate.run_record("11") == 0
        finally:
            gate._MARKER_DIR = original
        assert (marker_dir / "11").exists()

    def test_invalid_pr_number_is_fail_open(self, tmp_path: Path) -> None:
        marker_dir = tmp_path / "survey"
        original = gate._MARKER_DIR
        gate._MARKER_DIR = marker_dir
        try:
            assert gate.run_record("nope") == 0
        finally:
            gate._MARKER_DIR = original
        assert not marker_dir.exists()


class TestMain:
    def test_default_dispatches_to_gate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called: list[str] = []

        def _gate() -> int:
            called.append("gate")
            return 0

        def _record(_pr: str) -> int:
            called.append("record")
            return 0

        monkeypatch.setattr(gate, "run_gate", _gate)
        monkeypatch.setattr(gate, "run_record", _record)
        assert gate.main([]) == 0
        assert called == ["gate"]

    def test_record_flag_dispatches_to_recorder(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called: list[str] = []

        def _gate() -> int:
            called.append("gate")
            return 0

        def _record(_pr: str) -> int:
            called.append("record")
            return 0

        monkeypatch.setattr(gate, "run_gate", _gate)
        monkeypatch.setattr(gate, "run_record", _record)
        assert gate.main(["--record", "12"]) == 0
        assert called == ["record"]
