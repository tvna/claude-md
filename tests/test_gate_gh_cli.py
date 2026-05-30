"""Tests for ``scripts/gate_gh_cli.py``.

Verifies that:
- ``gh`` CLI invocations are denied with a redirect to scripts/github_api.py.
- Direct ``curl api.github.com`` calls are denied.
- ``scripts/github_api.py`` calls pass through.
- Non-Bash tools are ignored.
- The stdin/stdout boundary works end-to-end.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gate_gh_cli as ggc

pytestmark = pytest.mark.shard_preflight


class TestDecide:
    @pytest.mark.parametrize(
        "command",
        [
            "gh api repos/owner/repo/issues",
            "gh issue list --state open",
            "gh pr create --title foo",
            "gh release list",
            "gh repo view",
            "echo ok && gh issue view 1",
            "gh auth status",
            "gh search issues --repo owner/repo",
        ],
    )
    def test_gh_cli_calls_are_denied(self, command: str) -> None:
        decision = ggc.decide("Bash", command)
        assert decision is not None
        assert decision["permissionDecision"] == "deny"
        assert "scripts/github_api.py" in decision["decisionReason"]
        assert "gh" in decision["decisionReason"]

    @pytest.mark.parametrize(
        "command",
        [
            "curl https://api.github.com/repos/owner/repo/issues",
            "curl -H 'Authorization: Bearer tok' https://api.github.com/repos/o/r/pulls",
            "curl -s http://api.github.com/repos/o/r/issues",
        ],
    )
    def test_curl_github_api_calls_are_denied(self, command: str) -> None:
        decision = ggc.decide("Bash", command)
        assert decision is not None
        assert decision["permissionDecision"] == "deny"
        assert "scripts/github_api.py" in decision["decisionReason"]

    @pytest.mark.parametrize(
        "command",
        [
            "python3 scripts/github_api.py GET https://api.github.com/repos/o/r/issues",
            "python3 scripts/github_api.py GET https://api.github.com/repos/o/r/issues --fields number,title",
            "curl https://example.com/data",
            "git status",
            "ls -la",
            "echo 'github api is cool'",
            "python3 scripts/preflight_push_base.py",
        ],
    )
    def test_approved_commands_pass_through(self, command: str) -> None:
        assert ggc.decide("Bash", command) is None

    @pytest.mark.parametrize(
        "tool_name",
        ["Read", "Edit", "Write", "mcp__github__issue_write", "Bash2"],
    )
    def test_non_bash_tools_are_ignored(self, tool_name: str) -> None:
        assert ggc.decide(tool_name, "gh api anything") is None

    @pytest.mark.parametrize(
        "command",
        [
            # 'gh' as part of path/variable should NOT be blocked
            "echo 'not_gh api'",
            "cat /usr/share/github/config",
        ],
    )
    def test_gh_in_non_cli_context_passes(self, command: str) -> None:
        assert ggc.decide("Bash", command) is None

    def test_deny_message_contains_mcp_alternative_for_writes(self) -> None:
        decision = ggc.decide("Bash", "gh pr create --title foo")
        assert decision is not None
        assert "mcp__github__" in decision["decisionReason"]


class TestMain:
    def _run(self, payload: object, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        ggc.main()
        return stdout_buf.getvalue(), stderr_buf.getvalue()

    def test_gh_cli_produces_deny(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout, _ = self._run(
            {"tool_name": "Bash", "tool_input": {"command": "gh issue list"}},
            monkeypatch,
        )
        decision = json.loads(stdout)
        assert decision["permissionDecision"] == "deny"

    def test_curl_github_api_produces_deny(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout, _ = self._run(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "curl https://api.github.com/repos/o/r/issues"},
            },
            monkeypatch,
        )
        decision = json.loads(stdout)
        assert decision["permissionDecision"] == "deny"

    def test_approved_command_produces_no_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout, _ = self._run(
            {
                "tool_name": "Bash",
                "tool_input": {
                    "command": "python3 scripts/github_api.py GET https://api.github.com/repos/o/r/issues"
                },
            },
            monkeypatch,
        )
        assert stdout == ""

    def test_empty_stdin_is_handled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        rc = ggc.main()
        assert rc == 0
        assert stdout_buf.getvalue() == ""

    def test_malformed_json_fails_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        rc = ggc.main()
        assert rc == 0
        assert stdout_buf.getvalue() == ""
        assert "malformed" in stderr_buf.getvalue()

    def test_missing_tool_name_fails_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout, stderr = self._run({"tool_input": {"command": "gh api"}}, monkeypatch)
        assert stdout == ""
        assert "tool_name" in stderr


def test_main_block_exits_via_runpy(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy

    monkeypatch.setattr("sys.stdin", type("Input", (), {"read": lambda self: ""})())
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("gate_gh_cli", run_name="__main__")
    assert exc_info.value.code == 0
