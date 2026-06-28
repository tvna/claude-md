"""Tests for ``scripts/preflight_push_unsigned_commits.py``.

Refs #2138. Verifies that the PreToolUse hook denies a ``git push`` whose
pushed commits include an unsigned one, allows a push of only signed commits,
and falls open everywhere a deny would be a guess: a non-remote session, a
non-Bash tool, a non-push command, an ``# unsigned-ack`` marker, an
undeterminable range, or a git error. A new branch (all-zeros remote sha) is
scanned via ``rev-list --not --remotes`` so all of its commits are checked.
"""

from __future__ import annotations

import io
import json
import subprocess
from typing import Any

import preflight_push_unsigned_commits as subject
import pytest

pytestmark = pytest.mark.shard_preflight

_LOCAL_SHA = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
_REMOTE_SHA = "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
_ALL_ZEROS = "0" * 40
_SIGNED = "1111111111111111111111111111111111111111"
_UNSIGNED = "2222222222222222222222222222222222222222"


def _bash_event(command: str) -> dict[str, Any]:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _cp(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["git"], returncode=returncode, stdout=stdout, stderr="")


class _FakeGit:
    """A canned ``git`` runner keyed on the subcommand.

    ``rev_parse`` maps a ref to a sha (absent -> non-zero exit, i.e. unresolved).
    ``rev_list`` is the list returned for any ``rev-list`` call. ``unsigned`` is
    the set of shas whose ``cat-file commit`` object carries no ``gpgsig``
    header (the signed shas get one); the gate reads that header presence.
    """

    def __init__(
        self,
        *,
        rev_parse: dict[str, str] | None = None,
        rev_list: list[str] | None = None,
        rev_list_rc: int = 0,
        unsigned: set[str] | None = None,
        raise_on: str | None = None,
    ) -> None:
        self.rev_parse = rev_parse or {}
        self.rev_list = rev_list if rev_list is not None else []
        self.rev_list_rc = rev_list_rc
        self.unsigned = unsigned or set()
        self.raise_on = raise_on
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        sub = args[0]
        if self.raise_on is not None and sub == self.raise_on:
            raise OSError("boom")
        if sub == "rev-parse":
            ref = args[-1]
            sha = self.rev_parse.get(ref)
            if sha is None:
                return _cp(returncode=1)
            return _cp(stdout=sha + "\n")
        if sub == "rev-list":
            if self.rev_list_rc != 0:
                return _cp(returncode=self.rev_list_rc)
            return _cp(stdout="\n".join(self.rev_list) + "\n")
        if sub == "cat-file":
            sha = args[-1]
            headers = "tree 0\nauthor a <a@b> 0 +0000\ncommitter a <a@b> 0 +0000\n"
            if sha not in self.unsigned:
                headers += (
                    "gpgsig -----BEGIN SSH SIGNATURE-----\n"
                    " AAAA\n -----END SSH SIGNATURE-----\n"
                )
            return _cp(stdout=headers + "\nmessage body mentioning gpgsig\n")
        return _cp()


@pytest.fixture
def remote(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")


# ---------------------------------------------------------------------------
# environment / target gates -> fail-open
# ---------------------------------------------------------------------------


def test_passthrough_when_not_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    monkeypatch.delenv("CODEX_CODE_REMOTE", raising=False)
    git = _FakeGit(unsigned={_UNSIGNED})
    assert subject.decide(_bash_event("git push origin feat/x"), runner=git) is None
    assert git.calls == []  # never even shells out


def test_codex_remote_signal_activates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    monkeypatch.setenv("CODEX_CODE_REMOTE", "true")
    git = _FakeGit(
        rev_parse={"HEAD": _LOCAL_SHA, "refs/remotes/origin/feat/x": _REMOTE_SHA},
        rev_list=[_UNSIGNED],
        unsigned={_UNSIGNED},
    )
    result = subject.decide(_bash_event("git push origin feat/x"), runner=git)
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_passthrough_non_bash_tool(remote: None) -> None:
    git = _FakeGit(unsigned={_UNSIGNED})
    event = {"tool_name": "Write", "tool_input": {"command": "git push origin feat/x"}}
    assert subject.decide(event, runner=git) is None


def test_passthrough_bash_non_push(remote: None) -> None:
    git = _FakeGit(unsigned={_UNSIGNED})
    assert subject.decide(_bash_event("git status"), runner=git) is None
    assert subject.decide(_bash_event("git commit -m x"), runner=git) is None


def test_passthrough_ack_marker(remote: None) -> None:
    git = _FakeGit(
        rev_parse={"HEAD": _LOCAL_SHA, "refs/remotes/origin/feat/x": _REMOTE_SHA},
        rev_list=[_UNSIGNED],
        unsigned={_UNSIGNED},
    )
    cmd = "git push origin feat/x  # unsigned-ack"
    assert subject.decide(_bash_event(cmd), runner=git) is None


# ---------------------------------------------------------------------------
# signed-only push -> allow ; unsigned commit -> deny
# ---------------------------------------------------------------------------


def test_allows_signed_only_push(remote: None) -> None:
    git = _FakeGit(
        rev_parse={"HEAD": _LOCAL_SHA, "refs/remotes/origin/feat/x": _REMOTE_SHA},
        rev_list=[_SIGNED, _SIGNED],
        unsigned=set(),
    )
    assert subject.decide(_bash_event("git push origin feat/x"), runner=git) is None


def test_denies_push_with_unsigned_commit(remote: None) -> None:
    git = _FakeGit(
        rev_parse={"HEAD": _LOCAL_SHA, "refs/remotes/origin/feat/x": _REMOTE_SHA},
        rev_list=[_SIGNED, _UNSIGNED],
        unsigned={_UNSIGNED},
    )
    result = subject.decide(_bash_event("git push origin feat/x"), runner=git)
    assert result is not None
    reason = result["hookSpecificOutput"]["permissionDecisionReason"]
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert _UNSIGNED[:12] in reason
    assert "#2138" in reason


def test_denies_push_u_with_unsigned_commit(remote: None) -> None:
    git = _FakeGit(
        rev_parse={"HEAD": _LOCAL_SHA, "refs/remotes/origin/feat/x": _REMOTE_SHA},
        rev_list=[_UNSIGNED],
        unsigned={_UNSIGNED},
    )
    result = subject.decide(_bash_event("git push -u origin feat/x"), runner=git)
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


# ---------------------------------------------------------------------------
# new branch (all-zeros remote sha) -> rev-list --not --remotes
# ---------------------------------------------------------------------------


def test_new_branch_scans_all_commits_not_on_remote(remote: None) -> None:
    # The remote-tracking ref does not resolve (new branch): the gate must scan
    # via ``rev-list <local> --not --remotes`` and still catch an unsigned one.
    git = _FakeGit(
        rev_parse={"HEAD": _LOCAL_SHA},  # remote ref absent -> unresolved
        rev_list=[_SIGNED, _UNSIGNED],
        unsigned={_UNSIGNED},
    )
    result = subject.decide(_bash_event("git push origin feat/new"), runner=git)
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    rev_list_calls = [c for c in git.calls if c[0] == "rev-list"]
    assert rev_list_calls == [["rev-list", _LOCAL_SHA, "--not", "--remotes"]]


def test_existing_branch_uses_range(remote: None) -> None:
    git = _FakeGit(
        rev_parse={"HEAD": _LOCAL_SHA, "refs/remotes/origin/feat/x": _REMOTE_SHA},
        rev_list=[_SIGNED],
        unsigned=set(),
    )
    subject.decide(_bash_event("git push origin feat/x"), runner=git)
    rev_list_calls = [c for c in git.calls if c[0] == "rev-list"]
    assert rev_list_calls == [["rev-list", f"{_REMOTE_SHA}..{_LOCAL_SHA}"]]


def test_all_zeros_remote_sha_treated_as_new_branch(remote: None) -> None:
    git = _FakeGit(
        rev_parse={"HEAD": _LOCAL_SHA, "refs/remotes/origin/feat/x": _ALL_ZEROS},
        rev_list=[_SIGNED],
        unsigned=set(),
    )
    subject.decide(_bash_event("git push origin feat/x"), runner=git)
    rev_list_calls = [c for c in git.calls if c[0] == "rev-list"]
    assert rev_list_calls == [["rev-list", _LOCAL_SHA, "--not", "--remotes"]]


# ---------------------------------------------------------------------------
# fail-open paths
# ---------------------------------------------------------------------------


def test_passthrough_no_explicit_refspec(remote: None) -> None:
    git = _FakeGit(unsigned={_UNSIGNED})
    assert subject.decide(_bash_event("git push"), runner=git) is None
    assert subject.decide(_bash_event("git push origin"), runner=git) is None


def test_passthrough_local_sha_unresolved(remote: None) -> None:
    git = _FakeGit(rev_parse={}, rev_list=[_UNSIGNED], unsigned={_UNSIGNED})
    assert subject.decide(_bash_event("git push origin feat/x"), runner=git) is None


def test_passthrough_empty_range(remote: None) -> None:
    git = _FakeGit(
        rev_parse={"HEAD": _LOCAL_SHA, "refs/remotes/origin/feat/x": _REMOTE_SHA},
        rev_list=[],
        unsigned={_UNSIGNED},
    )
    assert subject.decide(_bash_event("git push origin feat/x"), runner=git) is None


def test_passthrough_on_rev_list_error(remote: None) -> None:
    git = _FakeGit(
        rev_parse={"HEAD": _LOCAL_SHA, "refs/remotes/origin/feat/x": _REMOTE_SHA},
        rev_list=[_UNSIGNED],
        unsigned={_UNSIGNED},
        raise_on="rev-list",
    )
    assert subject.decide(_bash_event("git push origin feat/x"), runner=git) is None


def test_passthrough_on_rev_list_nonzero(remote: None) -> None:
    git = _FakeGit(
        rev_parse={"HEAD": _LOCAL_SHA, "refs/remotes/origin/feat/x": _REMOTE_SHA},
        rev_list_rc=128,
        unsigned={_UNSIGNED},
    )
    assert subject.decide(_bash_event("git push origin feat/x"), runner=git) is None


def test_passthrough_on_rev_parse_error(remote: None) -> None:
    git = _FakeGit(
        rev_parse={"HEAD": _LOCAL_SHA, "refs/remotes/origin/feat/x": _REMOTE_SHA},
        rev_list=[_UNSIGNED],
        unsigned={_UNSIGNED},
        raise_on="rev-parse",
    )
    assert subject.decide(_bash_event("git push origin feat/x"), runner=git) is None


def test_cat_file_error_fails_open(remote: None) -> None:
    # A cat-file subprocess error must not deny (cannot evaluate -> open).
    git = _FakeGit(
        rev_parse={"HEAD": _LOCAL_SHA, "refs/remotes/origin/feat/x": _REMOTE_SHA},
        rev_list=[_UNSIGNED],
        unsigned={_UNSIGNED},
        raise_on="cat-file",
    )
    assert subject.decide(_bash_event("git push origin feat/x"), runner=git) is None


def test_rtk_rewritten_push_is_checked(remote: None) -> None:
    git = _FakeGit(
        rev_parse={"HEAD": _LOCAL_SHA, "refs/remotes/origin/feat/x": _REMOTE_SHA},
        rev_list=[_UNSIGNED],
        unsigned={_UNSIGNED},
    )
    result = subject.decide(_bash_event("rtk git push origin feat/x"), runner=git)
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


# ---------------------------------------------------------------------------
# _parse_push_target() unit tests
# ---------------------------------------------------------------------------


class TestParsePushTarget:
    def test_simple_push(self) -> None:
        assert subject._parse_push_target("git push origin feat/x") == ("origin", "HEAD", "feat/x")

    def test_u_flag(self) -> None:
        assert subject._parse_push_target("git push -u origin feat/x") == ("origin", "HEAD", "feat/x")

    def test_colon_refspec(self) -> None:
        assert subject._parse_push_target("git push origin a:b") == ("origin", "a", "b")

    def test_head_colon_refspec(self) -> None:
        assert subject._parse_push_target("git push origin HEAD:b") == ("origin", "HEAD", "b")

    def test_force_prefix_stripped(self) -> None:
        assert subject._parse_push_target("git push origin +feat/x") == ("origin", "HEAD", "feat/x")

    def test_no_refspec_returns_none(self) -> None:
        assert subject._parse_push_target("git push") is None
        assert subject._parse_push_target("git push origin") is None

    def test_no_push_returns_none(self) -> None:
        assert subject._parse_push_target("echo hello") is None

    def test_malformed_quote_returns_none(self) -> None:
        assert subject._parse_push_target('git push origin "feat/x') is None

    def test_empty_remote_side_returns_none(self) -> None:
        assert subject._parse_push_target("git push origin HEAD:") is None

    def test_double_dash_end_of_options(self) -> None:
        assert subject._parse_push_target("git push origin -- feat/x") == ("origin", "HEAD", "feat/x")  # dh-ok

    def test_flag_with_value_consumes_token(self) -> None:
        assert subject._parse_push_target("git push -o ci=skip origin feat/x") == ("origin", "HEAD", "feat/x")

    def test_unknown_flag_skipped(self) -> None:
        assert subject._parse_push_target("git push --weird origin feat/x") == ("origin", "HEAD", "feat/x")

    def test_stops_at_shell_operator(self) -> None:
        assert subject._parse_push_target("git push origin feat/x && echo ok") == ("origin", "HEAD", "feat/x")


# ---------------------------------------------------------------------------
# _is_unsigned(): header-presence semantics (the verify-commit false-positive
# fix: a signed-but-locally-unverifiable commit must read as signed)
# ---------------------------------------------------------------------------


class TestIsUnsigned:
    def _runner(self, stdout: str, returncode: int = 0):
        def run(_args: list[str]) -> subprocess.CompletedProcess[str]:
            return _cp(returncode=returncode, stdout=stdout)

        return run

    def test_signed_header_present_reads_signed(self) -> None:
        body = (
            "tree 0\nauthor a <a@b> 0 +0000\ncommitter a <a@b> 0 +0000\n"
            "gpgsig -----BEGIN SSH SIGNATURE-----\n A\n -----END SSH SIGNATURE-----\n"
            "\nmsg\n"
        )
        assert subject._is_unsigned(self._runner(body), _SIGNED) is False

    def test_sha256_signature_header_reads_signed(self) -> None:
        body = "tree 0\ncommitter a <a@b> 0 +0000\ngpgsig-sha256 sig\n\nmsg\n"
        assert subject._is_unsigned(self._runner(body), _SIGNED) is False

    def test_no_header_reads_unsigned(self) -> None:
        body = "tree 0\nauthor a <a@b> 0 +0000\ncommitter a <a@b> 0 +0000\n\nmsg\n"
        assert subject._is_unsigned(self._runner(body), _UNSIGNED) is True

    def test_message_mention_does_not_mask_unsigned(self) -> None:
        # "gpgsig" only in the message body (after the blank line) is not a header.
        body = "tree 0\ncommitter a <a@b> 0 +0000\n\ngpgsig in the message\n"
        assert subject._is_unsigned(self._runner(body), _UNSIGNED) is True

    def test_nonzero_exit_fails_open(self) -> None:
        assert subject._is_unsigned(self._runner("", returncode=128), _UNSIGNED) is False


# ---------------------------------------------------------------------------
# main() entry point (stdin/stdout boundary)
# ---------------------------------------------------------------------------


def _run_main(payload: object, monkeypatch: pytest.MonkeyPatch) -> str:
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
    out: list[str] = []
    monkeypatch.setattr(
        "sys.stdout", type("FakeOut", (), {"write": lambda self, s: out.append(s)})()
    )
    rc = subject.main()
    assert rc == 0
    return "".join(out)


def test_main_silent_for_allowed_push(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    monkeypatch.delenv("CODEX_CODE_REMOTE", raising=False)
    assert _run_main(_bash_event("git push origin feat/x"), monkeypatch) == ""


def test_main_handles_malformed_json(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))
    assert subject.main() == 0
    assert "malformed" in capsys.readouterr().err


def test_default_runner_returns_completed_process() -> None:
    # The production runner shells out to real git; a harmless read confirms it
    # returns a CompletedProcess (covers the default-runner seam).
    result = subject._default_runner(["rev-parse", "--git-dir"])
    assert isinstance(result, subprocess.CompletedProcess)
    assert result.returncode == 0


def test_main_block_exits_via_runpy(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy

    monkeypatch.setattr("sys.stdin", type("Input", (), {"read": lambda self: ""})())
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("preflight_push_unsigned_commits", run_name="__main__")
    assert exc_info.value.code == 0
