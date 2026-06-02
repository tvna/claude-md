"""Tests for ``scripts/gate_handoff_retro_survey_askuserquestion.py``.

A Stop hook: when the session transcript shows a created PR with no
recorded survey marker, the gate blocks the stop and hands the agent the
satisfaction-first / scenario-branched survey. Otherwise it lets the stop
proceed. A ``--record`` recorder mode writes the marker.

Covers:
- ``_coerce_pr_number``: int / integral float / decimal str accepted;
  bool, negative, non-integral float, non-decimal str rejected.
- ``created_pr_numbers``: pairs a ``create_pull_request`` tool_use with
  its ``tool_result`` ``/pull/<n>`` URL, canonicalises Codex names,
  ignores unmatched results, and de-duplicates oldest-first.
- ``evaluate``: blocks an unrecorded created PR; no-op with a marker,
  with ``stop_hook_active``, off-target event, or no created PR.
- ``load_transcript``: missing / unreadable / bad-line tolerance.
- ``record`` / ``run_record``: marker write and invalid-PR fail-open.
- ``run_gate``: malformed stdin, no transcript, and block-on-stdout.
- ``main`` dispatch between gate and recorder.

Refs #1073.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import gate_handoff_retro_survey_askuserquestion as gate
import pytest

pytestmark = pytest.mark.shard_ci_ops


def _msg(role: str, *blocks: dict[str, Any]) -> dict[str, Any]:
    return {"type": role, "message": {"role": role, "content": list(blocks)}}


def _create_pr_use(tool_id: str, *, name: str = gate._CREATE_PR_TOOL) -> dict[str, Any]:
    return {"type": "tool_use", "name": name, "id": tool_id, "input": {}}


def _result(tool_use_id: str, content: Any) -> dict[str, Any]:
    return {"type": "tool_result", "tool_use_id": tool_use_id, "content": content}


def _pr_transcript(tool_id: str = "t1", number: int = 42) -> list[Any]:
    return [
        _msg("assistant", _create_pr_use(tool_id)),
        _msg("user", _result(tool_id, f"Created https://github.com/o/r/pull/{number}")),
    ]


# ---------------------------------------------------------------------------
# _coerce_pr_number
# ---------------------------------------------------------------------------


class TestCoercePrNumber:
    def test_positive_int(self) -> None:
        assert gate._coerce_pr_number(42) == 42

    def test_integral_float(self) -> None:
        assert gate._coerce_pr_number(8.0) == 8

    def test_decimal_string(self) -> None:
        assert gate._coerce_pr_number("77") == 77

    def test_bool_rejected(self) -> None:
        assert gate._coerce_pr_number(True) is None

    def test_zero_and_negative_rejected(self) -> None:
        assert gate._coerce_pr_number(0) is None
        assert gate._coerce_pr_number(-3) is None

    def test_non_integral_float_rejected(self) -> None:
        assert gate._coerce_pr_number(8.5) is None

    def test_non_decimal_string_rejected(self) -> None:
        assert gate._coerce_pr_number("nope") is None
        assert gate._coerce_pr_number("-1") is None


# ---------------------------------------------------------------------------
# created_pr_numbers
# ---------------------------------------------------------------------------


class TestCreatedPrNumbers:
    def test_paired_use_and_result(self) -> None:
        assert gate.created_pr_numbers(_pr_transcript("t1", 42)) == [42]

    def test_codex_name_is_canonicalised(self) -> None:
        entries = [
            _msg("assistant", _create_pr_use("c1", name="mcp__codex_apps__github._create_pull_request")),
            _msg("user", _result("c1", "see /pull/13")),
        ]
        assert gate.created_pr_numbers(entries) == [13]

    def test_result_without_matching_use_is_ignored(self) -> None:
        entries = [_msg("user", _result("orphan", "/pull/9"))]
        assert gate.created_pr_numbers(entries) == []

    def test_non_create_tool_is_ignored(self) -> None:
        entries = [
            _msg("assistant", {"type": "tool_use", "name": "mcp__github__merge_pull_request", "id": "m1", "input": {}}),
            _msg("user", _result("m1", "/pull/5")),
        ]
        assert gate.created_pr_numbers(entries) == []

    def test_list_content_result_text_is_read(self) -> None:
        entries = [
            _msg("assistant", _create_pr_use("t1")),
            _msg("user", _result("t1", [{"type": "text", "text": "ok /pull/21"}])),
        ]
        assert gate.created_pr_numbers(entries) == [21]

    def test_result_without_pull_url_is_skipped(self) -> None:
        entries = [
            _msg("assistant", _create_pr_use("t1")),
            _msg("user", _result("t1", "no url here")),
        ]
        assert gate.created_pr_numbers(entries) == []

    def test_dedup_oldest_first(self) -> None:
        entries = [
            _msg("assistant", _create_pr_use("a")),
            _msg("user", _result("a", "/pull/7")),
            _msg("assistant", _create_pr_use("b")),
            _msg("user", _result("b", "/pull/7")),
            _msg("assistant", _create_pr_use("c")),
            _msg("user", _result("c", "/pull/9")),
        ]
        assert gate.created_pr_numbers(entries) == [7, 9]


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------


class TestEvaluate:
    def test_blocks_unrecorded_created_pr(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(gate, "_MARKER_DIR", tmp_path / "empty")
        decision = gate.evaluate({}, _pr_transcript("t1", 99))
        assert decision is not None
        assert decision["decision"] == "block"
        assert "#99" in decision["reason"]
        assert "SATISFACTION first" in decision["reason"]
        assert "--record 99" in decision["reason"]

    def test_recorded_pr_is_noop(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(gate, "_MARKER_DIR", tmp_path)
        (tmp_path / "42").touch()
        assert gate.evaluate({}, _pr_transcript("t1", 42)) is None

    def test_stop_hook_active_is_noop(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(gate, "_MARKER_DIR", tmp_path / "empty")
        assert gate.evaluate({"stop_hook_active": True}, _pr_transcript()) is None

    def test_off_target_event_is_noop(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(gate, "_MARKER_DIR", tmp_path / "empty")
        assert gate.evaluate({"hook_event_name": "PreToolUse"}, _pr_transcript()) is None

    def test_no_created_pr_is_noop(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(gate, "_MARKER_DIR", tmp_path / "empty")
        assert gate.evaluate({}, [_msg("assistant", {"type": "text", "text": "done"})]) is None


# ---------------------------------------------------------------------------
# load_transcript
# ---------------------------------------------------------------------------


class TestLoadTranscript:
    def test_missing_path_is_empty(self) -> None:
        assert gate.load_transcript(None) == []
        assert gate.load_transcript("") == []

    def test_unreadable_path_is_empty(self, tmp_path: Path) -> None:
        assert gate.load_transcript(str(tmp_path / "nope.jsonl")) == []

    def test_reads_jsonl_and_skips_bad_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "t.jsonl"
        f.write_text(json.dumps(_msg("user")) + "\n\nnot-json\n" + json.dumps(_msg("assistant")) + "\n")
        assert len(gate.load_transcript(str(f))) == 2


# ---------------------------------------------------------------------------
# record / run_record
# ---------------------------------------------------------------------------


class TestRecord:
    def test_record_creates_marker(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        marker_dir = tmp_path / "survey"
        monkeypatch.setattr(gate, "_MARKER_DIR", marker_dir)
        assert gate.record(55) is True
        assert (marker_dir / "55").exists()

    def test_run_record_writes_marker(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        marker_dir = tmp_path / "survey"
        monkeypatch.setattr(gate, "_MARKER_DIR", marker_dir)
        assert gate.run_record("11") == 0
        assert (marker_dir / "11").exists()

    def test_run_record_invalid_is_fail_open(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        marker_dir = tmp_path / "survey"
        monkeypatch.setattr(gate, "_MARKER_DIR", marker_dir)
        assert gate.run_record("nope") == 0
        assert not marker_dir.exists()


# ---------------------------------------------------------------------------
# run_gate
# ---------------------------------------------------------------------------


class TestRunGate:
    def _run(self, monkeypatch: pytest.MonkeyPatch, stdin: str) -> str:
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        out = io.StringIO()
        monkeypatch.setattr("sys.stdout", out)
        assert gate.run_gate() == 0
        return out.getvalue()

    def test_malformed_stdin_fails_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert self._run(monkeypatch, "{not json") == ""

    def test_no_transcript_writes_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert self._run(monkeypatch, json.dumps({"hook_event_name": "Stop"})) == ""

    def test_block_written_to_stdout(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        monkeypatch.setattr(gate, "_MARKER_DIR", tmp_path / "empty")
        f = tmp_path / "t.jsonl"
        f.write_text("\n".join(json.dumps(e) for e in _pr_transcript("t1", 7)) + "\n")
        out = self._run(monkeypatch, json.dumps({"hook_event_name": "Stop", "transcript_path": str(f)}))
        assert json.loads(out)["decision"] == "block"

    def test_evaluate_exception_is_fail_open(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        def _boom(_event: dict[str, Any], _entries: list[Any]) -> dict[str, Any]:
            raise RuntimeError("kaboom")

        monkeypatch.setattr(gate, "evaluate", _boom)
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({"hook_event_name": "Stop"})))
        assert gate.run_gate() == 0
        assert "kaboom" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    @staticmethod
    def _spies(monkeypatch: pytest.MonkeyPatch, called: list[str]) -> None:
        def _gate() -> int:
            called.append("gate")
            return 0

        def _record(_pr: str) -> int:
            called.append("record")
            return 0

        monkeypatch.setattr(gate, "run_gate", _gate)
        monkeypatch.setattr(gate, "run_record", _record)

    def test_default_dispatches_to_gate(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called: list[str] = []
        self._spies(monkeypatch, called)
        assert gate.main([]) == 0
        assert called == ["gate"]

    def test_record_flag_dispatches_to_recorder(self, monkeypatch: pytest.MonkeyPatch) -> None:
        called: list[str] = []
        self._spies(monkeypatch, called)
        assert gate.main(["--record", "12"]) == 0
        assert called == ["record"]
