"""Tests for scripts/post_merge_retro_append.py.

Verifies that the PostToolUse hook correctly detects a merge event,
emits the right additionalContext for the append path (auto-retro found)
and the fallback/create path (no auto-retro), and stays silent for
non-merge tools or malformed input. Refs issue #916.
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
    def test_pr_number_from_tool_input_int(self) -> None:
        tool_input = {"owner": "tvna", "repo": "claude-md", "pullRequestNumber": 916}
        owner, repo, number = hook.extract_merge_coords(tool_input, None)
        assert (owner, repo, number) == ("tvna", "claude-md", "916")

    def test_pr_number_from_tool_input_str(self) -> None:
        tool_input = {"owner": "tvna", "repo": "claude-md", "pullRequestNumber": "916"}
        owner, repo, number = hook.extract_merge_coords(tool_input, None)
        assert number == "916"

    def test_pr_number_from_response_url(self) -> None:
        tool_input: dict[str, object] = {}
        response = {"url": "https://github.com/tvna/claude-md/pull/916"}
        owner, repo, number = hook.extract_merge_coords(tool_input, response)
        assert (owner, repo, number) == ("tvna", "claude-md", "916")

    def test_tool_input_owner_repo_preferred_over_url(self) -> None:
        tool_input = {"owner": "tvna", "repo": "claude-md", "pullRequestNumber": 100}
        response = {"url": "https://github.com/other/repo/pull/999"}
        owner, repo, number = hook.extract_merge_coords(tool_input, response)
        assert (owner, repo, number) == ("tvna", "claude-md", "100")

    def test_missing_all_returns_none_triple(self) -> None:
        owner, repo, number = hook.extract_merge_coords({}, None)
        assert (owner, repo, number) == (None, None, None)

    def test_non_decimal_pr_number_string_ignored(self) -> None:
        tool_input = {"owner": "tvna", "repo": "claude-md", "pullRequestNumber": "abc"}
        _, _, number = hook.extract_merge_coords(tool_input, None)
        assert number is None

    def test_zero_pr_number_ignored(self) -> None:
        tool_input = {"pullRequestNumber": 0}
        _, _, number = hook.extract_merge_coords(tool_input, None)
        assert number is None

    def test_response_string_url(self) -> None:
        tool_input: dict[str, object] = {}
        response = "merged https://github.com/tvna/claude-md/pull/42"
        _, _, number = hook.extract_merge_coords(tool_input, response)
        assert number == "42"


# ---------------------------------------------------------------------------
# decide — non-merge tool: silent
# ---------------------------------------------------------------------------


class TestDecideNonMergeTool:
    def test_ignores_create_pull_request(self) -> None:
        event = {"tool_name": "mcp__github__create_pull_request"}
        assert hook.decide(event) is None

    def test_ignores_bash(self) -> None:
        assert hook.decide({"tool_name": "Bash"}) is None

    def test_ignores_unrelated_mcp_tool(self) -> None:
        assert hook.decide({"tool_name": "mcp__github__add_issue_comment"}) is None


# ---------------------------------------------------------------------------
# decide — merge event with auto-retro found (append path)
# ---------------------------------------------------------------------------


class TestDecideAppendPath:
    def _merge_event(self, pr_number: int = 916) -> dict[str, object]:
        return {
            "tool_name": hook.TARGET_TOOL,
            "tool_input": {
                "owner": "tvna",
                "repo": "claude-md",
                "pullRequestNumber": pr_number,
            },
            "tool_response": {"merged": True},
        }

    def test_returns_hook_specific_output(self) -> None:
        output = hook.decide(self._merge_event())
        assert output is not None
        assert "hookSpecificOutput" in output

    def test_hook_event_name_is_post_tool_use(self) -> None:
        output = hook.decide(self._merge_event())
        assert output is not None
        assert output["hookSpecificOutput"]["hookEventName"] == "PostToolUse"

    def test_contains_dedup_guard_marker(self) -> None:
        output = hook.decide(self._merge_event())
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "AUTO-RETRO DEDUP GUARD" in ctx

    def test_contains_do_not_create_instruction(self) -> None:
        output = hook.decide(self._merge_event())
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "NOT" in ctx
        assert "new retro" in ctx.lower() or "retrospective" in ctx.lower()

    def test_contains_retro_title_prefix(self) -> None:
        output = hook.decide(self._merge_event())
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert hook.RETRO_TITLE_PREFIX in ctx

    def test_contains_pr_number(self) -> None:
        output = hook.decide(self._merge_event(pr_number=916))
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "916" in ctx

    def test_does_not_instruct_comment_append(self) -> None:
        # Phase 1 of #1386: the hook no longer tells the agent to append a
        # repair-analysis comment. It must not name the comment tool and must
        # explicitly forbid posting a separate comment.
        output = hook.decide(self._merge_event())
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "mcp__github__add_issue_comment" not in ctx
        assert "do NOT post a separate" in ctx

    def test_contains_owner_and_repo(self) -> None:
        output = hook.decide(self._merge_event())
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "tvna" in ctx
        assert "claude-md" in ctx

    def test_output_is_valid_json(self) -> None:
        output = hook.decide(self._merge_event())
        assert output is not None
        assert json.loads(json.dumps(output)) == output


# ---------------------------------------------------------------------------
# decide — merge event with no auto-retro (create fallback path)
# ---------------------------------------------------------------------------


class TestDecideCreateFallbackPath:
    def test_fallback_instruction_present(self) -> None:
        event = {
            "tool_name": hook.TARGET_TOOL,
            "tool_input": {
                "owner": "tvna",
                "repo": "claude-md",
                "pullRequestNumber": 916,
            },
            "tool_response": {"merged": True},
        }
        output = hook.decide(event)
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "fallback" in ctx.lower() or "Fallback" in ctx

    def test_forbidden_action_mentioned(self) -> None:
        event = {
            "tool_name": hook.TARGET_TOOL,
            "tool_input": {"pullRequestNumber": 916},
            "tool_response": None,
        }
        output = hook.decide(event)
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "orbidden" in ctx or " forbidden" in ctx.lower()


# ---------------------------------------------------------------------------
# decide — PR number missing
# ---------------------------------------------------------------------------


class TestDecideMissingPrNumber:
    def test_emits_fallback_context_when_no_number(self) -> None:
        event = {
            "tool_name": hook.TARGET_TOOL,
            "tool_input": {"owner": "tvna", "repo": "claude-md"},
            "tool_response": {},
        }
        output = hook.decide(event)
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "AUTO-RETRO DEDUP GUARD" in ctx
        assert hook.RETRO_TITLE_PREFIX in ctx

    def test_emits_context_with_none_tool_input(self) -> None:
        event = {"tool_name": hook.TARGET_TOOL, "tool_input": None, "tool_response": None}
        output = hook.decide(event)
        assert output is not None
        assert "hookSpecificOutput" in output


# ---------------------------------------------------------------------------
# main (stdin/stdout boundary)
# ---------------------------------------------------------------------------


class TestMain:
    def test_main_writes_json_to_stdout(
        self, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        event = {
            "tool_name": hook.TARGET_TOOL,
            "tool_input": {"owner": "tvna", "repo": "claude-md", "pullRequestNumber": 916},
            "tool_response": {"merged": True},
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

    def test_main_non_dict_input_exits_zero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([1, 2, 3])))
        assert hook.main() == 0
