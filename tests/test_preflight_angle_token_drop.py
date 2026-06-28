"""Tests for ``scripts/preflight_angle_token_drop.py`` (PreToolUse hook).

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.

Mirrors the table-driven style of ``tests/test_preflight_non_ascii.py``.
Pure functions get parametrize cases; the stdin/stdout boundary in
:func:`preflight_angle_token_drop.main` is exercised with ``monkeypatch``
over ``sys.stdin`` and ``capsys`` over ``sys.stdout``/``sys.stderr``.

Refs #1673, #1593 (R2).
"""

from __future__ import annotations

import io
import json

import preflight_angle_token_drop as patd
import pytest

pytestmark = pytest.mark.shard_preflight


# ---------------------------------------------------------------------------
# find_angle_tokens
# ---------------------------------------------------------------------------


class TestFindAngleTokens:
    def test_finds_token(self) -> None:
        assert patd.find_angle_tokens("run `git revert <sha>`") == ["<sha>"]

    def test_finds_token_outside_backticks(self) -> None:
        # Backticks do not protect the token from the MCP-write drop (see
        # test_body_policy.TestDetectDroppedAngleTokens.test_detects_dropped_token),
        # so a backtick-wrapped token is reported just like a bare one.
        assert patd.find_angle_tokens("revert <sha> now") == ["<sha>"]

    def test_dedupes_in_document_order(self) -> None:
        assert patd.find_angle_tokens("<b> then <a> then <b>") == ["<b>", "<a>"]

    def test_html_comment_is_stripped(self) -> None:
        # The established <!-- ... --> markers (e.g. the non-ascii-ack
        # opt-out) are stripped before scanning so they are not flagged.
        assert patd.find_angle_tokens("text\n<!-- non-ascii-ack -->") == []

    def test_clean_text_returns_empty(self) -> None:
        assert patd.find_angle_tokens("a clean body with no tokens") == []

    def test_strips_carriage_returns(self) -> None:
        assert patd.find_angle_tokens("a\r\n<x>\r\n") == ["<x>"]


# ---------------------------------------------------------------------------
# extract_text_fields
# ---------------------------------------------------------------------------


class TestExtractTextFields:
    def test_both_present(self) -> None:
        assert patd.extract_text_fields({"title": "T", "body": "B"}) == ("T", "B")

    def test_missing_keys_become_empty(self) -> None:
        assert patd.extract_text_fields({}) == ("", "")

    def test_none_values_become_empty(self) -> None:
        assert patd.extract_text_fields({"title": None, "body": None}) == ("", "")

    def test_non_string_values_become_empty(self) -> None:
        assert patd.extract_text_fields({"title": 1, "body": ["x"]}) == ("", "")


# ---------------------------------------------------------------------------
# offending_tokens
# ---------------------------------------------------------------------------


class TestOffendingTokens:
    def test_clean_input_returns_empty(self) -> None:
        assert patd.offending_tokens("clean title", "clean body") == {}

    def test_body_token_detected(self) -> None:
        assert patd.offending_tokens("clean", "run `git revert <sha>`") == {
            "body": ["<sha>"]
        }

    def test_title_token_detected(self) -> None:
        assert patd.offending_tokens("review PR #<n>", "clean") == {
            "title": ["<n>"]
        }

    def test_both_fields_detected(self) -> None:
        out = patd.offending_tokens("<a>", "<b>")
        assert out == {"title": ["<a>"], "body": ["<b>"]}

    def test_html_comment_is_exempt(self) -> None:
        # The established <!-- ... --> markers (e.g. the non-ascii-ack
        # opt-out) must not be flagged.
        assert patd.offending_tokens("clean", "body\n<!-- non-ascii-ack -->") == {}

    def test_dedupes_repeated_token(self) -> None:
        assert patd.offending_tokens("clean", "<x> then <x>") == {"body": ["<x>"]}


# ---------------------------------------------------------------------------
# build_deny_reason
# ---------------------------------------------------------------------------


class TestBuildDenyReason:
    def test_names_tokens_and_field(self) -> None:
        reason = patd.build_deny_reason(
            "mcp__github__create_pull_request", {"body": ["<sha>"]}
        )
        assert "<sha>" in reason
        assert "body" in reason
        assert "mcp__github__create_pull_request" in reason

    def test_advises_against_backticks(self) -> None:
        # Evidence (test_body_policy.test_detects_dropped_token): a
        # backtick-wrapped <sha> is still dropped, so the remediation must
        # not tell the author to wrap in backticks.
        reason = patd.build_deny_reason("mcp__github__issue_write", {"body": ["<x>"]})
        assert "does NOT protect" in reason

    def test_lists_multiple_fields(self) -> None:
        reason = patd.build_deny_reason(
            "mcp__github__create_pull_request",
            {"title": ["<a>"], "body": ["<b>"]},
        )
        assert "title and body" in reason


# ---------------------------------------------------------------------------
# decide
# ---------------------------------------------------------------------------


class TestDecide:
    def test_clean_issue_allows(self) -> None:
        out = patd.decide(
            "mcp__github__issue_write",
            {"title": "Fix bug", "body": "details here"},
        )
        assert out is None

    def test_body_token_denies(self) -> None:
        out = patd.decide(
            "mcp__github__create_pull_request",
            {"title": "ok", "body": "revert `git revert <sha>`"},
        )
        assert out is not None
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        assert "<sha>" in reason

    def test_title_token_denies(self) -> None:
        out = patd.decide(
            "mcp__github__issue_write",
            {"title": "review PR #<n> loops", "body": "clean"},
        )
        assert out is not None
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        assert "<n>" in reason
        assert "title" in reason

    def test_html_comment_only_allows(self) -> None:
        out = patd.decide(
            "mcp__github__add_issue_comment",
            {"body": "looks good\n<!-- non-ascii-ack -->"},
        )
        assert out is None

    @pytest.mark.parametrize(
        "tool_name",
        [
            "mcp__github__list_issues",
            "mcp__github__issue_read",
            "mcp__github__merge_pull_request",
            "Bash",
            "Read",
        ],
    )
    def test_off_target_tools_allow(self, tool_name: str) -> None:
        out = patd.decide(tool_name, {"title": "<x>", "body": "<y>"})
        assert out is None

    def test_codex_connector_name_is_gated(self) -> None:
        # canonical_github_tool folds the Codex connector name onto its
        # Claude equivalent so a Codex-shaped write is gated too.
        out = patd.decide(
            "mcp__codex_apps__github._create_pull_request",
            {"title": "ok", "body": "<sha>"},
        )
        assert out is not None
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"

    @pytest.mark.parametrize(
        "tool_name",
        [
            "mcp__github__issue_write",
            "mcp__github__add_issue_comment",
            "mcp__github__create_pull_request",
            "mcp__github__update_pull_request",
            "mcp__github__add_reply_to_pull_request_comment",
            "mcp__github__pull_request_review_write",
            "mcp__github__add_comment_to_pending_review",
            "mcp__github__sub_issue_write",
        ],
    )
    def test_every_targeted_tool_is_gated(self, tool_name: str) -> None:
        out = patd.decide(tool_name, {"title": "ok", "body": "<sha>"})
        assert out is not None
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"


# ---------------------------------------------------------------------------
# main (stdin/stdout boundary)
# ---------------------------------------------------------------------------


class TestMain:
    def _run(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        payload: str,
    ) -> tuple[int, str, str]:
        monkeypatch.setattr("sys.stdin", io.StringIO(payload))
        rc = patd.main([])
        captured = capsys.readouterr()
        return rc, captured.out, captured.err

    def test_clean_event_emits_nothing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        event = {
            "tool_name": "mcp__github__issue_write",
            "tool_input": {"title": "Hello", "body": "World"},
        }
        rc, out, err = self._run(monkeypatch, capsys, json.dumps(event))
        assert rc == 0
        assert out == ""
        assert err == ""

    def test_token_event_emits_deny_json(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        event = {
            "tool_name": "mcp__github__create_pull_request",
            "tool_input": {"title": "ok", "body": "see <sha>"},
        }
        rc, out, err = self._run(monkeypatch, capsys, json.dumps(event))
        assert rc == 0
        decision = json.loads(out)
        assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert err == ""

    def test_malformed_json_fails_open(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc, out, err = self._run(monkeypatch, capsys, "{not json")
        assert rc == 0
        assert out == ""
        assert "::error::" in err
        assert "malformed stdin JSON" in err

    def test_missing_tool_name_fails_open(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc, out, err = self._run(monkeypatch, capsys, json.dumps({"foo": "bar"}))
        assert rc == 0
        assert out == ""
        assert "::error::" in err
        assert "missing tool_name" in err

    def test_empty_stdin_fails_open(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        rc, out, err = self._run(monkeypatch, capsys, "")
        assert rc == 0
        assert out == ""
        assert "::error::" in err
