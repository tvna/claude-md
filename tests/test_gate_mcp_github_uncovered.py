"""Tests for ``scripts/gate_mcp_github_uncovered.py``.

Verifies that:
- Tools in HOOK_COVERED_TOOLS pass through (no deny decision).
- Unknown mcp__github__* tools are denied with a gh-CLI redirect message.
- Non-mcp__github__ tools are ignored.
- The covered set matches what .claude/settings.json actually gates.
- The stdin/stdout boundary works end-to-end.
"""

from __future__ import annotations

import io
import json
import re
from pathlib import Path

import gate_mcp_github_uncovered as gmu
import pytest

pytestmark = pytest.mark.shard_preflight

ROOT = Path(__file__).resolve().parents[1]
CLAUDE_SETTINGS = ROOT / ".claude" / "settings.json"

# ---------------------------------------------------------------------------
# decide()
# ---------------------------------------------------------------------------


class TestDecide:
    @pytest.mark.parametrize(
        "tool_name",
        sorted(gmu.HOOK_COVERED_TOOLS),
    )
    def test_covered_tools_pass_through(self, tool_name: str) -> None:
        assert gmu.decide(tool_name) is None

    @pytest.mark.parametrize(
        "tool_name",
        [
            "mcp__github__list_issues",
            "mcp__github__pull_request_read",
            "mcp__github__search_issues",
            "mcp__github__list_commits",
            "mcp__github__get_file_contents",
            "mcp__github__merge_pull_request",
            "mcp__github__list_pull_requests",
        ],
    )
    def test_uncovered_tools_are_denied(self, tool_name: str) -> None:
        decision = gmu.decide(tool_name)
        assert decision is not None
        assert decision["permissionDecision"] == "deny"
        assert "scripts/github_api.py" in decision["decisionReason"]
        assert "PreToolUse" in decision["decisionReason"]

    @pytest.mark.parametrize(
        "tool_name",
        [
            "Bash",
            "Read",
            "Edit",
            "mcp__codex_apps__github._create_issue",
            "some_other_tool",
        ],
    )
    def test_non_mcp_github_tools_pass_through(self, tool_name: str) -> None:
        assert gmu.decide(tool_name) is None

    def test_deny_message_contains_tool_short_name(self) -> None:
        decision = gmu.decide("mcp__github__list_issues")
        assert decision is not None
        assert "list_issues" in decision["decisionReason"]


# ---------------------------------------------------------------------------
# Consistency: HOOK_COVERED_TOOLS vs .claude/settings.json
# ---------------------------------------------------------------------------


class TestCoveredSetMatchesSettings:
    """The covered set must match what settings.json actually gates."""

    def _extract_mcp_github_tools_from_matchers(self) -> set[str]:
        """Return the set of mcp__github__ tool names extracted from
        PreToolUse matchers in settings.json (excluding the catch-all).

        Handles both single-tool matchers (``mcp__github__issue_write``)
        and alternation groups
        (``mcp__github__(issue_write|create_pull_request)``).
        """
        data = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
        hooks = data.get("hooks", {})
        pre = hooks.get("PreToolUse", [])
        tools: set[str] = set()
        # Matches: mcp__github__word  OR  mcp__github__(word|word|...)
        _single = re.compile(r"mcp__github__(\w+)")
        _group = re.compile(r"mcp__github__\(([^)]+)\)")
        for group in pre:
            if not isinstance(group, dict):
                continue
            matcher = group.get("matcher", "")
            if not isinstance(matcher, str) or "mcp__github__" not in matcher:
                continue
            for m in _group.finditer(matcher):
                for alt in m.group(1).split("|"):
                    alt = alt.strip()
                    if re.fullmatch(r"\w+", alt):
                        tools.add(f"mcp__github__{alt}")
            for m in _single.finditer(matcher):
                # skip if the character after the match is '(' or '|'
                # (already covered by _group above)
                end = m.end()
                if end < len(matcher) and matcher[end] in "(|":
                    continue
                tools.add(f"mcp__github__{m.group(1)}")
        return tools

    def test_covered_set_matches_settings(self) -> None:
        settings_tools = self._extract_mcp_github_tools_from_matchers()
        # Every tool in HOOK_COVERED_TOOLS must appear in settings.json
        missing_from_settings = gmu.HOOK_COVERED_TOOLS - settings_tools
        assert not missing_from_settings, (
            f"HOOK_COVERED_TOOLS contains tools not gated in settings.json: "
            f"{missing_from_settings}. Remove them from HOOK_COVERED_TOOLS or "
            f"add dedicated PreToolUse hooks in .claude/settings.json."
        )


# ---------------------------------------------------------------------------
# main() stdin/stdout boundary
# ---------------------------------------------------------------------------


class TestMain:
    def _run(self, payload: object, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        gmu.main()
        return stdout_buf.getvalue(), stderr_buf.getvalue()

    def test_covered_tool_produces_no_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout, _ = self._run(
            {"tool_name": "mcp__github__create_pull_request", "tool_input": {}},
            monkeypatch,
        )
        assert stdout == ""

    def test_uncovered_tool_produces_deny(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout, _ = self._run(
            {"tool_name": "mcp__github__list_issues", "tool_input": {}},
            monkeypatch,
        )
        decision = json.loads(stdout)
        assert decision["permissionDecision"] == "deny"

    def test_empty_stdin_is_handled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        rc = gmu.main()
        assert rc == 0
        assert stdout_buf.getvalue() == ""

    def test_malformed_json_fails_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        rc = gmu.main()
        assert rc == 0
        assert stdout_buf.getvalue() == ""
        assert "malformed" in stderr_buf.getvalue()

    def test_missing_tool_name_fails_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout, stderr = self._run({"tool_input": {}}, monkeypatch)
        assert stdout == ""
        assert "tool_name" in stderr
