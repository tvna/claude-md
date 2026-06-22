"""Tests for ``scripts/gate_pr_body_retro_issue_link.py``.

Verifies that:
- ``has_retro_label``: returns True for retro labels, False otherwise.
- ``decide``:
  - off-target tool -> None (pass-through)
  - missing body -> None
  - retro-close PR title -> None (permitted exception)
  - no refs in body -> None
  - missing owner/repo -> None
  - no token -> None (fail-open)
  - retro issue linked (``type:retrospective``) -> deny
  - retro issue linked (``auto-retro``) -> deny
  - non-retro issue linked -> None
  - label lookup failure -> None (fail-open)
  - multiple refs: one retro -> deny naming it
  - Codex canonicalised tool name -> deny
- stdin/stdout boundary: block written to stdout when a retro issue is linked.

Refs #1882.
"""

from __future__ import annotations

import io
import json
from typing import Any

import gate_pr_body_retro_issue_link as gate
import pytest

pytestmark = pytest.mark.shard_preflight

_TOKEN = "tok"
_OWNER = "o"
_REPO = "r"


def _input(
    body: str,
    title: str = "fix(x): do the thing",
    owner: str = _OWNER,
    repo: str = _REPO,
) -> dict[str, Any]:
    return {"owner": owner, "repo": repo, "title": title, "body": body}


def _decide(
    tool_name: str,
    body: str,
    *,
    title: str = "fix(x): do the thing",
    labels_by_number: dict[int, list[str] | None] | None = None,
    token: str | None = _TOKEN,
) -> dict[str, Any] | None:
    labels = labels_by_number or {}
    return gate.decide(
        tool_name,
        _input(body, title=title),
        token_getter=lambda: token,
        label_getter=lambda _o, _r, n: labels.get(n, []),
    )


# ---------------------------------------------------------------------------
# has_retro_label
# ---------------------------------------------------------------------------


class TestHasRetroLabel:
    def test_type_retrospective(self) -> None:
        assert gate.has_retro_label(["type:retrospective"]) is True

    def test_auto_retro(self) -> None:
        assert gate.has_retro_label(["auto-retro"]) is True

    def test_both(self) -> None:
        assert gate.has_retro_label(["type:retrospective", "auto-retro"]) is True

    def test_non_retro_labels(self) -> None:
        assert gate.has_retro_label(["type:fix", "layer:p3-harness"]) is False

    def test_empty(self) -> None:
        assert gate.has_retro_label([]) is False


# ---------------------------------------------------------------------------
# decide -- pass-through paths
# ---------------------------------------------------------------------------


class TestDecidePassThrough:
    def test_off_target_tool_is_noop(self) -> None:
        assert (
            gate.decide(
                "mcp__github__merge_pull_request",
                _input("Closes #1"),
                token_getter=lambda: _TOKEN,
                label_getter=lambda _o, _r, _n: ["type:retrospective"],
            )
            is None
        )

    def test_missing_body_is_noop(self) -> None:
        result = gate.decide(
            "mcp__github__create_pull_request",
            {"owner": _OWNER, "repo": _REPO},
            token_getter=lambda: _TOKEN,
            label_getter=lambda _o, _r, _n: ["type:retrospective"],
        )
        assert result is None

    def test_retro_close_pr_title_is_allowed(self) -> None:
        # A retro-close PR may link a retro issue directly.
        assert (
            _decide(
                "mcp__github__create_pull_request",
                "Closes #42",
                title="chore(auto-retro): review PR #42 repair loops",
                labels_by_number={42: ["type:retrospective", "auto-retro"]},
            )
            is None
        )

    def test_no_refs_is_noop(self) -> None:
        assert (
            _decide(
                "mcp__github__create_pull_request",
                "No issue reference here.",
            )
            is None
        )

    def test_missing_owner_is_noop(self) -> None:
        result = gate.decide(
            "mcp__github__create_pull_request",
            {"repo": _REPO, "body": "Closes #1"},
            token_getter=lambda: _TOKEN,
            label_getter=lambda _o, _r, _n: ["type:retrospective"],
        )
        assert result is None

    def test_no_token_is_fail_open(self) -> None:
        assert (
            _decide(
                "mcp__github__create_pull_request",
                "Closes #42",
                labels_by_number={42: ["type:retrospective"]},
                token=None,
            )
            is None
        )

    def test_label_lookup_failure_is_fail_open(self) -> None:
        # None from label_getter means API failure -> fail-open.
        assert (
            _decide(
                "mcp__github__create_pull_request",
                "Closes #42",
                labels_by_number={42: None},
            )
            is None
        )

    def test_non_retro_issue_is_allowed(self) -> None:
        assert (
            _decide(
                "mcp__github__create_pull_request",
                "Closes #42",
                labels_by_number={42: ["type:fix", "layer:p3-harness"]},
            )
            is None
        )

    def test_refs_in_html_comment_ignored(self) -> None:
        # strip_html_comments removes the reference before extract_refs sees it.
        body = "<!-- Refs #42 -->\n## Summary\n\nCloses #99"
        assert (
            _decide(
                "mcp__github__create_pull_request",
                body,
                labels_by_number={42: ["type:retrospective"], 99: ["type:fix"]},
            )
            is None
        )


# ---------------------------------------------------------------------------
# decide -- deny paths
# ---------------------------------------------------------------------------


class TestDecideDeny:
    def test_retro_issue_via_closes_is_denied(self) -> None:
        decision = _decide(
            "mcp__github__create_pull_request",
            "Closes #42",
            labels_by_number={42: ["type:retrospective"]},
        )
        assert decision is not None
        out = decision["hookSpecificOutput"]
        assert out["permissionDecision"] == "deny"
        reason = out["permissionDecisionReason"]
        assert "#42" in reason
        assert "retro-close PR" in reason
        assert "#1882" in reason

    def test_retro_issue_via_refs_is_denied(self) -> None:
        decision = _decide(
            "mcp__github__create_pull_request",
            "Refs #7",
            labels_by_number={7: ["auto-retro"]},
        )
        assert decision is not None
        assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_update_pull_request_also_denied(self) -> None:
        decision = _decide(
            "mcp__github__update_pull_request",
            "Closes #7",
            labels_by_number={7: ["type:retrospective"]},
        )
        assert decision is not None
        assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_only_retro_issues_named_in_reason(self) -> None:
        # When multiple refs are present, only retro ones appear in the reason.
        decision = _decide(
            "mcp__github__create_pull_request",
            "Closes #10\nCloses #20",
            labels_by_number={10: ["type:retrospective"], 20: ["type:fix"]},
        )
        assert decision is not None
        reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
        assert "#10" in reason
        assert "#20" not in reason

    def test_codex_tool_name_canonicalised(self) -> None:
        # The Codex variant name is canonicalised to the MCP name before matching.
        decision = gate.decide(
            "mcp__codex_apps__github._create_pull_request",
            _input("Closes #5"),
            token_getter=lambda: _TOKEN,
            label_getter=lambda _o, _r, _n: ["type:retrospective"],
        )
        assert decision is not None
        assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"


# ---------------------------------------------------------------------------
# stdin/stdout boundary
# ---------------------------------------------------------------------------


class TestMain:
    def _run(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tool_name: str,
        body: str,
        labels_by_number: dict[int, list[str]],
        token: str = _TOKEN,
    ) -> str:
        event = json.dumps({
            "tool_name": tool_name,
            "tool_input": _input(body),
        })
        monkeypatch.setenv("GH_TOKEN", token)
        monkeypatch.setattr("sys.stdin", io.StringIO(event))
        out = io.StringIO()
        monkeypatch.setattr("sys.stdout", out)

        def _fake_fetch(owner: str, repo: str, number: int, *, token: str, **_: object) -> list[str] | None:
            return labels_by_number.get(number)

        monkeypatch.setattr(gate, "fetch_labels", _fake_fetch)
        assert gate.main() == 0
        return out.getvalue()

    def test_deny_written_to_stdout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        out = self._run(
            monkeypatch,
            "mcp__github__create_pull_request",
            "Closes #42",
            {42: ["type:retrospective"]},
        )
        payload = json.loads(out)
        assert payload["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_no_output_for_non_retro(self, monkeypatch: pytest.MonkeyPatch) -> None:
        out = self._run(
            monkeypatch,
            "mcp__github__create_pull_request",
            "Closes #42",
            {42: ["type:fix"]},
        )
        assert out == ""
