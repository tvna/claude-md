"""Tests for ``scripts/preflight_title_policy.py``.

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.

Mirrors the table-driven style of ``tests/test_preflight_non_ascii.py``.
Pure functions get parametrize cases; the stdin/stdout boundary in
:func:`preflight_title_policy.main` is exercised with ``monkeypatch``
over ``sys.stdin`` and ``capsys`` over ``sys.stdout``/``sys.stderr``.

Refs #496. Supersedes ``tests/test_preflight_pr_title_issue_ref.py``
(extended issue-write coverage to close the gap surfaced by triage
2026-05-27, tracking #491 / #492 / #493).
"""

from __future__ import annotations

import io
import json

import preflight_title_policy as preflight
import pytest

pytestmark = pytest.mark.shard_preflight
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
# kind_for_tool
# ---------------------------------------------------------------------------


class TestKindForTool:
    @pytest.mark.parametrize(
        ("tool_name", "expected"),
        [
            ("mcp__github__issue_write", "issue"),
            ("mcp__github__create_pull_request", "pull_request"),
            ("mcp__github__update_pull_request", "pull_request"),
        ],
    )
    def test_targeted_tools(self, tool_name: str, expected: str) -> None:
        assert preflight.kind_for_tool(tool_name) == expected

    @pytest.mark.parametrize(
        "tool_name",
        [
            "mcp__github__add_issue_comment",
            "mcp__github__sub_issue_write",
            "mcp__github__pull_request_read",
            "mcp__github__list_issues",
            "Bash",
            "Read",
        ],
    )
    def test_off_target_returns_none(self, tool_name: str) -> None:
        assert preflight.kind_for_tool(tool_name) is None


# ---------------------------------------------------------------------------
# find_invalid_type
# ---------------------------------------------------------------------------


class TestFindInvalidType:
    @pytest.mark.parametrize(
        "title",
        [
            "feat: add thing",
            "fix(scope): bug",
            "feat(scripts): add ruff S security gate for workflow scripts",
            "chore: housekeeping",
            "ci(workflows): tighten gate",
            "docs(agent): rewrite section",
            "perf: shave allocations",
            "refactor(api): rename module",
            "revert: undo prior change",
            "style: format",
            "test: add coverage",
            "tracking: umbrella",
            "build: pin dep",
        ],
    )
    def test_known_type_returns_none_for_pull_request(self, title: str) -> None:
        assert preflight.find_invalid_type(title, kind="pull_request") is None

    @pytest.mark.parametrize(
        "title",
        [
            "tracking: umbrella for triage round",
            "ci(ops): preflight hook for title-policy",
            "feat(scripts): add helper",
        ],
    )
    def test_known_type_returns_none_for_issue(self, title: str) -> None:
        assert preflight.find_invalid_type(title, kind="issue") is None

    @pytest.mark.parametrize(
        ("title", "expected_prefix"),
        [
            # The exact prefix that triggered the 2026-05-27 triage repair.
            ("ops: preflight hook for title-policy", "ops"),
            # The repair from PR #346 -> retro #347 -> #348.
            ("security(scripts): enable ruff S rules", "security"),
            # Bare unknown type, no scope.
            ("hotfix: emergency", "hotfix"),
            # Capitalized type does not match the lowercase configured types.
            ("Feat: shouted", "Feat"),
            # Missing the required ": " separator.
            ("featx add thing", "featx add thing"),
            # Scope present but type unknown.
            ("wip(scope): in progress", "wip"),
        ],
    )
    def test_unknown_type_returns_offending_prefix_for_pull_request(self, title: str, expected_prefix: str) -> None:
        assert preflight.find_invalid_type(title, kind="pull_request") == expected_prefix

    def test_unknown_type_returns_offending_prefix_for_issue(self) -> None:
        # The exact title shape from issues #491, #492, #493.
        assert preflight.find_invalid_type("ops: foo", kind="issue") == "ops"

    def test_empty_title_returns_empty_prefix(self) -> None:
        assert preflight.find_invalid_type("", kind="pull_request") == ""


# ---------------------------------------------------------------------------
# build_non_ascii_deny_reason
# ---------------------------------------------------------------------------


class TestBuildNonAsciiDenyReason:
    def test_quotes_findings_and_title(self) -> None:
        reason = preflight.build_non_ascii_deny_reason(
            "mcp__github__create_pull_request",
            "pull_request",
            "feat: テst",
            ["index 6: U+30C6"],
        )
        assert "U+30C6" in reason
        assert "'feat: テst'" in reason
        assert "pull_request" in reason

    def test_cites_server_side_authority(self) -> None:
        reason = preflight.build_non_ascii_deny_reason(
            "mcp__github__issue_write",
            "issue",
            "feat: x‍y",
            ["index 7: U+200D"],
        )
        assert "title_policy.py" in reason
        assert "#155" in reason
        assert "issue" in reason

    def test_includes_tool_name(self) -> None:
        reason = preflight.build_non_ascii_deny_reason(
            "mcp__github__update_pull_request",
            "pull_request",
            "feat: x‍y",
            ["index 7: U+200D"],
        )
        assert "mcp__github__update_pull_request" in reason


# ---------------------------------------------------------------------------
# build_invalid_type_deny_reason
# ---------------------------------------------------------------------------


class TestBuildInvalidTypeDenyReason:
    def test_names_offending_prefix_and_expected_shape(self) -> None:
        reason = preflight.build_invalid_type_deny_reason(
            "mcp__github__create_pull_request",
            "pull_request",
            "security(scripts): enable ruff S rules",
            "security",
        )
        assert "'security'" in reason
        assert "type(scope): summary" in reason
        # Full allowed-type list so the agent does not need to re-read
        # title_policy.py to recover.
        assert "feat" in reason
        assert "tracking" in reason

    def test_cites_server_side_authority(self) -> None:
        reason = preflight.build_invalid_type_deny_reason(
            "mcp__github__create_pull_request",
            "pull_request",
            "wip(scope): something",
            "wip",
        )
        assert "title_policy.py" in reason
        assert "verify-title-policy.yml" in reason

    def test_offers_likely_alternative_for_security_titles(self) -> None:
        reason = preflight.build_invalid_type_deny_reason(
            "mcp__github__create_pull_request",
            "pull_request",
            "security(scripts): enable ruff S rules",
            "security",
        )
        # Concrete remediation: PR #346 retro #347 names this exact path.
        assert "feat(" in reason or "ci(" in reason

    def test_mentions_ops_repair_for_issue_titles(self) -> None:
        # The 2026-05-27 triage repair fingerprint (ops: -> ci(ops): ...).
        reason = preflight.build_invalid_type_deny_reason(
            "mcp__github__issue_write",
            "issue",
            "ops: foo",
            "ops",
        )
        assert "ci(ops):" in reason


# ---------------------------------------------------------------------------
# build_issue_ref_deny_reason
# ---------------------------------------------------------------------------


class TestBuildIssueRefDenyReason:
    def test_lists_every_offending_token(self) -> None:
        reason = preflight.build_issue_ref_deny_reason(
            "mcp__github__create_pull_request",
            "chore: a (#1) and b (#22)",
            ["(#1)", "(#22)"],
            "chore: a and b",
        )
        assert "(#1)" in reason
        assert "(#22)" in reason

    def test_references_server_side_rule(self) -> None:
        reason = preflight.build_issue_ref_deny_reason(
            "mcp__github__create_pull_request",
            "feat: x (#1)",
            ["(#1)"],
            "feat: x",
        )
        assert "title_policy.py" in reason
        assert "#167" in reason
        assert "#214" in reason
        assert "verify-issue-link.yml" in reason

    def test_shows_suggested_fix(self) -> None:
        reason = preflight.build_issue_ref_deny_reason(
            "mcp__github__update_pull_request",
            "feat: x (#1)",
            ["(#1)"],
            "feat: x",
        )
        assert "'feat: x'" in reason

    def test_includes_tool_name(self) -> None:
        reason = preflight.build_issue_ref_deny_reason(
            "mcp__github__update_pull_request",
            "feat: x (#1)",
            ["(#1)"],
            "feat: x",
        )
        assert "mcp__github__update_pull_request" in reason


# ---------------------------------------------------------------------------
# decide -- issue_write
# ---------------------------------------------------------------------------


class TestDecideIssueWrite:
    def test_clean_issue_title_allows(self) -> None:
        out = preflight.decide(
            "mcp__github__issue_write",
            {
                "method": "create",
                "title": "tracking: umbrella for triage 2026-05-27",
                "body": "...",
            },
        )
        assert out is None

    def test_ops_prefix_denies(self) -> None:
        # The exact failure mode from #491 / #492 / #493 motivating #496.
        out = preflight.decide(
            "mcp__github__issue_write",
            {"method": "create", "title": "ops: preflight hook missing", "body": ""},
        )
        assert out is not None
        hook = out["hookSpecificOutput"]
        assert hook["permissionDecision"] == "deny"
        assert hook["hookEventName"] == "PreToolUse"
        reason = hook["permissionDecisionReason"]
        assert "'ops'" in reason
        assert "type(scope): summary" in reason
        # The repair fingerprint cited in the deny reason.
        assert "ci(ops):" in reason

    def test_non_ascii_issue_title_denies(self) -> None:
        out = preflight.decide(
            "mcp__github__issue_write",
            {"method": "create", "title": "feat: テst"},
        )
        assert out is not None
        hook = out["hookSpecificOutput"]
        assert hook["permissionDecision"] == "deny"
        assert "U+30C6" in hook["permissionDecisionReason"]
        assert "#155" in hook["permissionDecisionReason"]

    def test_update_without_title_skips(self) -> None:
        # ``issue_write method=update`` may omit the title field when the
        # caller only changes body / labels / state. The hook must not
        # block those calls.
        out = preflight.decide(
            "mcp__github__issue_write",
            {"method": "update", "issue_number": 42, "body": "new body"},
        )
        assert out is None

    def test_issue_title_with_paren_ref_allows(self) -> None:
        # ``(#NNN)`` is forbidden in PR titles only; issue titles may
        # carry it (rare, but consistent with title_policy.verify_title).
        out = preflight.decide(
            "mcp__github__issue_write",
            {"method": "create", "title": "tracking: parent for #491 (#491)"},
        )
        assert out is None


# ---------------------------------------------------------------------------
# decide -- pull_request
# ---------------------------------------------------------------------------


class TestDecidePullRequest:
    def test_clean_pr_title_allows(self) -> None:
        out = preflight.decide(
            "mcp__github__create_pull_request",
            {"title": "feat(harness): add preflight gate", "body": "..."},
        )
        assert out is None

    def test_issue_ref_denies(self) -> None:
        out = preflight.decide(
            "mcp__github__create_pull_request",
            {"title": "feat: x (#289)", "body": ""},
        )
        assert out is not None
        hook = out["hookSpecificOutput"]
        assert hook["permissionDecision"] == "deny"
        assert "(#289)" in hook["permissionDecisionReason"]

    def test_update_pull_request_also_gated(self) -> None:
        out = preflight.decide(
            "mcp__github__update_pull_request",
            {"title": "fix: y (#1)"},
        )
        assert out is not None
        assert out["hookSpecificOutput"]["permissionDecision"] == "deny"

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
        out = preflight.decide(
            "mcp__github__create_pull_request",
            {"title": "docs: see #123 for context"},
        )
        assert out is None

    def test_unknown_type_denies(self) -> None:
        out = preflight.decide(
            "mcp__github__create_pull_request",
            {"title": "security(scripts): enable ruff S rules"},
        )
        assert out is not None
        hook = out["hookSpecificOutput"]
        assert hook["permissionDecision"] == "deny"
        reason = hook["permissionDecisionReason"]
        assert "'security'" in reason
        assert "type(scope): summary" in reason

    def test_non_ascii_pr_title_denies(self) -> None:
        out = preflight.decide(
            "mcp__github__create_pull_request",
            {"title": "feat: テst"},
        )
        assert out is not None
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        assert "U+30C6" in reason

    def test_zero_width_joiner_denies(self) -> None:
        out = preflight.decide(
            "mcp__github__create_pull_request",
            {"title": "feat: x‍y"},
        )
        assert out is not None
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        assert "U+200D" in reason

    def test_performance_type_mismatch_denies(self) -> None:
        out = preflight.decide(
            "mcp__github__create_pull_request",
            {
                "title": "fix(devcontainer): cache image builds",
                "body": "## Facts\n\n- Fact: caches image builds to reduce runtime.",
            },
        )
        assert out is not None
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        assert "does not fit" in reason
        assert "perf(devcontainer)" in reason

    def test_devcontainer_perf_title_allows(self) -> None:
        out = preflight.decide(
            "mcp__github__create_pull_request",
            {
                "title": "perf(devcontainer): cache image builds",
                "body": "## Facts\n\n- Fact: caches image builds to reduce runtime.",
            },
        )
        assert out is None


# ---------------------------------------------------------------------------
# decide -- rule precedence & skip paths
# ---------------------------------------------------------------------------


class TestDecidePrecedenceAndSkip:
    def test_non_ascii_wins_over_type_and_ref(self) -> None:
        out = preflight.decide(
            "mcp__github__create_pull_request",
            {"title": "unknownt: テst (#1)"},
        )
        assert out is not None
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        assert "non-ASCII" in reason
        # Issue-ref deny text would name "issue-reference"; assert absent.
        assert "issue-reference" not in reason

    def test_invalid_type_wins_over_issue_ref(self) -> None:
        out = preflight.decide(
            "mcp__github__create_pull_request",
            {"title": "unknownt: clean (#1)"},
        )
        assert out is not None
        reason = out["hookSpecificOutput"]["permissionDecisionReason"]
        assert "'unknownt'" in reason
        assert "issue-reference" not in reason

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
            "mcp__github__add_issue_comment",
            "mcp__github__add_reply_to_pull_request_comment",
            "mcp__github__pull_request_review_write",
            "mcp__github__sub_issue_write",
            "mcp__github__list_issues",
            "mcp__github__pull_request_read",
            "Bash",
            "Read",
        ],
    )
    def test_off_target_tools_allow(self, tool_name: str) -> None:
        out = preflight.decide(tool_name, {"title": "ops: foo (#1)"})
        assert out is None

    @pytest.mark.parametrize(
        "tool_name",
        [
            "mcp__github__issue_write",
            "mcp__github__create_pull_request",
            "mcp__github__update_pull_request",
        ],
    )
    def test_every_targeted_tool_is_gated(self, tool_name: str) -> None:
        out = preflight.decide(tool_name, {"title": "ops: foo"})
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
        rc = preflight.main([])
        captured = capsys.readouterr()
        return rc, captured.out, captured.err

    def test_clean_pr_event_emits_nothing(
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

    def test_clean_issue_event_emits_nothing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        event = {
            "tool_name": "mcp__github__issue_write",
            "tool_input": {"method": "create", "title": "tracking: x", "body": "..."},
        }
        rc, out, err = self._run(monkeypatch, capsys, json.dumps(event))
        assert rc == 0
        assert out == ""
        assert err == ""

    def test_ops_prefix_issue_event_emits_deny_json(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Live verification fingerprint for Issue #496 AC: a call with
        # title `ops: foo` against issue_write is denied locally.
        event = {
            "tool_name": "mcp__github__issue_write",
            "tool_input": {"method": "create", "title": "ops: foo", "body": ""},
        }
        rc, out, err = self._run(monkeypatch, capsys, json.dumps(event))
        assert rc == 0
        decision = json.loads(out)
        hook = decision["hookSpecificOutput"]
        assert hook["permissionDecision"] == "deny"
        assert hook["hookEventName"] == "PreToolUse"
        assert "'ops'" in hook["permissionDecisionReason"]
        assert err == ""

    def test_dirty_pr_event_emits_deny_json(
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
        assert err == ""

    def test_off_target_tool_emits_nothing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        event = {
            "tool_name": "mcp__github__add_issue_comment",
            "tool_input": {"body": "ops: would be off-target"},
        }
        rc, out, err = self._run(monkeypatch, capsys, json.dumps(event))
        assert rc == 0
        assert out == ""

    def test_update_without_title_emits_nothing(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        event = {
            "tool_name": "mcp__github__issue_write",
            "tool_input": {"method": "update", "issue_number": 42, "body": "x"},
        }
        rc, out, err = self._run(monkeypatch, capsys, json.dumps(event))
        assert rc == 0
        assert out == ""
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

    def test_non_ascii_pr_event_emits_deny_json(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        event = {
            "tool_name": "mcp__github__update_pull_request",
            "tool_input": {"title": "feat: テst"},
        }
        rc, out, err = self._run(monkeypatch, capsys, json.dumps(event))
        assert rc == 0
        decision = json.loads(out)
        hook = decision["hookSpecificOutput"]
        assert hook["permissionDecision"] == "deny"
        assert "U+30C6" in hook["permissionDecisionReason"]
        assert err == ""
