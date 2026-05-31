"""Tests for ``scripts/gate_issue_close_comment.py``.

Covers:
- Close with a prior comment marker: allowed (None).
- Close without a prior comment marker: denied with redirect message.
- Non-close issue_write calls (open, label change): always allowed.
- Other tools: always allowed.
- Fail-open on malformed stdin (run_gate / run_record).
- Recorder: writes marker file; handles missing issue_number gracefully.
"""

from __future__ import annotations

import io
import json
import sys
from collections.abc import Callable
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gate_issue_close_comment as gic

pytestmark = pytest.mark.shard_preflight


class TestDecide:
    def test_close_with_prior_comment_is_allowed(self, tmp_path: Path) -> None:
        marker_dir = tmp_path / "comments"
        marker_dir.mkdir()
        (marker_dir / "42").touch()
        original = gic._COMMENT_DIR
        gic._COMMENT_DIR = marker_dir
        try:
            result = gic.decide("mcp__github__issue_write", {"state": "closed", "issue_number": 42})
        finally:
            gic._COMMENT_DIR = original
        assert result is None

    def test_close_without_prior_comment_is_denied(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "comments"
        empty_dir.mkdir()
        original = gic._COMMENT_DIR
        gic._COMMENT_DIR = empty_dir
        try:
            result = gic.decide("mcp__github__issue_write", {"state": "closed", "issue_number": 99})
        finally:
            gic._COMMENT_DIR = original
        assert result is not None
        assert result["permissionDecision"] == "deny"
        assert "99" in result["decisionReason"]
        assert "add_issue_comment" in result["decisionReason"]

    def test_open_state_is_allowed(self) -> None:
        result = gic.decide("mcp__github__issue_write", {"state": "open", "issue_number": 10})
        assert result is None

    def test_label_change_no_state_is_allowed(self) -> None:
        result = gic.decide("mcp__github__issue_write", {"labels": ["bug"], "issue_number": 10})
        assert result is None

    def test_other_tool_is_allowed(self) -> None:
        result = gic.decide("mcp__github__add_issue_comment", {"state": "closed", "issue_number": 5})
        assert result is None

    def test_close_with_string_issue_number(self, tmp_path: Path) -> None:
        empty_dir = tmp_path / "comments"
        empty_dir.mkdir()
        original = gic._COMMENT_DIR
        gic._COMMENT_DIR = empty_dir
        try:
            result = gic.decide("mcp__github__issue_write", {"state": "closed", "issue_number": "77"})
        finally:
            gic._COMMENT_DIR = original
        assert result is not None
        assert result["permissionDecision"] == "deny"


class TestRecord:
    def test_record_creates_marker_file(self, tmp_path: Path) -> None:
        marker_dir = tmp_path / "comments"
        original = gic._COMMENT_DIR
        gic._COMMENT_DIR = marker_dir
        try:
            ok = gic.record({"issue_number": 55})
        finally:
            gic._COMMENT_DIR = original
        assert ok is True
        assert (marker_dir / "55").exists()

    def test_record_missing_issue_number_returns_false(self, tmp_path: Path) -> None:
        original = gic._COMMENT_DIR
        gic._COMMENT_DIR = tmp_path
        try:
            ok = gic.record({"body": "hello"})
        finally:
            gic._COMMENT_DIR = original
        assert ok is False

    def test_record_string_issue_number(self, tmp_path: Path) -> None:
        marker_dir = tmp_path / "comments"
        original = gic._COMMENT_DIR
        gic._COMMENT_DIR = marker_dir
        try:
            ok = gic.record({"issue_number": "33"})
        finally:
            gic._COMMENT_DIR = original
        assert ok is True
        assert (marker_dir / "33").exists()


class TestRunGate:
    def test_malformed_stdin_is_fail_open(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("not json {{{"))
        rc = gic.run_gate()
        assert rc == 0
        out = capsys.readouterr().out
        assert out == ""

    def test_empty_stdin_is_fail_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert gic.run_gate() == 0

    def test_deny_written_to_stdout(self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], tmp_path: Path) -> None:
        empty_dir = tmp_path / "c"
        empty_dir.mkdir()
        original = gic._COMMENT_DIR
        gic._COMMENT_DIR = empty_dir
        payload = json.dumps({"tool_name": "mcp__github__issue_write", "tool_input": {"state": "closed", "issue_number": 7}})
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        try:
            rc = gic.run_gate()
        finally:
            gic._COMMENT_DIR = original
        assert rc == 0
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert parsed["permissionDecision"] == "deny"


class TestRunRecord:
    def test_malformed_stdin_is_fail_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("bad json"))
        assert gic.run_record() == 0

    def test_records_issue_from_stdin(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        marker_dir = tmp_path / "c"
        original = gic._COMMENT_DIR
        gic._COMMENT_DIR = marker_dir
        payload = json.dumps({"tool_name": "mcp__github__add_issue_comment", "tool_input": {"issue_number": 11}})
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        try:
            rc = gic.run_record()
        finally:
            gic._COMMENT_DIR = original
        assert rc == 0
        assert (marker_dir / "11").exists()

    def test_non_dict_event_is_fail_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A JSON scalar parses fine but is not a dict event -> early return 0.
        monkeypatch.setattr("sys.stdin", io.StringIO('"just-a-string"'))
        assert gic.run_record() == 0

    def test_non_dict_tool_input_is_skipped(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = json.dumps({"tool_name": "mcp__github__add_issue_comment", "tool_input": ["nope"]})
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        assert gic.run_record() == 0


class TestExtractCloseTarget:
    def test_invalid_issue_number_yields_none(self, tmp_path: Path) -> None:
        # state==closed on the target tool, but issue_number is non-numeric:
        # decide() must fall through to allow (None), exercising the final
        # return in _extract_close_target.
        result = gic.decide("mcp__github__issue_write", {"state": "closed", "issue_number": "not-a-number"})
        assert result is None

    def test_zero_issue_number_yields_none(self) -> None:
        result = gic.decide("mcp__github__issue_write", {"state": "closed", "issue_number": 0})
        assert result is None


class TestRunGateGuards:
    def test_non_dict_event_is_fail_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO('"a-string"'))
        assert gic.run_gate() == 0

    def test_non_dict_tool_input_is_coerced(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # tool_input is a list; the gate coerces it to {} and allows the call.
        payload = json.dumps({"tool_name": "mcp__github__issue_write", "tool_input": ["bad"]})
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        assert gic.run_gate() == 0


class TestMain:
    @staticmethod
    def _spy(called: list[str], label: str) -> Callable[[], int]:
        def _fn() -> int:
            called.append(label)
            return 0

        return _fn

    def test_default_dispatches_to_gate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called: list[str] = []
        monkeypatch.setattr(gic, "run_gate", self._spy(called, "gate"))
        monkeypatch.setattr(gic, "run_record", self._spy(called, "record"))
        assert gic.main([]) == 0
        assert called == ["gate"]

    def test_record_flag_dispatches_to_recorder(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called: list[str] = []
        monkeypatch.setattr(gic, "run_gate", self._spy(called, "gate"))
        monkeypatch.setattr(gic, "run_record", self._spy(called, "record"))
        assert gic.main(["--record"]) == 0
        assert called == ["record"]
