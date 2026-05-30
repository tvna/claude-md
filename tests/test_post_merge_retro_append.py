"""Tests for scripts/post_merge_retro_append.py.

Verifies that the PostToolUse hook correctly detects merge events and emits
the mandatory retro-append additionalContext. Refs issue #916.
"""

from __future__ import annotations

import io
import json

import post_merge_retro_append as hook
import pytest

pytestmark = pytest.mark.shard_preflight


# ---------------------------------------------------------------------------
# extract_merge_coords
# ---------------------------------------------------------------------------


class TestExtractMergeCoords:
    def test_url_in_response(self) -> None:
        tool_input = {"owner": "tvna", "repo": "claude-md", "pullRequestNumber": 908}
        response = {"url": "https://github.com/tvna/claude-md/pull/908"}
        owner, repo, number = hook.extract_merge_coords(tool_input, response)
        assert (owner, repo, number) == ("tvna", "claude-md", "908")

    def test_pr_number_from_tool_input(self) -> None:
        tool_input = {"owner": "tvna", "repo": "claude-md", "pullRequestNumber": 42}
        owner, repo, number = hook.extract_merge_coords(tool_input, {})
        assert (owner, repo, number) == ("tvna", "claude-md", "42")

    def test_pr_number_string_from_tool_input(self) -> None:
        tool_input = {"owner": "tvna", "repo": "claude-md", "pull_request_number": "99"}
        owner, repo, number = hook.extract_merge_coords(tool_input, {})
        assert (owner, repo, number) == ("tvna", "claude-md", "99")

    def test_pr_number_from_response_dict(self) -> None:
        tool_input = {"owner": "tvna", "repo": "claude-md"}
        response = {"number": 123}
        owner, repo, number = hook.extract_merge_coords(tool_input, response)
        assert (owner, repo, number) == ("tvna", "claude-md", "123")

    def test_prefers_url_over_number_in_response(self) -> None:
        tool_input = {"owner": "tvna", "repo": "claude-md", "pullRequestNumber": 999}
        response = {"url": "https://github.com/tvna/claude-md/pull/100", "number": 999}
        owner, repo, number = hook.extract_merge_coords(tool_input, response)
        assert number == "100"

    def test_missing_all_returns_none(self) -> None:
        owner, repo, number = hook.extract_merge_coords({}, None)
        assert number is None

    def test_response_none_fallback_to_input(self) -> None:
        tool_input = {"owner": "tvna", "repo": "claude-md", "pullRequestNumber": 7}
        _, _, number = hook.extract_merge_coords(tool_input, None)
        assert number == "7"


# ---------------------------------------------------------------------------
# decide — non-merge tool
# ---------------------------------------------------------------------------


class TestDecideIgnoresOtherTools:
    def test_ignores_create_pull_request(self) -> None:
        event = {
            "tool_name": "mcp__github__create_pull_request",
            "tool_input": {"owner": "tvna", "repo": "claude-md"},
            "tool_response": {"number": 1},
        }
        assert hook.decide(event) is None

    def test_ignores_bash(self) -> None:
        assert hook.decide({"tool_name": "Bash"}) is None

    def test_ignores_issue_write(self) -> None:
        assert hook.decide({"tool_name": "mcp__github__issue_write"}) is None


# ---------------------------------------------------------------------------
# decide — auto-retro found (append path)
# ---------------------------------------------------------------------------


class TestDecideAppendPath:
    """Merge event where auto-retro is expected to exist (normal CI path)."""

    def _make_merge_event(self, pr_number: int = 908) -> dict:
        return {
            "tool_name": hook.TARGET_TOOL,
            "tool_input": {
                "owner": "tvna",
                "repo": "claude-md",
                "pullRequestNumber": pr_number,
            },
            "tool_response": {
                "url": f"https://github.com/tvna/claude-md/pull/{pr_number}"
            },
        }

    def test_emits_mandatory_retro_append(self) -> None:
        event = self._make_merge_event(908)
        output = hook.decide(event)
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "MANDATORY RETRO APPEND" in ctx

    def test_references_pr_number(self) -> None:
        event = self._make_merge_event(908)
        output = hook.decide(event)
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "PR #908" in ctx

    def test_references_repo(self) -> None:
        event = self._make_merge_event(908)
        output = hook.decide(event)
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "tvna/claude-md" in ctx

    def test_instructs_search_step(self) -> None:
        event = self._make_merge_event(908)
        output = hook.decide(event)
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "STEP 1" in ctx
        assert "fix(auto-retro)" in ctx

    def test_instructs_comment_step(self) -> None:
        event = self._make_merge_event(908)
        output = hook.decide(event)
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "STEP 2" in ctx
        assert "mcp__github__add_issue_comment" in ctx

    def test_includes_fallback_instruction(self) -> None:
        event = self._make_merge_event(908)
        output = hook.decide(event)
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "FALLBACK" in ctx

    def test_forbids_duplicate_retro(self) -> None:
        event = self._make_merge_event(908)
        output = hook.decide(event)
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "FORBIDDEN" in ctx

    def test_hook_event_name_is_post_tool_use(self) -> None:
        event = self._make_merge_event(908)
        output = hook.decide(event)
        assert output is not None
        assert output["hookSpecificOutput"]["hookEventName"] == "PostToolUse"

    def test_output_is_valid_json(self) -> None:
        event = self._make_merge_event(908)
        output = hook.decide(event)
        assert output is not None
        assert json.loads(json.dumps(output)) == output


# ---------------------------------------------------------------------------
# decide — no auto-retro / fallback create path
# ---------------------------------------------------------------------------


class TestDecideCreateFallbackPath:
    """Merge event where PR number is not extractable (fallback create path)."""

    def test_missing_pr_number_emits_fallback_context(self) -> None:
        event = {
            "tool_name": hook.TARGET_TOOL,
            "tool_input": {"owner": "tvna", "repo": "claude-md"},
            "tool_response": {},
        }
        output = hook.decide(event)
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "RETRO APPEND" in ctx
        assert "could not be extracted" in ctx

    def test_fallback_still_forbids_duplicate(self) -> None:
        event = {
            "tool_name": hook.TARGET_TOOL,
            "tool_input": {},
            "tool_response": {},
        }
        output = hook.decide(event)
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "Do NOT create a new retro issue if one already exists" in ctx


# ---------------------------------------------------------------------------
# main (stdin/stdout boundary)
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_writes_json_to_stdout(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        event = {
            "tool_name": hook.TARGET_TOOL,
            "tool_input": {
                "owner": "tvna",
                "repo": "claude-md",
                "pullRequestNumber": 908,
            },
            "tool_response": {"number": 908},
        }
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
        rc = hook.main()
        assert rc == 0
        captured = capsys.readouterr()
        parsed = json.loads(captured.out)
        assert "hookSpecificOutput" in parsed

    def test_main_empty_stdin_exits_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert hook.main() == 0

    def test_main_malformed_json_exits_zero(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))
        rc = hook.main()
        assert rc == 0
        captured = capsys.readouterr()
        assert "::error::" in captured.err

    def test_main_non_merge_tool_no_stdout(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        event = {"tool_name": "mcp__github__create_pull_request"}
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
        rc = hook.main()
        assert rc == 0
        assert capsys.readouterr().out == ""

    def test_main_non_dict_event_exits_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("[1, 2, 3]"))
        assert hook.main() == 0
