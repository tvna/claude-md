"""Tests for ``scripts/gate_reserved_retro_scope.py``.

Verifies that:
- An ``mcp__github__issue_write`` ``create`` whose title carries the reserved
  ``auto-retro`` scope (any Conventional Commit type, plus the legacy no-colon
  prefix) is denied, with a reason naming the reserved scope and #1395.
- A create whose title uses a non-reserved scope passes through.
- Non-create methods, off-target tools, and an absent / non-string title fail
  open (no decision).
- The reserved-scope verdict is the OR of the two single-source detectors in
  :mod:`auto_retro`.
- The stdin/stdout boundary works end-to-end.
"""

from __future__ import annotations

import io
import json

import auto_retro
import gate_reserved_retro_scope as gate
import pytest

pytestmark = pytest.mark.shard_preflight


def _create_input(title: object) -> dict[str, object]:
    return {"method": "create", "owner": "o", "repo": "r", "title": title}


class TestUsesReservedScope:
    @pytest.mark.parametrize(
        "title",
        [
            "chore(auto-retro): review PR #5 repair loops",
            "fix(auto-retro): close retro #5",
            "docs(auto-retro): document retro outcome",
            "feat(auto-retro): something",
            # legacy no-colon prefix caught by is_retro_issue_title
            "chore(auto-retro) review PR #5 repair loops",
        ],
    )
    def test_reserved_scope_titles_match(self, title: str) -> None:
        assert gate.uses_reserved_scope(title) is True

    @pytest.mark.parametrize(
        "title",
        [
            "chore(retro-visibility): track retro fields",
            "fix(gate): close the omission",
            "feat(auto): unrelated auto scope",
            "chore(retro): legacy migrated scope",
            "docs: no scope at all",
            "",
        ],
    )
    def test_non_reserved_titles_do_not_match(self, title: str) -> None:
        assert gate.uses_reserved_scope(title) is False

    def test_verdict_is_or_of_single_sources(self) -> None:
        # The gate must never disagree with the detectors it guards.
        title = "chore(auto-retro): review PR #5 repair loops"
        assert gate.uses_reserved_scope(title) == (
            auto_retro.is_retro_pr(title)
            or auto_retro.is_retro_issue_title(title)
        )


class TestDecide:
    def test_reserved_scope_create_is_denied(self) -> None:
        # A reserved-scope title that is NOT the canonical handoff retro shape
        # (Refs #1581 exception) stays denied.
        decision = gate.decide(
            "mcp__github__issue_write",
            _create_input("fix(auto-retro): close retro #5"),
        )
        assert decision is not None
        out = decision["hookSpecificOutput"]
        assert out["permissionDecision"] == "deny"
        reason = out["permissionDecisionReason"]
        assert "auto-retro" in reason
        assert "#1395" in reason

    def test_canonical_handoff_retro_title_is_allowed(self) -> None:
        # Refs #1581 / D1: the pre-merge handoff survey opens the canonical
        # retro in-session. The single permitted exception is the EXACT
        # build_retro_title shape; the gate must NOT deny it.
        decision = gate.decide(
            "mcp__github__issue_write",
            _create_input("chore(auto-retro): review PR #5 repair loops"),
        )
        assert decision is None

    def test_canonical_exception_aligns_with_build_retro_title(self) -> None:
        # The allow-list predicate must never drift from the title producer:
        # whatever build_retro_title emits must pass the gate.
        pr = auto_retro.MergedPR(
            number=4242,
            title="fix(x): y",
            merged=True,
            merged_at="2026-06-10T00:00:00Z",
            merged_by_login="human",
            user_login="human",
            layer_labels=(),
            html_url="",
        )
        canonical = auto_retro.build_retro_title(pr)
        assert auto_retro.is_canonical_handoff_retro_title(canonical) is True
        assert (
            gate.decide("mcp__github__issue_write", _create_input(canonical))
            is None
        )

    def test_other_auto_retro_titles_still_denied(self) -> None:
        # The exception is narrow: every other auto-retro title stays denied,
        # including the legacy no-colon prefix and a different fix/docs scope.
        for title in (
            "docs(auto-retro): document retro outcome",
            "chore(auto-retro) review PR #5 repair loops",
            "chore(auto-retro): review PR #5 repair loops extra",
        ):
            decision = gate.decide(
                "mcp__github__issue_write", _create_input(title)
            )
            assert decision is not None, title
            assert (
                decision["hookSpecificOutput"]["permissionDecision"] == "deny"
            )

    def test_non_reserved_scope_create_passes(self) -> None:
        decision = gate.decide(
            "mcp__github__issue_write",
            _create_input("chore(retro-visibility): track retro fields"),
        )
        assert decision is None

    def test_update_method_passes(self) -> None:
        tool_input = {
            "method": "update",
            "owner": "o",
            "repo": "r",
            "title": "chore(auto-retro): review PR #5 repair loops",
        }
        assert gate.decide("mcp__github__issue_write", tool_input) is None

    def test_missing_title_fails_open(self) -> None:
        tool_input = {"method": "create", "owner": "o", "repo": "r"}
        assert gate.decide("mcp__github__issue_write", tool_input) is None

    def test_non_string_title_fails_open(self) -> None:
        assert gate.decide("mcp__github__issue_write", _create_input(123)) is None

    @pytest.mark.parametrize(
        "tool_name",
        [
            "mcp__github__create_pull_request",
            "mcp__github__add_issue_comment",
            "Bash",
        ],
    )
    def test_off_target_tools_pass(self, tool_name: str) -> None:
        assert (
            gate.decide(
                tool_name,
                _create_input("chore(auto-retro): review PR #5 repair loops"),
            )
            is None
        )


class TestMain:
    def _run(self, payload: object, monkeypatch: pytest.MonkeyPatch) -> str:
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        rc = gate.main()
        assert rc == 0
        return stdout_buf.getvalue()

    def test_reserved_scope_create_produces_deny(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stdout = self._run(
            {
                "tool_name": "mcp__github__issue_write",
                "tool_input": _create_input(
                    "fix(auto-retro): close retro #5"
                ),
            },
            monkeypatch,
        )
        decision = json.loads(stdout)
        assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_canonical_handoff_retro_produces_no_output(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Refs #1581: the permitted handoff retro create yields no decision.
        stdout = self._run(
            {
                "tool_name": "mcp__github__issue_write",
                "tool_input": _create_input(
                    "chore(auto-retro): review PR #5 repair loops"
                ),
            },
            monkeypatch,
        )
        assert stdout == ""

    def test_non_reserved_create_produces_no_output(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        stdout = self._run(
            {
                "tool_name": "mcp__github__issue_write",
                "tool_input": _create_input("fix(gate): close the omission"),
            },
            monkeypatch,
        )
        assert stdout == ""

    def test_empty_stdin_is_handled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        stdout_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", io.StringIO())
        assert gate.main() == 0
        assert stdout_buf.getvalue() == ""

    def test_malformed_json_fails_open(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        assert gate.main() == 0
        assert stdout_buf.getvalue() == ""
        assert "malformed" in stderr_buf.getvalue()


def test_main_block_exits_via_runpy(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy

    monkeypatch.setattr(
        "sys.stdin", type("Input", (), {"read": lambda self: ""})()
    )
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("gate_reserved_retro_scope", run_name="__main__")
    assert exc_info.value.code == 0
