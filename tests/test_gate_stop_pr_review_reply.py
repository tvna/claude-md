"""Tests for ``scripts/gate_stop_pr_review_reply.py`` (Stop hook).

Covers heuristic helpers and evaluate() gate logic. main() is exercised
via monkeypatched stdin in the integration class.

Refs #1768, #1860.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import gate_stop_pr_review_reply as gate
import pytest

pytestmark = pytest.mark.shard_ci_ops


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _user(text: str = "hi") -> dict[str, Any]:
    return {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": text}]}}


def _user_str_content(text: str) -> dict[str, Any]:
    """User message with a raw string (not a list) as content."""
    return {"type": "user", "message": {"role": "user", "content": text}}


def _assistant(*blocks: dict[str, Any]) -> dict[str, Any]:
    return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks)}}


def _tool(name: str, **kwargs: Any) -> dict[str, Any]:
    return {"type": "tool_use", "name": name, "input": kwargs}


def _webhook(body: str) -> dict[str, Any]:
    return _user(f"<github-webhook-activity>\n{body}\n</github-webhook-activity>")


# Canned webhook fixtures
REVIEW_COMMENT_WEBHOOK = _webhook("PR #42 review_comment: please fix the type annotation.")
CHANGES_REQUESTED_WEBHOOK = _webhook("PR #42 Changes requested by reviewer.")
PULL_REQUEST_REVIEW_WEBHOOK = _webhook("pull_request_review submitted on PR #42.")
CI_WEBHOOK = _webhook("CI: lint-scripts-pytest (preflight) passed.")
PUSH_WEBHOOK = _webhook("PR #42: new commit pushed to branch.")

REPLY = _tool("mcp__github__add_reply_to_pull_request_comment", comment_id=1)
PENDING_REPLY = _tool("mcp__github__add_comment_to_pending_review", body="acknowledged")
REVIEW_WRITE = _tool("mcp__github__pull_request_review_write", body="LGTM")
BASH_TOOL = _tool("Bash", command="ls")


# ---------------------------------------------------------------------------
# is_review_webhook
# ---------------------------------------------------------------------------


class TestIsReviewWebhook:
    def test_review_comment_marker_matches(self) -> None:
        assert gate.is_review_webhook(REVIEW_COMMENT_WEBHOOK)

    def test_changes_requested_marker_matches(self) -> None:
        assert gate.is_review_webhook(CHANGES_REQUESTED_WEBHOOK)

    def test_pull_request_review_marker_matches(self) -> None:
        assert gate.is_review_webhook(PULL_REQUEST_REVIEW_WEBHOOK)

    def test_REVIEW_COMMENT_uppercase_matches(self) -> None:
        assert gate.is_review_webhook(_webhook("REVIEW_COMMENT event"))

    def test_changes_requested_lowercase_matches(self) -> None:
        assert gate.is_review_webhook(_webhook("changes_requested by bob"))

    def test_ci_webhook_does_not_match(self) -> None:
        assert not gate.is_review_webhook(CI_WEBHOOK)

    def test_push_webhook_does_not_match(self) -> None:
        assert not gate.is_review_webhook(PUSH_WEBHOOK)

    def test_plain_user_message_does_not_match(self) -> None:
        assert not gate.is_review_webhook(_user("Hello, please fix the bug."))

    def test_assistant_entry_does_not_match(self) -> None:
        assert not gate.is_review_webhook(_assistant(_tool("AskUserQuestion")))

    def test_string_content_with_review_matches(self) -> None:
        # content can be a raw string rather than a list of blocks
        entry = _user_str_content("<github-webhook-activity>pull_request_review done</github-webhook-activity>")
        assert gate.is_review_webhook(entry)

    def test_webhook_tag_without_review_marker_does_not_match(self) -> None:
        assert not gate.is_review_webhook(_webhook("PR merged successfully."))

    # --- human-readable system description format (refs #1860) ---

    def test_system_review_comment_description_matches(self) -> None:
        # Actual format delivered by Claude Code system for inline comments.
        msg = "The following is a GitHub review comment left on the PR."
        assert gate.is_review_webhook(_webhook(msg))

    def test_system_review_description_matches(self) -> None:
        # Actual format delivered by Claude Code system for top-level reviews.
        msg = "The following is a GitHub review left on the PR."
        assert gate.is_review_webhook(_webhook(msg))

    def test_system_ci_description_does_not_match(self) -> None:
        msg = "The following is a CI failure on the PR."
        assert not gate.is_review_webhook(_webhook(msg))


# ---------------------------------------------------------------------------
# has_reply_tool_call
# ---------------------------------------------------------------------------


class TestHasReplyToolCall:
    def test_reply_after_webhook_returns_true(self) -> None:
        entries = [REVIEW_COMMENT_WEBHOOK, _assistant(REPLY)]
        assert gate.has_reply_tool_call(entries, 0)

    def test_add_comment_to_pending_review_counts(self) -> None:
        entries = [REVIEW_COMMENT_WEBHOOK, _assistant(PENDING_REPLY)]
        assert gate.has_reply_tool_call(entries, 0)

    def test_pull_request_review_write_counts(self) -> None:
        entries = [REVIEW_COMMENT_WEBHOOK, _assistant(REVIEW_WRITE)]
        assert gate.has_reply_tool_call(entries, 0)

    def test_non_reply_tool_does_not_count(self) -> None:
        entries = [REVIEW_COMMENT_WEBHOOK, _assistant(BASH_TOOL)]
        assert not gate.has_reply_tool_call(entries, 0)

    def test_reply_before_webhook_does_not_count(self) -> None:
        entries = [_assistant(REPLY), REVIEW_COMMENT_WEBHOOK]
        assert not gate.has_reply_tool_call(entries, 1)

    def test_no_entries_after_returns_false(self) -> None:
        entries = [REVIEW_COMMENT_WEBHOOK]
        assert not gate.has_reply_tool_call(entries, 0)

    def test_reply_two_entries_later_counts(self) -> None:
        entries = [REVIEW_COMMENT_WEBHOOK, _assistant(BASH_TOOL), _assistant(REPLY)]
        assert gate.has_reply_tool_call(entries, 0)


# ---------------------------------------------------------------------------
# find_unaddressed_review_webhooks
# ---------------------------------------------------------------------------


class TestFindUnaddressedReviewWebhooks:
    def test_no_webhooks_returns_empty(self) -> None:
        entries = [_user(), _assistant(BASH_TOOL)]
        assert gate.find_unaddressed_review_webhooks(entries) == []

    def test_ci_webhook_ignored(self) -> None:
        entries = [CI_WEBHOOK, _assistant(BASH_TOOL)]
        assert gate.find_unaddressed_review_webhooks(entries) == []

    def test_addressed_webhook_not_returned(self) -> None:
        entries = [REVIEW_COMMENT_WEBHOOK, _assistant(REPLY)]
        assert gate.find_unaddressed_review_webhooks(entries) == []

    def test_unaddressed_webhook_returned(self) -> None:
        entries = [REVIEW_COMMENT_WEBHOOK, _assistant(BASH_TOOL)]
        assert gate.find_unaddressed_review_webhooks(entries) == [0]

    def test_second_unaddressed_webhook_returned(self) -> None:
        # First addressed, second not
        entries = [
            REVIEW_COMMENT_WEBHOOK,
            _assistant(REPLY),
            CHANGES_REQUESTED_WEBHOOK,
            _assistant(BASH_TOOL),
        ]
        assert gate.find_unaddressed_review_webhooks(entries) == [2]

    def test_both_unaddressed_webhooks_returned(self) -> None:
        entries = [REVIEW_COMMENT_WEBHOOK, _assistant(BASH_TOOL), CHANGES_REQUESTED_WEBHOOK]
        unaddressed = gate.find_unaddressed_review_webhooks(entries)
        assert 0 in unaddressed
        assert 2 in unaddressed


# ---------------------------------------------------------------------------
# evaluate
# ---------------------------------------------------------------------------


class TestEvaluate:
    def test_blocks_when_unaddressed_review_webhook(self) -> None:
        entries = [REVIEW_COMMENT_WEBHOOK, _assistant(BASH_TOOL)]
        decision = gate.evaluate({}, entries)
        assert decision is not None
        assert decision.get("decision") == "block"
        assert "review" in decision.get("reason", "").lower()

    def test_passes_when_webhook_addressed(self) -> None:
        entries = [REVIEW_COMMENT_WEBHOOK, _assistant(REPLY)]
        assert gate.evaluate({}, entries) is None

    def test_passes_when_no_review_webhooks(self) -> None:
        entries = [CI_WEBHOOK, _assistant(BASH_TOOL)]
        assert gate.evaluate({}, entries) is None

    def test_passes_with_empty_entries(self) -> None:
        assert gate.evaluate({}, []) is None

    def test_stop_hook_active_is_noop(self) -> None:
        entries = [REVIEW_COMMENT_WEBHOOK, _assistant(BASH_TOOL)]
        assert gate.evaluate({"stop_hook_active": True}, entries) is None

    def test_non_stop_event_name_is_noop(self) -> None:
        entries = [REVIEW_COMMENT_WEBHOOK, _assistant(BASH_TOOL)]
        assert gate.evaluate({"hook_event_name": "PreToolUse"}, entries) is None

    def test_stop_event_name_triggers_check(self) -> None:
        entries = [REVIEW_COMMENT_WEBHOOK, _assistant(BASH_TOOL)]
        assert gate.evaluate({"hook_event_name": "Stop"}, entries) is not None


# ---------------------------------------------------------------------------
# load_transcript
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# _content_blocks / _entry_role / _entry_text edge cases (coverage lines
# 100, 103, 107, 113, 119-120, 126, 129, 141)
# ---------------------------------------------------------------------------


class TestContentBlocks:
    def test_non_dict_entry_returns_empty(self) -> None:
        assert gate._content_blocks("not-a-dict") == []

    def test_non_dict_message_returns_empty(self) -> None:
        assert gate._content_blocks({"message": "string"}) == []

    def test_non_list_content_returns_empty(self) -> None:
        assert gate._content_blocks({"message": {"content": "raw string"}}) == []


class TestEntryRole:
    def test_non_dict_entry_returns_empty_string(self) -> None:
        assert gate._entry_role(42) == ""

    def test_entry_type_used_when_no_message(self) -> None:
        # Falls back to entry["type"] when message has no role key.
        assert gate._entry_role({"type": "tool_result"}) == "tool_result"

    def test_entry_type_non_string_returns_empty(self) -> None:
        assert gate._entry_role({"type": 99}) == ""


class TestEntryText:
    def test_non_dict_entry_returns_empty_string(self) -> None:
        assert gate._entry_text(None) == ""

    def test_non_dict_message_returns_empty_string(self) -> None:
        assert gate._entry_text({"message": 42}) == ""

    def test_non_str_non_list_content_returns_empty_string(self) -> None:
        assert gate._entry_text({"message": {"content": 99}}) == ""


class TestLoadTranscript:
    def test_returns_empty_for_missing_path(self) -> None:
        assert gate.load_transcript("/nonexistent/path.jsonl") == []

    def test_returns_empty_for_none(self) -> None:
        assert gate.load_transcript(None) == []

    def test_returns_empty_for_empty_string(self) -> None:
        assert gate.load_transcript("") == []

    def test_parses_valid_jsonl(self, tmp_path: Path) -> None:
        f = tmp_path / "transcript.jsonl"
        entry = {"type": "user", "message": {"role": "user", "content": "hi"}}
        f.write_text(json.dumps(entry) + "\n")
        entries = gate.load_transcript(str(f))
        assert len(entries) == 1
        assert entries[0]["type"] == "user"

    def test_skips_malformed_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "transcript.jsonl"
        f.write_text('{"ok": 1}\nNOT JSON\n{"ok": 2}\n')
        entries = gate.load_transcript(str(f))
        assert len(entries) == 2

    def test_skips_blank_lines(self, tmp_path: Path) -> None:
        f = tmp_path / "transcript.jsonl"
        f.write_text('{"ok": 1}\n\n   \n{"ok": 2}\n')
        entries = gate.load_transcript(str(f))
        assert len(entries) == 2


# ---------------------------------------------------------------------------
# main() integration
# ---------------------------------------------------------------------------


class TestMain:
    def _run(self, event: dict[str, Any], entries: list[Any], monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> tuple[str, int]:
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("\n".join(json.dumps(e) for e in entries))
        event["transcript_path"] = str(transcript)
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
        stdout_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        rc = gate.main()
        return stdout_buf.getvalue(), rc

    def test_main_blocks_on_unaddressed_review(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        entries = [REVIEW_COMMENT_WEBHOOK, _assistant(BASH_TOOL)]
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("\n".join(json.dumps(e) for e in entries))
        event = {"hook_event_name": "Stop", "transcript_path": str(transcript)}
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
        stdout_capture = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_capture)
        rc = gate.main()
        assert rc == 0  # hook exits 0 always (fail-open)
        out = stdout_capture.getvalue()
        assert out  # non-empty output = block decision was emitted
        decision = json.loads(out)
        assert decision.get("decision") == "block"

    def test_main_passes_on_addressed_review(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        entries = [REVIEW_COMMENT_WEBHOOK, _assistant(REPLY)]
        transcript = tmp_path / "t.jsonl"
        transcript.write_text("\n".join(json.dumps(e) for e in entries))
        event = {"hook_event_name": "Stop", "transcript_path": str(transcript)}
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
        stdout_capture = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_capture)
        rc = gate.main()
        assert rc == 0
        assert stdout_capture.getvalue() == ""  # no block emitted

    def test_main_returns_zero_when_read_event_returns_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # read_event() returns None on invalid/empty stdin -> main exits 0.
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        rc = gate.main()
        assert rc == 0

    def test_main_fails_open_on_exception(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        # If evaluate() raises, main catches it and exits 0 (fail-open).
        transcript = tmp_path / "t.jsonl"
        transcript.write_text(json.dumps(REVIEW_COMMENT_WEBHOOK))
        event = {"hook_event_name": "Stop", "transcript_path": str(transcript)}
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
        stderr_capture = io.StringIO()
        monkeypatch.setattr("sys.stderr", stderr_capture)
        with patch.object(gate, "evaluate", side_effect=RuntimeError("boom")):
            rc = gate.main()
        assert rc == 0
        assert "boom" in stderr_capture.getvalue()
