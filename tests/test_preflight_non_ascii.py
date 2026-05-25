"""Tests for ``scripts/preflight_non_ascii.py`` (Layer 2.5 hook).

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.

Mirrors the table-driven style of ``tests/test_scan_non_ascii.py``.
Pure functions get parametrize cases; the stdin/stdout boundary in
:func:`preflight_non_ascii.main` is exercised with ``monkeypatch`` over
``sys.stdin`` and ``capsys`` over ``sys.stdout``/``sys.stderr``.

Refs #146, umbrella #102.
"""

from __future__ import annotations

import io
import json

import preflight_non_ascii as pna
import pytest
from scan_non_ascii import ACK_MARKER

# ---------------------------------------------------------------------------
# extract_text_fields
# ---------------------------------------------------------------------------


class TestExtractTextFields:
    def test_both_present(self) -> None:
        assert pna.extract_text_fields({"title": "T", "body": "B"}) == ("T", "B")

    def test_missing_keys_become_empty(self) -> None:
        assert pna.extract_text_fields({}) == ("", "")

    def test_none_values_become_empty(self) -> None:
        assert pna.extract_text_fields({"title": None, "body": None}) == ("", "")

    def test_non_string_values_become_empty(self) -> None:
        assert pna.extract_text_fields({"title": 1, "body": ["x"]}) == ("", "")


# ---------------------------------------------------------------------------
# offending_fields
# ---------------------------------------------------------------------------


class TestOffendingFields:
    @pytest.mark.parametrize(
        ("title", "body", "expected"),
        [
            ("ASCII only", "all ascii", []),
            ("日本語", "ascii body", ["title"]),
            ("ascii title", "日本語", ["body"]),
            ("日", "本", ["title", "body"]),
            ("", "", []),
            ("", "🎯", ["body"]),
        ],
    )
    def test_table(
        self, title: str, body: str, expected: list[str]
    ) -> None:
        assert pna.offending_fields(title, body) == expected


# ---------------------------------------------------------------------------
# build_deny_reason
# ---------------------------------------------------------------------------


class TestBuildDenyReason:
    def test_mentions_both_remediation_options(self) -> None:
        reason = pna.build_deny_reason(
            "mcp__github__issue_write", ["title"], r"日本語"
        )
        assert "Translate" in reason
        assert ACK_MARKER in reason
        assert r"日本語" in reason

    def test_names_each_offending_field(self) -> None:
        reason = pna.build_deny_reason(
            "mcp__github__create_pull_request",
            ["title", "body"],
            r"日\n本",
        )
        assert "title and body" in reason

    def test_includes_tool_name(self) -> None:
        reason = pna.build_deny_reason(
            "mcp__github__add_issue_comment", ["body"], r"🎯"
        )
        assert "mcp__github__add_issue_comment" in reason


# ---------------------------------------------------------------------------
# decide
# ---------------------------------------------------------------------------


class TestDecide:
    def test_ascii_only_issue_allows(self) -> None:
        out = pna.decide(
            "mcp__github__issue_write",
            {"title": "Fix bug", "body": "details"},
        )
        assert out is None

    def test_japanese_title_denies(self) -> None:
        out = pna.decide(
            "mcp__github__issue_write",
            {"title": "日本語", "body": ""},
        )
        assert out is not None
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
        assert out["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        assert "title" in reason
        assert ACK_MARKER in reason

    def test_ack_marker_in_body_allows_even_with_non_ascii(self) -> None:
        out = pna.decide(
            "mcp__github__issue_write",
            {"title": "x", "body": f"日本語\n{ACK_MARKER}"},
        )
        assert out is None

    def test_ack_marker_in_body_rescues_non_ascii_title(self) -> None:
        # Parity with scan_non_ascii.classify_action: the marker lives in
        # body and applies globally to the item. A non-ASCII title with an
        # acked body would also yield action=skip server-side, so the hook
        # must not deny here either.
        out = pna.decide(
            "mcp__github__issue_write",
            {"title": "日本語", "body": f"ascii\n{ACK_MARKER}"},
        )
        assert out is None

    def test_comment_with_emoji_denies_with_surrogate_pair(self) -> None:
        out = pna.decide(
            "mcp__github__add_issue_comment",
            {"body": "\U0001f3af"},
        )
        assert out is not None
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        # U+1F3AF (🎯, non-BMP) must round-trip via the UTF-16 surrogate
        # pair so the model sees data, not a 4-byte codepoint.
        assert "\\ud83c\\udfaf" in reason
        # Raw emoji must NOT appear in the escaped block.
        assert "\U0001f3af" not in reason.split("```")[1]

    def test_pr_creation_both_fields_lists_both(self) -> None:
        out = pna.decide(
            "mcp__github__create_pull_request",
            {"title": "日", "body": "本"},
        )
        assert out is not None
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        assert "title and body" in reason

    def test_sub_issue_body_denies(self) -> None:
        out = pna.decide(
            "mcp__github__sub_issue_write",
            {"body": "日本語"},
        )
        assert out is not None
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        assert "body" in reason
        assert "mcp__github__sub_issue_write" in reason

    @pytest.mark.parametrize(
        "tool_name",
        [
            "mcp__github__list_issues",
            "mcp__github__issue_read",
            "mcp__github__search_code",
            "Bash",
            "Read",
        ],
    )
    def test_off_target_tools_allow(self, tool_name: str) -> None:
        out = pna.decide(tool_name, {"title": "日本語", "body": "日本語"})
        assert out is None

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
        out = pna.decide(tool_name, {"title": "日", "body": "日"})
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
        rc = pna.main([])
        captured = capsys.readouterr()
        return rc, captured.out, captured.err

    def test_ascii_event_emits_nothing(
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

    def test_non_ascii_event_emits_deny_json(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        event = {
            "tool_name": "mcp__github__issue_write",
            "tool_input": {"title": "日本語", "body": ""},
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
        # Empty stdin -> event is {} -> missing tool_name -> error log
        assert "::error::" in err
