"""Tests for scripts/check_commit_signing_ready.py.

Refs #1987 (PR #1985 retrospective, Fact 2). Pins the live test-sign gate that
fails loud when commit.gpgsign is true but a commit would land unsigned.

The probe (probe_sign_status) is exercised against a mocked ``run_git`` so no
real signer is invoked; higher-level modes mock ``probe_sign_status`` /
``signing_required`` directly to pin the decision branches.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from unittest.mock import patch

import check_commit_signing_ready as subject
import pytest

pytestmark = pytest.mark.shard_preflight


def _cp(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr="")


# ---------------------------------------------------------------------------
# _is_remote
# ---------------------------------------------------------------------------
class TestIsRemote:
    def test_false_when_no_signal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
        monkeypatch.delenv("CODEX_CODE_REMOTE", raising=False)
        assert subject._is_remote() is False

    def test_true_on_claude_signal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
        monkeypatch.delenv("CODEX_CODE_REMOTE", raising=False)
        assert subject._is_remote() is True

    def test_true_on_codex_signal(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
        monkeypatch.setenv("CODEX_CODE_REMOTE", "TRUE")
        assert subject._is_remote() is True

    def test_false_on_other_value(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("CLAUDE_CODE_REMOTE", "1")
        monkeypatch.delenv("CODEX_CODE_REMOTE", raising=False)
        assert subject._is_remote() is False


# ---------------------------------------------------------------------------
# _git_config_get / signing_required
# ---------------------------------------------------------------------------
class TestGitConfigGet:
    def test_returns_value(self) -> None:
        with patch("check_commit_signing_ready.run_git", return_value=_cp(0, "ssh\n")):
            assert subject._git_config_get("gpg.format") == "ssh"

    def test_none_on_nonzero(self) -> None:
        with patch("check_commit_signing_ready.run_git", return_value=_cp(1, "")):
            assert subject._git_config_get("gpg.format") is None

    def test_none_on_empty(self) -> None:
        with patch("check_commit_signing_ready.run_git", return_value=_cp(0, "  \n")):
            assert subject._git_config_get("user.signingkey") is None

    def test_none_when_git_missing(self) -> None:
        with patch("check_commit_signing_ready.run_git", side_effect=RuntimeError("no git")):
            assert subject._git_config_get("gpg.format") is None


class TestSigningRequired:
    def test_true_when_bool_true(self) -> None:
        with patch("check_commit_signing_ready.run_git", return_value=_cp(0, "true\n")):
            assert subject.signing_required() is True

    def test_false_when_bool_false(self) -> None:
        with patch("check_commit_signing_ready.run_git", return_value=_cp(0, "false\n")):
            assert subject.signing_required() is False

    def test_false_when_unset(self) -> None:
        with patch("check_commit_signing_ready.run_git", return_value=_cp(1, "")):
            assert subject.signing_required() is False

    def test_false_when_git_missing(self) -> None:
        with patch("check_commit_signing_ready.run_git", side_effect=RuntimeError("no git")):
            assert subject.signing_required() is False


# ---------------------------------------------------------------------------
# probe_sign_status
# ---------------------------------------------------------------------------
class TestProbeSignStatus:
    @staticmethod
    def _router(*, commit_rc: int = 0, cat_rc: int = 0, cat_out: str = "") -> object:
        """Build a run_git side_effect keyed on the git subcommand."""

        def _run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            if args[0] == "init":
                return _cp(0, "")
            # remaining calls are ``-C <tmp> <subcommand> ...``
            sub = args[2] if len(args) > 2 else ""
            if sub == "config":
                return _cp(0, "")
            if sub == "commit":
                return _cp(commit_rc, "")
            if sub == "cat-file":
                return _cp(cat_rc, cat_out)
            return _cp(0, "")

        return _run

    def test_signed_when_gpgsig_present(self) -> None:
        body = "tree abc\nauthor a\ngpgsig -----BEGIN SSH SIGNATURE-----\n\nmsg\n"
        with patch("check_commit_signing_ready.run_git", side_effect=self._router(cat_out=body)):
            assert subject.probe_sign_status() == "signed"

    def test_unsigned_when_no_gpgsig(self) -> None:
        body = "tree abc\nauthor a\ncommitter c\n\nmsg\n"
        with patch("check_commit_signing_ready.run_git", side_effect=self._router(cat_out=body)):
            assert subject.probe_sign_status() == "unsigned"

    def test_unknown_when_commit_fails(self) -> None:
        with patch("check_commit_signing_ready.run_git", side_effect=self._router(commit_rc=1)):
            assert subject.probe_sign_status() == "unknown"

    def test_unknown_when_cat_file_fails(self) -> None:
        with patch("check_commit_signing_ready.run_git", side_effect=self._router(cat_rc=1)):
            assert subject.probe_sign_status() == "unknown"

    def test_unknown_when_init_fails(self) -> None:
        with patch("check_commit_signing_ready.run_git", return_value=_cp(1, "")):
            assert subject.probe_sign_status() == "unknown"

    def test_unknown_when_git_missing(self) -> None:
        with patch("check_commit_signing_ready.run_git", side_effect=RuntimeError("no git")):
            assert subject.probe_sign_status() == "unknown"

    def test_unknown_on_timeout(self) -> None:
        with patch(
            "check_commit_signing_ready.run_git",
            side_effect=subprocess.TimeoutExpired(cmd="git", timeout=1),
        ):
            assert subject.probe_sign_status() == "unknown"

    def test_unknown_when_mkdtemp_fails(self) -> None:
        with patch("check_commit_signing_ready.tempfile.mkdtemp", side_effect=OSError("no space")):
            assert subject.probe_sign_status() == "unknown"

    def test_copies_present_signing_config_into_probe(self) -> None:
        """Set keys that resolve to a value; skip the ones that are unset."""
        calls: list[list[str]] = []

        def _run(args: list[str], **_kwargs: object) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            if args[0] == "config" and args[1] == "--get":
                return _cp(0, "ssh\n") if args[2] == "gpg.format" else _cp(1, "")
            if len(args) > 2 and args[2] == "cat-file":
                return _cp(0, "gpgsig x\n")
            return _cp(0, "")

        with patch("check_commit_signing_ready.run_git", side_effect=_run):
            assert subject.probe_sign_status() == "signed"
        # gpg.format resolved -> applied into the probe repo; user.signingkey unset -> not applied.
        # Probe config-set calls are ``["-C", tmp, "config", <key>, <value>]``.
        applied = {c[3] for c in calls if len(c) > 4 and c[0] == "-C" and c[2] == "config"}
        assert "gpg.format" in applied
        assert "user.signingkey" not in applied


# ---------------------------------------------------------------------------
# decide (PreToolUse hook mode)
# ---------------------------------------------------------------------------
@pytest.fixture
def _remote(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")


class TestDecide:
    def test_none_when_not_remote(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
        monkeypatch.delenv("CODEX_CODE_REMOTE", raising=False)
        event = {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}
        assert subject.decide(event) is None

    def test_none_when_not_bash(self, _remote: None) -> None:
        assert subject.decide({"tool_name": "Edit", "tool_input": {}}) is None

    def test_none_when_not_git_commit(self, _remote: None) -> None:
        event = {"tool_name": "Bash", "tool_input": {"command": "git status"}}
        assert subject.decide(event) is None

    def test_none_when_commit_tree(self, _remote: None) -> None:
        event = {"tool_name": "Bash", "tool_input": {"command": "git commit-tree abc"}}
        assert subject.decide(event) is None

    def test_none_when_ack_marker(self, _remote: None) -> None:
        event = {"tool_name": "Bash", "tool_input": {"command": "git commit -m x # unsigned-ack"}}
        with patch("check_commit_signing_ready.probe_sign_status") as probe:
            assert subject.decide(event) is None
        probe.assert_not_called()

    def test_none_when_signing_not_required(self, _remote: None) -> None:
        event = {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}
        with patch("check_commit_signing_ready.signing_required", return_value=False):
            assert subject.decide(event) is None

    def test_none_when_signed(self, _remote: None) -> None:
        event = {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}
        with (
            patch("check_commit_signing_ready.signing_required", return_value=True),
            patch("check_commit_signing_ready.probe_sign_status", return_value="signed"),
        ):
            assert subject.decide(event) is None

    def test_none_when_unknown(self, _remote: None) -> None:
        event = {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}
        with (
            patch("check_commit_signing_ready.signing_required", return_value=True),
            patch("check_commit_signing_ready.probe_sign_status", return_value="unknown"),
        ):
            assert subject.decide(event) is None

    def test_deny_when_unsigned(self, _remote: None) -> None:
        event = {"tool_name": "Bash", "tool_input": {"command": "git add -A && git commit -m x"}}
        with (
            patch("check_commit_signing_ready.signing_required", return_value=True),
            patch("check_commit_signing_ready.probe_sign_status", return_value="unsigned"),
        ):
            decision = subject.decide(event)
        assert decision is not None
        reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
        assert "UNSIGNED" in reason
        assert "# unsigned-ack" in reason

    def test_none_on_probe_exception(self, _remote: None) -> None:
        event = {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}
        with (
            patch("check_commit_signing_ready.signing_required", return_value=True),
            patch("check_commit_signing_ready.probe_sign_status", side_effect=RuntimeError("boom")),
        ):
            assert subject.decide(event) is None

    @pytest.mark.parametrize(
        "command",
        [
            "git -C /workspace/claude-md commit -m x",
            "git -c user.name=x commit -m x",
            "git -c user.name=x -c user.email=y commit -m x",
            "git --no-pager commit -m x",
            "git --git-dir=/x/.git commit -m x",
            "cd /x && git -C /x commit -m x",
        ],
    )
    def test_deny_with_git_global_options(self, _remote: None, command: str) -> None:
        # Codex review on #1993: global options before ``commit`` must not let
        # the live signing probe be skipped.
        event = {"tool_name": "Bash", "tool_input": {"command": command}}
        with (
            patch("check_commit_signing_ready.signing_required", return_value=True),
            patch("check_commit_signing_ready.probe_sign_status", return_value="unsigned"),
        ):
            assert subject.decide(event) is not None

    @pytest.mark.parametrize(
        "command",
        [
            "git merge origin/main",
            "git merge --no-ff origin/main",
            "git -C /x merge origin/main",
            "git rebase origin/main",
            "git cherry-pick abc123",
            "git revert HEAD",
            "git am < patch.mbox",
            "git pull origin main",
            "git fetch origin main && git merge origin/main",
        ],
    )
    def test_deny_for_other_commit_producers(self, _remote: None, command: str) -> None:
        # retro #2114 / #2116: a cold signer leaves merge/rebase/cherry-pick/
        # revert/am/pull commits unsigned too, not only ``git commit``; the
        # PR #2103 unsigned ancestors came from the no-rebase ``git merge``.
        event = {"tool_name": "Bash", "tool_input": {"command": command}}
        with (
            patch("check_commit_signing_ready.signing_required", return_value=True),
            patch("check_commit_signing_ready.probe_sign_status", return_value="unsigned"),
        ):
            assert subject.decide(event) is not None

    @pytest.mark.parametrize(
        "command",
        [
            'git commit -m "--abort"',
            'git commit -m "fix --ff-only path"',
            "(git commit -m x)",
            "$(git commit -m x)",
            "`git commit -m x`",
            "{ git commit -m x; }",
        ],
    )
    def test_deny_for_quoted_or_grouped_commit(self, _remote: None, command: str) -> None:
        # A commit must be probed even when its message token equals a
        # non-creating flag, or when it is wrapped in a subshell / backtick
        # (Codex review and /code-review on #2120).
        event = {"tool_name": "Bash", "tool_input": {"command": command}}
        with (
            patch("check_commit_signing_ready.signing_required", return_value=True),
            patch("check_commit_signing_ready.probe_sign_status", return_value="unsigned"),
        ):
            assert subject.decide(event) is not None

    def test_none_when_git_commit_is_quoted_argument(self, _remote: None) -> None:
        # ``echo "git commit"`` is one quoted token, not a real commit; the
        # probe must not run (no false positive).
        event = {"tool_name": "Bash", "tool_input": {"command": 'echo "git commit"'}}
        with patch("check_commit_signing_ready.probe_sign_status") as probe:
            assert subject.decide(event) is None
        probe.assert_not_called()

    @pytest.mark.parametrize(
        "command",
        [
            "git commit-tree abc",
            "git merge-base HEAD origin/main",
            "git merge-file a b c",
            "git config commit.gpgsign true",
            "git -c x=y config commit.gpgsign true",
            "git -C /x status",
            # Non-creating modes of producer subcommands cannot mint a commit,
            # so a cold signer must not block them (Codex review on #2120).
            "git merge --abort",
            "git merge --ff-only origin/main",
            "git merge --no-commit origin/x",
            "git pull --ff-only origin main",
            "git rebase --abort",
            "git rebase --skip",
            "git cherry-pick --quit",
            "git -C /x merge --abort",
        ],
    )
    def test_none_when_commit_only_as_argument(self, _remote: None, command: str) -> None:
        # ``commit`` appearing as a config key / non-subcommand must not match.
        event = {"tool_name": "Bash", "tool_input": {"command": command}}
        with patch("check_commit_signing_ready.probe_sign_status") as probe:
            assert subject.decide(event) is None
        probe.assert_not_called()


# ---------------------------------------------------------------------------
# cmd_session_start
# ---------------------------------------------------------------------------
class TestSessionStart:
    def test_no_output_when_not_remote(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
        monkeypatch.delenv("CODEX_CODE_REMOTE", raising=False)
        assert subject.cmd_session_start(argparse_ns()) == 0
        assert capsys.readouterr().out == ""

    def test_no_output_when_not_required(
        self, _remote: None, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch("check_commit_signing_ready.signing_required", return_value=False):
            assert subject.cmd_session_start(argparse_ns()) == 0
        assert capsys.readouterr().out == ""

    def test_no_output_when_signed(self, _remote: None, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("check_commit_signing_ready.signing_required", return_value=True),
            patch("check_commit_signing_ready.probe_sign_status", return_value="signed"),
        ):
            assert subject.cmd_session_start(argparse_ns()) == 0
        assert capsys.readouterr().out == ""

    def test_warns_when_unsigned(self, _remote: None, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("check_commit_signing_ready.signing_required", return_value=True),
            patch("check_commit_signing_ready.probe_sign_status", return_value="unsigned"),
        ):
            assert subject.cmd_session_start(argparse_ns()) == 0
        parsed = json.loads(capsys.readouterr().out)
        assert "NOT READY" in parsed["hookSpecificOutput"]["additionalContext"]

    def test_exits_zero_on_exception(
        self, _remote: None, capsys: pytest.CaptureFixture[str]
    ) -> None:
        with patch("check_commit_signing_ready.signing_required", side_effect=RuntimeError("boom")):
            assert subject.cmd_session_start(argparse_ns()) == 0
        assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# cmd_check
# ---------------------------------------------------------------------------
class TestCheck:
    def test_ok_when_not_required(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("check_commit_signing_ready.signing_required", return_value=False):
            assert subject.cmd_check(argparse_ns()) == 0
        assert "not enabled" in capsys.readouterr().out

    def test_ok_when_signed(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("check_commit_signing_ready.signing_required", return_value=True),
            patch("check_commit_signing_ready.probe_sign_status", return_value="signed"),
        ):
            assert subject.cmd_check(argparse_ns()) == 0
        assert "verified signature" in capsys.readouterr().out

    def test_fail_when_unsigned(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("check_commit_signing_ready.signing_required", return_value=True),
            patch("check_commit_signing_ready.probe_sign_status", return_value="unsigned"),
        ):
            assert subject.cmd_check(argparse_ns()) == 1
        assert "UNSIGNED" in capsys.readouterr().err

    def test_unknown_returns_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        with (
            patch("check_commit_signing_ready.signing_required", return_value=True),
            patch("check_commit_signing_ready.probe_sign_status", return_value="unknown"),
        ):
            assert subject.cmd_check(argparse_ns()) == 0
        assert "UNKNOWN" in capsys.readouterr().out

    def test_unknown_on_exception(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch("check_commit_signing_ready.signing_required", side_effect=RuntimeError("boom")):
            assert subject.cmd_check(argparse_ns()) == 0
        assert "UNKNOWN" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# main dispatch
# ---------------------------------------------------------------------------
class TestMain:
    def test_session_start_dispatch(self) -> None:
        with patch("check_commit_signing_ready.cmd_session_start", return_value=0) as fn:
            assert subject.main(["session-start"]) == 0
        fn.assert_called_once()

    def test_check_dispatch(self) -> None:
        with patch("check_commit_signing_ready.cmd_check", return_value=1) as fn:
            assert subject.main(["check"]) == 1
        fn.assert_called_once()

    def test_default_runs_hook(self) -> None:
        with patch("check_commit_signing_ready.run_event_hook", return_value=0) as fn:
            assert subject.main([]) == 0
        fn.assert_called_once()
        assert fn.call_args.args[0] == "check_commit_signing_ready"


def argparse_ns() -> argparse.Namespace:
    return argparse.Namespace()
