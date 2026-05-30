"""Tests for scripts/post_pr_create_body_fix.py.

Verifies that the PostToolUse hook correctly detects the create_pull_request
body-corruption defects (& → &amp; encoding; duplicate footer) and emits
the right additionalContext instruction. Refs issue #892.
"""

from __future__ import annotations

import io
import json

import post_pr_create_body_fix as fix
import pytest

pytestmark = pytest.mark.shard_preflight


# ---------------------------------------------------------------------------
# extract_pr_coords
# ---------------------------------------------------------------------------


class TestExtractPrCoords:
    def test_url_in_response_dict(self) -> None:
        tool_input = {"owner": "tvna", "repo": "claude-md"}
        response = {"url": "https://github.com/tvna/claude-md/pull/123"}
        owner, repo, number = fix.extract_pr_coords(tool_input, response)
        assert (owner, repo, number) == ("tvna", "claude-md", "123")

    def test_url_in_response_string(self) -> None:
        tool_input: dict[str, str] = {}
        response = "created https://github.com/tvna/claude-md/pull/456"
        owner, repo, number = fix.extract_pr_coords(tool_input, response)
        assert (owner, repo, number) == ("tvna", "claude-md", "456")

    def test_number_field_with_input_owner_repo(self) -> None:
        tool_input = {"owner": "tvna", "repo": "claude-md"}
        response = {"number": 789}
        owner, repo, number = fix.extract_pr_coords(tool_input, response)
        assert (owner, repo, number) == ("tvna", "claude-md", "789")

    def test_string_number_field(self) -> None:
        tool_input = {"owner": "tvna", "repo": "claude-md"}
        response = {"pr_number": "42"}
        owner, repo, number = fix.extract_pr_coords(tool_input, response)
        assert (owner, repo, number) == ("tvna", "claude-md", "42")

    def test_prefers_url_over_number(self) -> None:
        tool_input = {"owner": "tvna", "repo": "claude-md"}
        response = {
            "url": "https://github.com/tvna/claude-md/pull/100",
            "number": 200,
        }
        owner, repo, number = fix.extract_pr_coords(tool_input, response)
        assert number == "100"

    def test_missing_all_returns_none_triple(self) -> None:
        owner, repo, number = fix.extract_pr_coords({}, None)
        assert number is None

    def test_response_none_falls_through(self) -> None:
        _, _, number = fix.extract_pr_coords({"owner": "o", "repo": "r"}, None)
        assert number is None


# ---------------------------------------------------------------------------
# decide
# ---------------------------------------------------------------------------


class TestDecide:
    def test_ignores_non_target_tool(self) -> None:
        event = {
            "tool_name": "mcp__github__update_pull_request",
            "tool_input": {"body": "hello & world"},
            "tool_response": {"number": 1},
        }
        assert fix.decide(event) is None

    def test_ignores_unrelated_tool(self) -> None:
        assert fix.decide({"tool_name": "Bash"}) is None

    def test_emits_mandatory_fix_instruction(self) -> None:
        event = {
            "tool_name": fix.TARGET_TOOL,
            "tool_input": {
                "owner": "tvna",
                "repo": "claude-md",
                "body": "## Summary\nfoo & bar\n\nhttps://session_url",
            },
            "tool_response": {"url": "https://github.com/tvna/claude-md/pull/99"},
        }
        output = fix.decide(event)
        assert output is not None
        hook = output["hookSpecificOutput"]
        assert hook["hookEventName"] == "PostToolUse"
        ctx = hook["additionalContext"]
        assert "MANDATORY BODY FIX" in ctx
        assert "tvna/claude-md#99" in ctx
        assert "foo & bar" in ctx
        assert "--- AUTHORED BODY (verbatim) ---" in ctx
        assert "--- END BODY ---" in ctx

    def test_body_contains_literal_ampersand(self) -> None:
        event = {
            "tool_name": fix.TARGET_TOOL,
            "tool_input": {
                "owner": "o",
                "repo": "r",
                "body": "## Risk & blast radius\ndetails",
            },
            "tool_response": {"number": 55},
        }
        output = fix.decide(event)
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "Risk & blast radius" in ctx

    def test_missing_body_emits_fallback(self) -> None:
        event = {
            "tool_name": fix.TARGET_TOOL,
            "tool_input": {"owner": "tvna", "repo": "claude-md"},
            "tool_response": {"number": 7},
        }
        output = fix.decide(event)
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "MANDATORY BODY FIX" not in ctx
        assert "skipped" in ctx

    def test_empty_body_emits_fallback(self) -> None:
        event = {
            "tool_name": fix.TARGET_TOOL,
            "tool_input": {"body": "   "},
            "tool_response": {"number": 7},
        }
        output = fix.decide(event)
        assert output is not None
        assert "skipped" in output["hookSpecificOutput"]["additionalContext"]

    def test_missing_pr_number_emits_fallback(self) -> None:
        event = {
            "tool_name": fix.TARGET_TOOL,
            "tool_input": {"body": "some body & content"},
            "tool_response": {},
        }
        output = fix.decide(event)
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "skipped" in ctx
        assert "MANDATORY BODY FIX" not in ctx

    def test_truncates_long_body(self) -> None:
        long_body = "x" * (fix._MAX_BODY_PREVIEW + 500)
        event = {
            "tool_name": fix.TARGET_TOOL,
            "tool_input": {"owner": "o", "repo": "r", "body": long_body},
            "tool_response": {"number": 1},
        }
        output = fix.decide(event)
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "truncated" in ctx
        assert len(ctx) < len(long_body) + 500

    def test_pr_label_without_owner_repo(self) -> None:
        event = {
            "tool_name": fix.TARGET_TOOL,
            "tool_input": {"body": "body content"},
            "tool_response": {"number": 12},
        }
        output = fix.decide(event)
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "PR #12" in ctx

    def test_output_is_valid_json(self) -> None:
        event = {
            "tool_name": fix.TARGET_TOOL,
            "tool_input": {"owner": "tvna", "repo": "claude-md", "body": "body & text"},
            "tool_response": {"number": 5},
        }
        output = fix.decide(event)
        assert output is not None
        assert json.loads(json.dumps(output)) == output


# ---------------------------------------------------------------------------
# main (stdin/stdout boundary)
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_writes_json_to_stdout(self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
        event = {
            "tool_name": fix.TARGET_TOOL,
            "tool_input": {"owner": "tvna", "repo": "claude-md", "body": "body & text"},
            "tool_response": {"number": 3},
        }
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
        rc = fix.main()
        assert rc == 0
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert "hookSpecificOutput" in parsed

    def test_main_empty_stdin_exits_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert fix.main() == 0

    def test_main_malformed_json_exits_zero(self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))
        rc = fix.main()
        assert rc == 0
        captured = capsys.readouterr()
        assert "::error::" in captured.err

    def test_main_non_target_tool_no_stdout(self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
        event = {"tool_name": "mcp__github__merge_pull_request"}
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
        rc = fix.main()
        assert rc == 0
        assert capsys.readouterr().out == ""
