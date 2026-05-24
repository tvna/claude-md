"""Tests for ``scripts/preflight_pr_title_issue_ref.py`` (Layer 2.5 hook).

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.

Mirrors the table-driven style of ``tests/test_preflight_non_ascii.py``.
Pure functions get parametrize cases; the stdin/stdout boundary in
:func:`preflight_pr_title_issue_ref.main` is exercised with
``monkeypatch`` over ``sys.stdin`` and ``capsys`` over
``sys.stdout``/``sys.stderr``.

Refs #292; builds on #167 / #214 (server-side title rule) and #146
(Layer 2.5 precedent).
"""

from __future__ import annotations

import io
import json

import preflight_pr_title_issue_ref as preflight
import pytest

# ---------------------------------------------------------------------------
# extract_title
# ---------------------------------------------------------------------------


class TestExtractTitle:
    def test_present(self) -> None:
        assert preflight.extract_title({"title": "feat: x"}) == "feat: x"

    def test_missing_key_becomes_empty(self) -> None:
        assert preflight.extract_title({}) == ""

    def test_none_value_becomes_empty(self) -> None:
        assert preflight.extract_title({"title": None}) == ""

    def test_non_string_value_becomes_empty(self) -> None:
        assert preflight.extract_title({"title": 12345}) == ""
        assert preflight.extract_title({"title": ["feat: x"]}) == ""


# ---------------------------------------------------------------------------
# find_issue_refs
# ---------------------------------------------------------------------------


class TestFindIssueRefs:
    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("feat: clean title", []),
            ("feat: x (#1)", ["(#1)"]),
            ("fix(scope): bar (#289)", ["(#289)"]),
            ("chore: a (#1) and b (#22)", ["(#1)", "(#22)"]),
            ("", []),
            # `#NNN` outside parens is NOT a violation per
            # ``title_policy._PR_ISSUE_REF_RE``; this hook must match
            # exactly what the server-side gate enforces.
            ("docs: see #123 for context", []),
            # Empty parens or non-digit content must not match.
            ("feat: x (#)", []),
            ("feat: x (#abc)", []),
            # Leading zeros and very large numbers still match \d+.
            ("feat: x (#007)", ["(#007)"]),
        ],
    )
    def test_table(self, title: str, expected: list[str]) -> None:
        assert preflight.find_issue_refs(title) == expected


# ---------------------------------------------------------------------------
# suggest_fix
# ---------------------------------------------------------------------------


class TestSuggestFix:
    @pytest.mark.parametrize(
        ("title", "expected"),
        [
            ("feat: foo (#1)", "feat: foo"),
            ("feat(scope): bar (#289)", "feat(scope): bar"),
            ("chore: a (#1) and b (#22)", "chore: a and b"),
            # Internal whitespace collapsed but type/scope spacing kept.
            ("fix:   y   (#3)   ", "fix: y"),
            ("clean title", "clean title"),
        ],
    )
    def test_table(self, title: str, expected: str) -> None:
        assert preflight.suggest_fix(title) == expected


# ---------------------------------------------------------------------------
# build_deny_reason
# ---------------------------------------------------------------------------


class TestBuildDenyReason:
    def test_lists_every_offending_token(self) -> None:
        reason = preflight.build_deny_reason(
            "mcp__github__create_pull_request",
            "chore: a (#1) and b (#22)",
            ["(#1)", "(#22)"],
        )
        assert "(#1)" in reason
        assert "(#22)" in reason

    def test_references_server_side_rule(self) -> None:
        reason = preflight.build_deny_reason(
            "mcp__github__create_pull_request",
            "feat: x (#1)",
            ["(#1)"],
        )
        # Cite the server-side authority so the agent gets the same
        # remediation context it would get from a CI failure.
        assert "title_policy.py" in reason
        assert "#167" in reason
        assert "#214" in reason
        assert "verify-issue-link.yml" in reason

    def test_shows_suggested_fix(self) -> None:
        reason = preflight.build_deny_reason(
            "mcp__github__update_pull_request",
            "feat: x (#1)",
            ["(#1)"],
        )
        assert "'feat: x'" in reason

    def test_includes_tool_name(self) -> None:
        reason = preflight.build_deny_reason(
            "mcp__github__update_pull_request",
            "feat: x (#1)",
            ["(#1)"],
        )
        assert "mcp__github__update_pull_request" in reason


# ---------------------------------------------------------------------------
# decide
# ---------------------------------------------------------------------------


class TestDecide:
    def test_clean_title_allows(self) -> None:
        out = preflight.decide(
            "mcp__github__create_pull_request",
            {"title": "feat(harness): add preflight gate", "body": "..."},
        )
        assert out is None

    def test_dirty_title_denies(self) -> None:
        out = preflight.decide(
            "mcp__github__create_pull_request",
            {"title": "feat: x (#289)", "body": ""},
        )
        assert out is not None
        hook = out["hookSpecificOutput"]
        assert hook["permissionDecision"] == "deny"
        assert hook["hookEventName"] == "PreToolUse"
        reason = hook["permissionDecisionReason"]
        assert "(#289)" in reason

    def test_update_pull_request_also_gated(self) -> None:
        out = preflight.decide(
            "mcp__github__update_pull_request",
            {"title": "fix: y (#1)"},
        )
        assert out is not None
        assert (
            out["hookSpecificOutput"]["permissionDecision"] == "deny"
        )

    def test_multiple_refs_all_listed(self) -> None:
        out = preflight.decide(
            "mcp__github__create_pull_request",
            {"title": "chore: a (#1) and b (#22)"},
        )
        assert out is not None
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        assert "(#1)" in reason
        assert "(#22)" in reason

    def test_hash_outside_parens_allows(self) -> None:
        """Server-side gate matches only ``(#NNN)``; mirror that."""
        out = preflight.decide(
            "mcp__github__create_pull_request",
            {"title": "docs: see #123 for context"},
        )
        assert out is None

    def test_missing_title_allows(self) -> None:
        out = preflight.decide(
            "mcp__github__create_pull_request",
            {"body": "no title supplied"},
        )
        assert out is None

    def test_empty_title_allows(self) -> None:
        out = preflight.decide(
            "mcp__github__create_pull_request",
            {"title": "", "body": "x"},
        )
        assert out is None

    def test_non_string_title_allows(self) -> None:
        out = preflight.decide(
            "mcp__github__create_pull_request",
            {"title": 42, "body": "x"},
        )
        assert out is None

    @pytest.mark.parametrize(
        "tool_name",
        [
            # Other GitHub MCP write tools whose payloads do not feed
            # the PR title policy.
            "mcp__github__issue_write",
            "mcp__github__add_issue_comment",
            "mcp__github__add_reply_to_pull_request_comment",
            "mcp__github__pull_request_review_write",
            "mcp__github__sub_issue_write",
            # Non-GitHub tools.
            "mcp__github__list_issues",
            "mcp__github__pull_request_read",
            "Bash",
            "Read",
        ],
    )
    def test_off_target_tools_allow(self, tool_name: str) -> None:
        out = preflight.decide(tool_name, {"title": "feat: x (#1)"})
        assert out is None

    @pytest.mark.parametrize(
        "tool_name",
        [
            "mcp__github__create_pull_request",
            "mcp__github__update_pull_request",
        ],
    )
    def test_every_targeted_tool_is_gated(self, tool_name: str) -> None:
        out = preflight.decide(tool_name, {"title": "feat: x (#1)"})
        assert out is not None
        assert (
            out["hookSpecificOutput"]["permissionDecision"] == "deny"
        )


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
        rc = preflight.main([])
        captured = capsys.readouterr()
        return rc, captured.out, captured.err

    def test_clean_event_emits_nothing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        event = {
            "tool_name": "mcp__github__create_pull_request",
            "tool_input": {"title": "feat: clean", "body": "Closes #1"},
        }
        rc, out, err = self._run(monkeypatch, capsys, json.dumps(event))
        assert rc == 0
        assert out == ""
        assert err == ""

    def test_dirty_event_emits_deny_json(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        event = {
            "tool_name": "mcp__github__create_pull_request",
            "tool_input": {"title": "feat: x (#1)", "body": ""},
        }
        rc, out, err = self._run(monkeypatch, capsys, json.dumps(event))
        assert rc == 0
        decision = json.loads(out)
        hook = decision["hookSpecificOutput"]
        assert hook["permissionDecision"] == "deny"
        assert hook["hookEventName"] == "PreToolUse"
        assert err == ""

    def test_off_target_tool_emits_nothing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        event = {
            "tool_name": "mcp__github__issue_write",
            "tool_input": {"title": "feat: x (#1)"},
        }
        rc, out, err = self._run(monkeypatch, capsys, json.dumps(event))
        assert rc == 0
        assert out == ""

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
        rc, out, err = self._run(
            monkeypatch, capsys, json.dumps({"foo": "bar"})
        )
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
        # Empty stdin -> event is {} -> missing tool_name -> error log.
        assert "::error::" in err
