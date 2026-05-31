"""Tests for ``scripts/gate_update_pr_branch.py``.

Verifies that:
- ``mcp__github__update_pull_request_branch`` is denied with a clear recovery path.
- Other tools pass through.
- The stdin/stdout boundary works end-to-end.
- The deny reason references the recovery runbook and issue #893.
"""

from __future__ import annotations

import io
import json

import gate_update_pr_branch as gub
import pytest

pytestmark = pytest.mark.shard_preflight


class TestDecide:
    def test_target_tool_is_denied(self) -> None:
        decision = gub.decide("mcp__github__update_pull_request_branch")
        assert decision is not None
        assert decision["permissionDecision"] == "deny"

    def test_deny_reason_contains_recovery_steps(self) -> None:
        decision = gub.decide("mcp__github__update_pull_request_branch")
        assert decision is not None
        reason = decision["decisionReason"]
        assert "origin/main" in reason
        assert "replacement-branch" in reason
        assert "single commit" in reason

    def test_deny_reason_references_runbook(self) -> None:
        decision = gub.decide("mcp__github__update_pull_request_branch")
        assert decision is not None
        assert "update-pr-branch-recovery.md" in decision["decisionReason"]

    def test_deny_reason_references_issue(self) -> None:
        decision = gub.decide("mcp__github__update_pull_request_branch")
        assert decision is not None
        assert "#893" in decision["decisionReason"]

    @pytest.mark.parametrize(
        "tool_name",
        [
            "mcp__github__create_pull_request",
            "mcp__github__merge_pull_request",
            "mcp__github__list_pull_requests",
            "Bash",
            "Read",
        ],
    )
    def test_other_tools_pass_through(self, tool_name: str) -> None:
        assert gub.decide(tool_name) is None


class TestMain:
    def _run(self, payload: object, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        gub.main()
        return stdout_buf.getvalue(), stderr_buf.getvalue()

    def test_target_tool_produces_deny(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout, _ = self._run(
            {"tool_name": "mcp__github__update_pull_request_branch", "tool_input": {}},
            monkeypatch,
        )
        decision = json.loads(stdout)
        assert decision["permissionDecision"] == "deny"

    def test_other_tool_produces_no_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout, _ = self._run(
            {"tool_name": "mcp__github__create_pull_request", "tool_input": {}},
            monkeypatch,
        )
        assert stdout == ""

    def test_empty_stdin_is_handled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        rc = gub.main()
        assert rc == 0
        assert stdout_buf.getvalue() == ""

    def test_malformed_json_fails_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        rc = gub.main()
        assert rc == 0
        assert stdout_buf.getvalue() == ""
        assert "malformed" in stderr_buf.getvalue()

    def test_missing_tool_name_fails_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout, stderr = self._run({"tool_input": {}}, monkeypatch)
        assert stdout == ""
        assert "tool_name" in stderr


def test_main_block_exits_via_runpy(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy

    monkeypatch.setattr("sys.stdin", type("Input", (), {"read": lambda self: ""})())
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("gate_update_pr_branch", run_name="__main__")
    assert exc_info.value.code == 0
