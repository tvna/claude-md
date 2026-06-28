"""Tests for ``scripts/gate_unsigned_commit_bash.py``.

Verifies that:
- ``git -c commit.gpgsign=<false-ish>`` invocations are denied.
- ``git --no-gpg-sign`` invocations are denied.
- Plain ``git commit`` and benign mentions in strings/args pass through.
- The ``# unsigned-ack`` opt-in marker passes through.
- Non-Bash tools are ignored.
- The stdin/stdout boundary works end-to-end (fail-open on bad input).
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gate_unsigned_commit_bash as gucb

pytestmark = pytest.mark.shard_preflight


class TestDecide:
    @pytest.mark.parametrize(
        "command",
        [
            "git -c commit.gpgsign=false commit -m 'x'",
            "git -c commit.gpgsign=0 commit -m 'x'",
            "git -c commit.gpgsign=no commit",
            "git -c commit.gpgsign=off commit",
            "git -c commit.gpgsign=FALSE commit",
            "git -c commit.gpgSign=false commit",
            "/usr/bin/git -c commit.gpgsign=false commit",
            "git -c user.name=x -c commit.gpgsign=false commit -m y",
            "echo ok && git -c commit.gpgsign=false commit -m y",
            "git -c commit.gpgsign=false rebase --continue",
        ],
    )
    def test_inline_gpgsign_off_is_denied(self, command: str) -> None:
        decision = gucb.decide("Bash", {"command": command})
        assert decision is not None
        assert decision["permissionDecision"] == "deny"
        assert "commit.gpgsign" in decision["decisionReason"]

    @pytest.mark.parametrize(
        "command",
        [
            "git commit --no-gpg-sign -m 'x'",
            "git commit -m 'x' --no-gpg-sign",
            "git merge --no-gpg-sign topic",
            "git cherry-pick --no-gpg-sign abc123",
            "echo ok && git commit --no-gpg-sign",
        ],
    )
    def test_no_gpg_sign_flag_is_denied(self, command: str) -> None:
        decision = gucb.decide("Bash", {"command": command})
        assert decision is not None
        assert decision["permissionDecision"] == "deny"
        assert "--no-gpg-sign" in decision["decisionReason"]

    @pytest.mark.parametrize(
        "command",
        [
            "git commit -m 'x'",
            "git -c commit.gpgsign=true commit -m 'x'",
            "git -c core.pager=cat log",
            "git status",
            "git push origin main",
            # benign mention inside a quoted string, not command position
            "echo 'git -c commit.gpgsign=false commit'",
            'echo "run: git commit --no-gpg-sign"',
            # a positional that merely looks like the assignment (not after -c)
            "git commit -m 'commit.gpgsign=false'",
            "ls -la",
        ],
    )
    def test_benign_commands_pass_through(self, command: str) -> None:
        assert gucb.decide("Bash", {"command": command}) is None

    @pytest.mark.parametrize(
        "command",
        [
            "git -c commit.gpgsign=false commit -m y  # unsigned-ack",
            "git commit --no-gpg-sign -m y  # unsigned-ack",
        ],
    )
    def test_ack_marker_passes_through(self, command: str) -> None:
        assert gucb.decide("Bash", {"command": command}) is None

    @pytest.mark.parametrize(
        "tool_name",
        ["Read", "Edit", "Write", "mcp__github__issue_write", "Bash2"],
    )
    def test_non_bash_tools_are_ignored(self, tool_name: str) -> None:
        assert gucb.decide(tool_name, {"command": "git -c commit.gpgsign=false commit"}) is None

    def test_empty_command_passes_through(self) -> None:
        assert gucb.decide("Bash", {"command": ""}) is None
        assert gucb.decide("Bash", {}) is None


class TestMain:
    def _run(self, payload: object, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        gucb.main()
        return stdout_buf.getvalue(), stderr_buf.getvalue()

    def test_bypass_produces_deny(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout, _ = self._run(
            {
                "tool_name": "Bash",
                "tool_input": {"command": "git -c commit.gpgsign=false commit -m x"},
            },
            monkeypatch,
        )
        decision = json.loads(stdout)
        assert decision["permissionDecision"] == "deny"

    def test_benign_produces_no_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout, _ = self._run(
            {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}},
            monkeypatch,
        )
        assert stdout == ""

    def test_empty_stdin_is_handled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        rc = gucb.main()
        assert rc == 0
        assert stdout_buf.getvalue() == ""

    def test_malformed_json_fails_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        rc = gucb.main()
        assert rc == 0
        assert stdout_buf.getvalue() == ""
        assert "malformed" in stderr_buf.getvalue()

    def test_missing_tool_name_fails_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout, stderr = self._run(
            {"tool_input": {"command": "git -c commit.gpgsign=false commit"}},
            monkeypatch,
        )
        assert stdout == ""
        assert "tool_name" in stderr

    def test_non_dict_tool_input_is_handled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout, _ = self._run({"tool_name": "Bash", "tool_input": "not-a-dict"}, monkeypatch)
        assert stdout == ""


def test_main_block_exits_via_runpy(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy

    monkeypatch.setattr("sys.stdin", type("Input", (), {"read": lambda self: ""})())
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("gate_unsigned_commit_bash", run_name="__main__")
    assert exc_info.value.code == 0
