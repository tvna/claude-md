"""Tests for scripts/preflight_issue_ci_staleness.py.

Covers the decision logic for blocking mcp__github__issue_write create calls
that appear to be about CI failures without a verification phrase. Refs #1944.
"""

from __future__ import annotations

import io
import json
from typing import Any

import preflight_issue_ci_staleness as gate
import pytest

pytestmark = pytest.mark.shard_ci_ops


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _create_input(title: str = "", body: str = "") -> dict[str, Any]:
    return {"method": "create", "title": title, "body": body}


def _update_input(title: str = "", body: str = "") -> dict[str, Any]:
    return {"method": "update", "title": title, "body": body, "issue_number": 1}


# ---------------------------------------------------------------------------
# _looks_like_ci_failure
# ---------------------------------------------------------------------------


class TestLooksLikeCiFailure:
    def test_actions_run_url_matches(self) -> None:
        assert gate._looks_like_ci_failure(
            "CI failure", "https://github.com/org/repo/actions/runs/12345"
        )

    def test_stale_keyword_matches(self) -> None:
        assert gate._looks_like_ci_failure("docs/generated/ is stale", "")

    def test_post_merge_ci_keyword_matches(self) -> None:
        assert gate._looks_like_ci_failure("", "post-merge CI failed")

    def test_ci_failure_keyword_matches(self) -> None:
        assert gate._looks_like_ci_failure("CI failure in main", "")

    def test_docs_generated_keyword_matches(self) -> None:
        assert gate._looks_like_ci_failure("", "docs/generated/ drift detected")

    def test_workflow_failed_keyword_matches(self) -> None:
        assert gate._looks_like_ci_failure("", "workflow failed after merge")

    def test_job_failed_keyword_matches(self) -> None:
        assert gate._looks_like_ci_failure("", "job failed with exit code 1")

    def test_unrelated_issue_does_not_match(self) -> None:
        assert not gate._looks_like_ci_failure(
            "Add new feature", "Implement the new API endpoint."
        )

    def test_empty_strings_do_not_match(self) -> None:
        assert not gate._looks_like_ci_failure("", "")

    def test_retrospective_issue_does_not_match(self) -> None:
        assert not gate._looks_like_ci_failure(
            "chore(retro): post-merge retrospective for PR #1933",
            "Two repairs between PR open and merge.",
        )

    def test_case_insensitive(self) -> None:
        assert gate._looks_like_ci_failure("", "CI FAILURE on main branch")

    def test_actions_run_url_case_insensitive(self) -> None:
        assert gate._looks_like_ci_failure(
            "", "GitHub.com/org/repo/actions/runs/99999"
        )


# ---------------------------------------------------------------------------
# _has_verification_phrase
# ---------------------------------------------------------------------------


class TestHasVerificationPhrase:
    def test_exact_phrase_matches(self) -> None:
        assert gate._has_verification_phrase(gate.FRESH_MAIN_CHECK_PHRASE)

    def test_phrase_in_body_matches(self) -> None:
        body = f"Some text. {gate.FRESH_MAIN_CHECK_PHRASE}. More text."
        assert gate._has_verification_phrase(body)

    def test_phrase_case_insensitive(self) -> None:
        assert gate._has_verification_phrase(gate.FRESH_MAIN_CHECK_PHRASE.upper())

    def test_missing_phrase_returns_false(self) -> None:
        assert not gate._has_verification_phrase("No verification here.")

    def test_empty_body_returns_false(self) -> None:
        assert not gate._has_verification_phrase("")


# ---------------------------------------------------------------------------
# decide
# ---------------------------------------------------------------------------


class TestDecide:
    def test_non_target_tool_allowed(self) -> None:
        assert gate.decide("mcp__github__create_pull_request", _create_input("CI failure", "")) is None

    def test_codex_connector_ci_failure_without_phrase_blocked(self) -> None:
        result = gate.decide(
            "mcp__codex_apps__github._create_issue",
            _create_input("CI failure in main", "The job failed."),
        )
        assert result is not None
        assert result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"

    def test_codex_connector_ci_failure_with_phrase_allowed(self) -> None:
        body = f"The job failed. {gate.FRESH_MAIN_CHECK_PHRASE}"
        result = gate.decide(
            "mcp__codex_apps__github._create_issue",
            _create_input("CI failure in main", body),
        )
        assert result is None

    def test_codex_connector_real_payload_without_phrase_blocked(self) -> None:
        """Real _create_issue payloads have no 'method' field; gate must still fire."""
        inp = {"title": "CI failure in main", "body": "The job failed."}
        result = gate.decide("mcp__codex_apps__github._create_issue", inp)
        assert result is not None
        assert result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"

    def test_codex_connector_real_payload_with_phrase_allowed(self) -> None:
        """Real _create_issue payloads with verification phrase must pass through."""
        inp = {
            "title": "CI failure in main",
            "body": f"The job failed. {gate.FRESH_MAIN_CHECK_PHRASE}",
        }
        result = gate.decide("mcp__codex_apps__github._create_issue", inp)
        assert result is None

    def test_update_method_allowed(self) -> None:
        assert gate.decide("mcp__github__issue_write", _update_input("CI failure", "")) is None

    def test_ci_failure_without_phrase_blocked(self) -> None:
        result = gate.decide(
            "mcp__github__issue_write",
            _create_input("CI failure in main", "The job failed."),
        )
        assert result is not None
        assert result.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"

    def test_ci_failure_with_phrase_allowed(self) -> None:
        body = f"The job failed. {gate.FRESH_MAIN_CHECK_PHRASE}"
        result = gate.decide(
            "mcp__github__issue_write",
            _create_input("CI failure in main", body),
        )
        assert result is None

    def test_actions_url_without_phrase_blocked(self) -> None:
        body = "See https://github.com/org/repo/actions/runs/12345 for details."
        result = gate.decide(
            "mcp__github__issue_write",
            _create_input("Investigate failure", body),
        )
        assert result is not None

    def test_unrelated_issue_allowed(self) -> None:
        result = gate.decide(
            "mcp__github__issue_write",
            _create_input("Add feature X", "Implement the new endpoint."),
        )
        assert result is None

    def test_stale_docs_without_phrase_blocked(self) -> None:
        result = gate.decide(
            "mcp__github__issue_write",
            _create_input(
                "fix(generated): regenerate docs/generated/",
                "docs/generated/ is stale after merge.",
            ),
        )
        assert result is not None

    def test_stale_docs_with_phrase_allowed(self) -> None:
        body = (
            "docs/generated/ is stale after merge. "
            f"{gate.FRESH_MAIN_CHECK_PHRASE}"
        )
        result = gate.decide(
            "mcp__github__issue_write",
            _create_input("fix(generated): regenerate docs", body),
        )
        assert result is None

    def test_deny_reason_mentions_verification_phrase(self) -> None:
        result = gate.decide(
            "mcp__github__issue_write",
            _create_input("CI failure", "job failed"),
        )
        assert result is not None
        reason = result.get("hookSpecificOutput", {}).get("permissionDecisionReason", "")
        assert gate.FRESH_MAIN_CHECK_PHRASE in reason

    def test_non_string_title_handled(self) -> None:
        inp = {"method": "create", "title": None, "body": "CI failure"}
        result = gate.decide("mcp__github__issue_write", inp)
        assert result is not None

    def test_non_string_body_handled(self) -> None:
        inp = {"method": "create", "title": "CI failure", "body": None}
        result = gate.decide("mcp__github__issue_write", inp)
        assert result is not None

    def test_retrospective_issue_allowed(self) -> None:
        result = gate.decide(
            "mcp__github__issue_write",
            _create_input(
                "chore(retro): post-merge retrospective for PR #1933",
                "Two repairs between PR open and merge.",
            ),
        )
        assert result is None


# ---------------------------------------------------------------------------
# main() integration
# ---------------------------------------------------------------------------


class TestMain:
    def _run(
        self, tool_name: str, tool_input: dict[str, Any], monkeypatch: pytest.MonkeyPatch
    ) -> tuple[str, int]:
        event = {"hook_event_name": "PreToolUse", "tool_name": tool_name, "tool_input": tool_input}
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
        stdout_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        rc = gate.main()
        return stdout_buf.getvalue(), rc

    def test_main_blocks_ci_failure_without_phrase(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out, rc = self._run(
            "mcp__github__issue_write",
            _create_input("CI failure", "docs/generated/ is stale"),
            monkeypatch,
        )
        assert rc == 0
        assert out
        decision = json.loads(out)
        assert decision.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"

    def test_main_allows_ci_failure_with_phrase(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        body = f"docs/generated/ is stale. {gate.FRESH_MAIN_CHECK_PHRASE}"
        out, rc = self._run(
            "mcp__github__issue_write",
            _create_input("CI failure", body),
            monkeypatch,
        )
        assert rc == 0
        assert out == ""

    def test_main_allows_unrelated_issue(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        out, rc = self._run(
            "mcp__github__issue_write",
            _create_input("Add feature", "Implement the new API endpoint."),
            monkeypatch,
        )
        assert rc == 0
        assert out == ""

    def test_main_fails_open_on_bad_stdin(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        rc = gate.main()
        assert rc == 0
