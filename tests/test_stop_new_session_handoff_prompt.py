"""Tests for ``scripts/stop_new_session_handoff_prompt.py`` (Stop hook).

Pure heuristics get focused unit tests; ``main()`` is exercised by
monkeypatching stdin and pointing the event at a temp transcript file -- the
same shape as ``test_gate_decision_handoff_askuserquestion.py``.

Refs #1334.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
import stop_new_session_handoff_prompt as hook

pytestmark = pytest.mark.shard_ci_ops


def _assistant(*blocks: dict[str, Any]) -> dict[str, Any]:
    return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}}


def _user(text: str = "hi") -> dict[str, Any]:
    return {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}


def _text(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}


# ---------------------------------------------------------------------------
# signals_handoff / already_provided
# ---------------------------------------------------------------------------


class TestSignalsHandoff:
    def test_japanese_new_session_matches(self) -> None:
        assert hook.signals_handoff("続きは新規セッションで対応してください。")

    def test_japanese_takeover_matches(self) -> None:
        assert hook.signals_handoff("残りは別セッションに引き継ぎます。")

    def test_english_new_session_matches_case_insensitively(self) -> None:
        assert hook.signals_handoff("Continue this in a NEW SESSION.")

    def test_english_handoff_matches(self) -> None:
        assert hook.signals_handoff("Handoff: the rest is parked on the branch.")

    def test_plain_completion_does_not_match(self) -> None:
        assert not hook.signals_handoff("Done. All tests pass.")

    def test_empty_does_not_match(self) -> None:
        assert not hook.signals_handoff("")


class TestAlreadyProvided:
    def test_fenced_block_counts_as_provided(self) -> None:
        assert hook.already_provided("Paste this:\n```text\ngoal...\n```")

    def test_paste_marker_counts_as_provided(self) -> None:
        assert hook.already_provided("以下をそのまま貼り付けてください。")

    def test_paste_ready_marker_matches_case_insensitively(self) -> None:
        assert hook.already_provided("Here is the PASTE-READY prompt:")

    def test_prose_without_prompt_is_not_provided(self) -> None:
        assert not hook.already_provided("Continue this in a new session please.")


# ---------------------------------------------------------------------------
# transcript helpers
# ---------------------------------------------------------------------------


class TestTurnHelpers:
    def test_final_turn_is_assistant_after_last_user(self) -> None:
        entries = [_assistant(_text("old")), _user(), _assistant(_text("new"))]
        turn = hook.final_assistant_turn(entries)
        assert hook.turn_text(turn) == "new"

    def test_no_assistant_after_user_is_empty(self) -> None:
        assert hook.final_assistant_turn([_user()]) == []

    def test_turn_text_joins_all_text_blocks(self) -> None:
        turn = [_assistant(_text("first"), _text("second"))]
        assert hook.turn_text(turn) == "first\nsecond"

    def test_turn_text_ignores_non_text_and_malformed(self) -> None:
        turn = [_assistant({"type": "tool_use", "name": "X"}, {"type": "text", "text": 5}, _text("ok"))]
        assert hook.turn_text(turn) == "ok"


class TestPrivateHelpers:
    def test_content_blocks_handles_malformed(self) -> None:
        assert hook._content_blocks("nope") == []
        assert hook._content_blocks({"message": "x"}) == []
        assert hook._content_blocks({"message": {"content": "x"}}) == []
        assert hook._content_blocks({"message": {"content": [{"a": 1}, 5]}}) == [{"a": 1}]

    def test_entry_role_prefers_message_role(self) -> None:
        assert hook._entry_role({"message": {"role": "user"}}) == "user"

    def test_entry_role_falls_back_to_type(self) -> None:
        assert hook._entry_role({"type": "assistant"}) == "assistant"
        assert hook._entry_role({"message": {"role": 5}, "type": "user"}) == "user"

    def test_entry_role_empty_for_malformed(self) -> None:
        assert hook._entry_role("nope") == ""
        assert hook._entry_role({}) == ""


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------


class TestEvaluate:
    def _entries(self, *blocks: dict[str, Any]) -> list[Any]:
        return [_user(), _assistant(*blocks)]

    def test_blocks_on_handoff_without_prompt(self) -> None:
        decision = hook.evaluate({}, self._entries(_text("続きは新規セッションでお願いします。")))
        assert decision == {"decision": "block", "reason": hook._BLOCK_REASON}

    def test_handoff_with_fenced_prompt_is_noop(self) -> None:
        entries = self._entries(_text("新規セッション用のプロンプト:\n```text\ngoal\n```"))
        assert hook.evaluate({}, entries) is None

    def test_stop_hook_active_is_noop(self) -> None:
        entries = self._entries(_text("続きは新規セッションでお願いします。"))
        assert hook.evaluate({"stop_hook_active": True}, entries) is None

    def test_no_handoff_cue_is_noop(self) -> None:
        assert hook.evaluate({}, self._entries(_text("Done."))) is None

    def test_no_entries_is_noop(self) -> None:
        assert hook.evaluate({}, []) is None

    def test_off_target_event_is_noop(self) -> None:
        entries = self._entries(_text("続きは新規セッションでお願いします。"))
        assert hook.evaluate({"hook_event_name": "PreToolUse"}, entries) is None


# ---------------------------------------------------------------------------
# load_transcript
# ---------------------------------------------------------------------------


class TestLoadTranscript:
    def test_missing_path_is_empty(self) -> None:
        assert hook.load_transcript(None) == []
        assert hook.load_transcript("") == []

    def test_unreadable_path_is_empty(self, tmp_path: Path) -> None:
        assert hook.load_transcript(str(tmp_path / "nope.jsonl")) == []

    def test_reads_jsonl_and_skips_bad_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "t.jsonl"
        f.write_text(json.dumps(_user()) + "\n\nnot-json\n" + json.dumps(_assistant(_text("x"))) + "\n")
        assert len(hook.load_transcript(str(f))) == 2


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    def _run(self, monkeypatch: pytest.MonkeyPatch, stdin: str) -> str:
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
        out = io.StringIO()
        monkeypatch.setattr("sys.stdout", out)
        assert hook.main() == 0
        return out.getvalue()

    def test_emits_block_for_unaided_handoff(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        f = tmp_path / "t.jsonl"
        f.write_text(json.dumps(_user()) + "\n" + json.dumps(_assistant(_text("続きは新規セッションで。"))) + "\n")
        out = self._run(monkeypatch, json.dumps({"hook_event_name": "Stop", "transcript_path": str(f)}))
        assert json.loads(out)["decision"] == "block"

    def test_provided_prompt_writes_nothing(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        f = tmp_path / "t.jsonl"
        body = "新規セッション用:\n```text\ngoal\n```"
        f.write_text(json.dumps(_user()) + "\n" + json.dumps(_assistant(_text(body))) + "\n")
        out = self._run(monkeypatch, json.dumps({"hook_event_name": "Stop", "transcript_path": str(f)}))
        assert out == ""

    def test_malformed_stdin_fails_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert self._run(monkeypatch, "{not json") == ""

    def test_internal_error_fails_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def boom(_path: object) -> list[Any]:
            raise RuntimeError("kaboom")

        monkeypatch.setattr(hook, "load_transcript", boom)
        err = io.StringIO()
        monkeypatch.setattr("sys.stderr", err)
        out = self._run(monkeypatch, json.dumps({"hook_event_name": "Stop", "transcript_path": "x"}))
        assert out == ""
        assert "kaboom" in err.getvalue()

    def test_no_transcript_writes_nothing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        assert self._run(monkeypatch, json.dumps({"hook_event_name": "Stop"})) == ""
