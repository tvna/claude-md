"""Tests for ``scripts/gate_decision_handoff_askuserquestion.py`` (Stop hook).

Pure heuristics get focused unit tests; ``main()`` is exercised by
monkeypatching stdin and pointing the event at a temp transcript file.

Refs #1044.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import gate_decision_handoff_askuserquestion as gate
import pytest

pytestmark = pytest.mark.shard_ci_ops


def _assistant(*blocks: dict[str, Any]) -> dict[str, Any]:
    return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}}


def _user(text: str = "hi") -> dict[str, Any]:
    return {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}


def _text(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


def _tool(name: str) -> dict[str, Any]:
    return {"type": "tool_use", "name": name, "input": {}}


# ---------------------------------------------------------------------------
# delegates_decision
# ---------------------------------------------------------------------------


class TestDelegatesDecision:
    def test_choice_cue_with_question_matches(self) -> None:
        assert gate.delegates_decision("どちらにしますか？")

    def test_english_which_matches(self) -> None:
        assert gate.delegates_decision("Which option do you want?")

    def test_enumerated_options_match(self) -> None:
        assert gate.delegates_decision("Pick one?\n- A first\n- B second")

    def test_single_option_line_does_not_match(self) -> None:
        assert not gate.delegates_decision("Should I?\n- only one")

    def test_plain_yes_no_question_does_not_match(self) -> None:
        # No choice cue and no enumeration -> intentionally out of scope.
        assert not gate.delegates_decision("進めてよいですか？")

    def test_statement_without_question_mark_does_not_match(self) -> None:
        assert not gate.delegates_decision("I picked option A for you.")

    def test_empty_does_not_match(self) -> None:
        assert not gate.delegates_decision("")


# ---------------------------------------------------------------------------
# transcript helpers
# ---------------------------------------------------------------------------


class TestTurnHelpers:
    def test_final_turn_is_assistant_after_last_user(self) -> None:
        entries = [_assistant(_text("old")), _user(), _assistant(_text("new"))]
        turn = gate.final_assistant_turn(entries)
        assert gate.last_text_block(turn) == "new"

    def test_no_assistant_after_user_is_empty(self) -> None:
        assert gate.final_assistant_turn([_user()]) == []

    def test_turn_used_tool_detects_name(self) -> None:
        turn = [_assistant(_tool("AskUserQuestion"))]
        assert gate.turn_used_tool(turn, "AskUserQuestion")
        assert not gate.turn_used_tool(turn, "ExitPlanMode")

    def test_last_text_block_returns_latest(self) -> None:
        turn = [_assistant(_text("first"), _text("second"))]
        assert gate.last_text_block(turn) == "second"


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------


class TestEvaluate:
    def _entries(self, *blocks: dict[str, Any]) -> list[Any]:
        return [_user(), _assistant(*blocks)]

    def test_blocks_on_unaided_choice(self) -> None:
        decision = gate.evaluate({}, self._entries(_text("どちらにしますか？")))
        assert decision == {"decision": "block", "reason": gate._BLOCK_REASON}

    def test_stop_hook_active_is_noop(self) -> None:
        entries = self._entries(_text("どちらにしますか？"))
        assert gate.evaluate({"stop_hook_active": True}, entries) is None

    def test_askuserquestion_already_used_is_noop(self) -> None:
        entries = self._entries(_text("どちらにしますか？"), _tool("AskUserQuestion"))
        assert gate.evaluate({}, entries) is None

    def test_exit_plan_mode_is_noop(self) -> None:
        entries = self._entries(_text("どちらにしますか？"), _tool("ExitPlanMode"))
        assert gate.evaluate({}, entries) is None

    def test_plain_statement_is_noop(self) -> None:
        assert gate.evaluate({}, self._entries(_text("Done."))) is None

    def test_no_entries_is_noop(self) -> None:
        assert gate.evaluate({}, []) is None

    def test_off_target_event_is_noop(self) -> None:
        entries = self._entries(_text("どちらにしますか？"))
        assert gate.evaluate({"hook_event_name": "PreToolUse"}, entries) is None


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
        f.write_text(json.dumps(_user()) + "\n\nnot-json\n" + json.dumps(_assistant(_text("x"))) + "\n")
        entries = gate.load_transcript(str(f))
        assert len(entries) == 2


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    def _run(self, monkeypatch: pytest.MonkeyPatch, stdin: str) -> str:
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        out = io.StringIO()
        monkeypatch.setattr("sys.stdout", out)
        assert gate.main() == 0
        return out.getvalue()

    def test_emits_block_for_unaided_choice(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        f = tmp_path / "t.jsonl"
        f.write_text(json.dumps(_user()) + "\n" + json.dumps(_assistant(_text("どちらにしますか？"))) + "\n")
        out = self._run(monkeypatch, json.dumps({"hook_event_name": "Stop", "transcript_path": str(f)}))
        assert json.loads(out)["decision"] == "block"

    def test_malformed_stdin_fails_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert self._run(monkeypatch, "{not json") == ""

    def test_no_transcript_writes_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert self._run(monkeypatch, json.dumps({"hook_event_name": "Stop"})) == ""
