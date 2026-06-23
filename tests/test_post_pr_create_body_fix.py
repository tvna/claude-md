"""Tests for scripts/post_pr_create_body_fix.py.

Verifies that the PostToolUse hook correctly detects the create_pull_request
body-corruption defects (& → &amp; encoding; duplicate footer) and emits
the right additionalContext instruction. Refs issue #892.
"""

from __future__ import annotations

import io
import json
from typing import Any

import post_pr_create_body_fix as fix
import pytest

pytestmark = pytest.mark.shard_preflight


@pytest.fixture(autouse=True)
def _local_cli_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default every test to the local-CLI environment (Refs #1441).

    ``decide`` reads ``os.environ`` to reconstruct the web-harness session
    footer. The test process may itself run under the remote harness
    (``CLAUDE_CODE_REMOTE=true``), which would leak a constructed footer into
    tests that assert its absence. Clearing both vars makes the default
    behavior deterministic; harness tests opt in with ``monkeypatch.setenv``.
    """
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    monkeypatch.delenv("CLAUDE_CODE_REMOTE_SESSION_ID", raising=False)


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
        assert "--- NORMALIZED BODY ---" in ctx
        assert "--- END BODY ---" in ctx

    def test_decodes_html_entities_in_normalized_body(self) -> None:
        event = {
            "tool_name": fix.TARGET_TOOL,
            "tool_input": {
                "owner": "tvna",
                "repo": "claude-md",
                "body": "## Scope\nuse &#34;quotes&#34; and a &gt; sign &amp; more",
            },
            "tool_response": {"url": "https://github.com/tvna/claude-md/pull/1"},
        }
        output = fix.decide(event)
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert 'use "quotes" and a > sign & more' in ctx
        assert "&#34;" not in ctx.split("--- NORMALIZED BODY ---", 1)[1]

    def test_collapses_duplicate_footer(self) -> None:
        footer = "_Generated by [Claude Code](https://claude.ai/code)_"
        event = {
            "tool_name": fix.TARGET_TOOL,
            "tool_input": {
                "owner": "o",
                "repo": "r",
                "body": f"## Scope\nbody text\n\n{footer}\n\n{footer}",
            },
            "tool_response": {"number": 2},
        }
        output = fix.decide(event)
        assert output is not None
        normalized = output["hookSpecificOutput"]["additionalContext"].split(
            "--- NORMALIZED BODY ---", 1
        )[1]
        assert normalized.count(footer) == 1

    def test_warns_about_dropped_angle_tokens(self) -> None:
        event = {
            "tool_name": fix.TARGET_TOOL,
            "tool_input": {
                "owner": "o",
                "repo": "r",
                "body": "## Rollback\nrun `git revert <sha>` to undo",
            },
            "tool_response": {
                "url": "https://github.com/o/r/pull/3",
                "body": "## Rollback\nrun `git revert ` to undo",
            },
        }
        output = fix.decide(event)
        assert output is not None
        ctx = output["hookSpecificOutput"]["additionalContext"]
        assert "WARNING" in ctx
        assert "<sha>" in ctx

    def test_no_dropped_token_warning_when_tokens_survive(self) -> None:
        body = "## Rollback\nrun `git revert <sha>` to undo"
        event = {
            "tool_name": fix.TARGET_TOOL,
            "tool_input": {"owner": "o", "repo": "r", "body": body},
            "tool_response": {
                "url": "https://github.com/o/r/pull/4",
                "body": body,
            },
        }
        output = fix.decide(event)
        assert output is not None
        assert "WARNING" not in output["hookSpecificOutput"]["additionalContext"]

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
# Footer carry-forward (Refs #1427)
# ---------------------------------------------------------------------------


def _normalized_section(output: dict[str, Any]) -> str:
    return output["hookSpecificOutput"]["additionalContext"].split(
        "--- NORMALIZED BODY ---", 1
    )[1]


_FOOTER = "_Generated by [Claude Code](https://claude.ai/code)_"


class TestHasTrailingAgentFooter:
    def test_true_when_last_line_is_footer(self) -> None:
        assert fix.has_trailing_agent_footer(f"## Scope\ntext\n\n{_FOOTER}") is True

    def test_true_ignores_trailing_whitespace(self) -> None:
        assert fix.has_trailing_agent_footer(f"text\n\n{_FOOTER}\n\n   \n") is True

    def test_false_when_no_footer(self) -> None:
        assert fix.has_trailing_agent_footer("## Scope\njust text") is False

    def test_false_when_footer_not_last(self) -> None:
        assert fix.has_trailing_agent_footer(f"{_FOOTER}\n\nmore after") is False

    def test_false_on_empty(self) -> None:
        assert fix.has_trailing_agent_footer("") is False


class TestExtractTrailingAgentFooter:
    def test_returns_footer_line(self) -> None:
        assert fix.extract_trailing_agent_footer(f"text\n\n{_FOOTER}") == _FOOTER

    def test_returns_last_when_multiple(self) -> None:
        other = "_Generated by [Codex](https://openai.com/codex)_"
        body = f"## Scope\n{other}\n\n{_FOOTER}"
        assert fix.extract_trailing_agent_footer(body) == _FOOTER

    def test_unescapes_html_entities(self) -> None:
        footer = "_Generated by [Claude Code](https://claude.ai/code?a=1&amp;b=2)_"
        assert (
            fix.extract_trailing_agent_footer(footer)
            == "_Generated by [Claude Code](https://claude.ai/code?a=1&b=2)_"
        )

    def test_none_when_absent(self) -> None:
        assert fix.extract_trailing_agent_footer("## Scope\ntext") is None


class TestFooterCarryForward:
    def test_carries_harness_footer_from_stored_body(self) -> None:
        # Secondary source (Refs #1441): not under the web harness, but the
        # create response did echo a stored body carrying a footer. With no
        # session id to reconstruct from, the fixer falls back to lifting the
        # footer out of the stored body so the mandated update is not denied.
        footer = "_Generated by [Claude Code](https://claude.ai/code/session_abc)_"
        event = {
            "tool_name": fix.TARGET_TOOL,
            "tool_input": {
                "owner": "tvna",
                "repo": "claude-md",
                "body": "## Summary\nfoo bar",
            },
            "tool_response": {
                "url": "https://github.com/tvna/claude-md/pull/77",
                "body": f"## Summary\nfoo bar\n\n{footer}",
            },
        }
        output = fix.decide(event)
        assert output is not None
        normalized = _normalized_section(output)
        assert footer in normalized
        assert normalized.count(footer) == 1

    def test_no_duplicate_when_authored_already_has_footer(self) -> None:
        # Local-CLI create: authored body already carries the footer, and so
        # does the stored body. Carry-forward must not duplicate it.
        footer = "_Generated by [Claude Code](https://claude.ai/code)_"
        body = f"## Summary\nfoo\n\n{footer}"
        event = {
            "tool_name": fix.TARGET_TOOL,
            "tool_input": {"owner": "o", "repo": "r", "body": body},
            "tool_response": {
                "url": "https://github.com/o/r/pull/1",
                "body": body,
            },
        }
        output = fix.decide(event)
        assert output is not None
        assert _normalized_section(output).count(footer) == 1

    def test_no_carry_when_stored_has_no_footer(self) -> None:
        # Neither side has a footer (e.g. local CLI mid-edit): nothing to
        # carry, and the fixer must not invent one.
        event = {
            "tool_name": fix.TARGET_TOOL,
            "tool_input": {"owner": "o", "repo": "r", "body": "## Summary\nfoo"},
            "tool_response": {
                "url": "https://github.com/o/r/pull/2",
                "body": "## Summary\nfoo",
            },
        }
        output = fix.decide(event)
        assert output is not None
        assert "_Generated by" not in _normalized_section(output)

    def test_no_carry_when_stored_body_absent(self) -> None:
        # tool_response carries no body field at all: carry-forward is a
        # no-op and must not raise.
        event = {
            "tool_name": fix.TARGET_TOOL,
            "tool_input": {"owner": "o", "repo": "r", "body": "## Summary\nfoo"},
            "tool_response": {"number": 9},
        }
        output = fix.decide(event)
        assert output is not None
        assert "_Generated by" not in _normalized_section(output)


# ---------------------------------------------------------------------------
# Harness session footer reconstruction (Refs #1441)
# ---------------------------------------------------------------------------


class TestBuildHarnessSessionFooter:
    def test_constructs_from_cse_prefixed_session_id(self) -> None:
        env = {
            "CLAUDE_CODE_REMOTE": "true",
            "CLAUDE_CODE_REMOTE_SESSION_ID": "cse_01ABCdef",
        }
        assert fix.build_harness_session_footer(env) == (
            "_Generated by [Claude Code](https://claude.ai/code/session_01ABCdef)_"
        )

    def test_session_id_without_cse_prefix_used_verbatim(self) -> None:
        env = {
            "CLAUDE_CODE_REMOTE": "true",
            "CLAUDE_CODE_REMOTE_SESSION_ID": "01ABCdef",
        }
        assert fix.build_harness_session_footer(env) == (
            "_Generated by [Claude Code](https://claude.ai/code/session_01ABCdef)_"
        )

    def test_none_when_not_remote(self) -> None:
        # Local CLI: CLAUDE_CODE_REMOTE unset -> never fabricate a footer.
        env = {"CLAUDE_CODE_REMOTE_SESSION_ID": "cse_01ABCdef"}
        assert fix.build_harness_session_footer(env) is None

    def test_none_when_remote_flag_not_true(self) -> None:
        env = {
            "CLAUDE_CODE_REMOTE": "false",
            "CLAUDE_CODE_REMOTE_SESSION_ID": "cse_01ABCdef",
        }
        assert fix.build_harness_session_footer(env) is None

    def test_none_when_session_id_missing(self) -> None:
        # Under the harness but no session id -> no malformed .../session_ URL.
        assert fix.build_harness_session_footer({"CLAUDE_CODE_REMOTE": "true"}) is None

    def test_none_when_session_id_only_prefix(self) -> None:
        env = {
            "CLAUDE_CODE_REMOTE": "true",
            "CLAUDE_CODE_REMOTE_SESSION_ID": "cse_",
        }
        assert fix.build_harness_session_footer(env) is None

    def test_none_when_token_breaks_footer_regex(self) -> None:
        # Anti-drift guard: a token that would yield a line the gate's own
        # regex rejects (e.g. an embedded space breaks the URL) returns None
        # rather than a footer that body_policy would deny.
        env = {
            "CLAUDE_CODE_REMOTE": "true",
            "CLAUDE_CODE_REMOTE_SESSION_ID": "cse_ab cd",
        }
        assert fix.build_harness_session_footer(env) is None


class TestDecideReconstructsHarnessFooter:
    def test_reconstructs_footer_when_create_response_omits_body(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Refs #1441 / #1439: the web-harness create response is {id, url}
        # only; no body to lift. The fixer must reconstruct the session
        # footer from the env so the mandated update carries exactly one.
        monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
        monkeypatch.setenv("CLAUDE_CODE_REMOTE_SESSION_ID", "cse_01XYZ")
        event = {
            "tool_name": fix.TARGET_TOOL,
            "tool_input": {
                "owner": "tvna",
                "repo": "claude-md",
                "body": "## Summary\nfoo bar",
            },
            # Reproduces the {id, url}-only shape observed on #1439: no body.
            "tool_response": {
                "id": 42,
                "url": "https://github.com/tvna/claude-md/pull/88",
            },
        }
        output = fix.decide(event)
        assert output is not None
        normalized = _normalized_section(output)
        expected = (
            "_Generated by [Claude Code](https://claude.ai/code/session_01XYZ)_"
        )
        assert expected in normalized
        assert normalized.count("_Generated by") == 1

    def test_no_double_footer_when_already_present_under_harness(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
        monkeypatch.setenv("CLAUDE_CODE_REMOTE_SESSION_ID", "cse_01XYZ")
        footer = "_Generated by [Claude Code](https://claude.ai/code/session_01XYZ)_"
        event = {
            "tool_name": fix.TARGET_TOOL,
            "tool_input": {
                "owner": "o",
                "repo": "r",
                "body": f"## Summary\nfoo\n\n{footer}",
            },
            "tool_response": {"id": 1, "url": "https://github.com/o/r/pull/1"},
        }
        output = fix.decide(event)
        assert output is not None
        assert _normalized_section(output).count(footer) == 1

    def test_local_cli_does_not_fabricate_footer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Refs #1441 acceptance: no CLAUDE_CODE_REMOTE and a body-less create
        # response -> the fixer must not invent a footer.
        monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
        monkeypatch.setenv("CLAUDE_CODE_REMOTE_SESSION_ID", "cse_01XYZ")
        event = {
            "tool_name": fix.TARGET_TOOL,
            "tool_input": {"owner": "o", "repo": "r", "body": "## Summary\nfoo"},
            "tool_response": {"id": 1, "url": "https://github.com/o/r/pull/2"},
        }
        output = fix.decide(event)
        assert output is not None
        assert "_Generated by" not in _normalized_section(output)


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
