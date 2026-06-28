"""Tests for ``scripts/preflight_signed_commits.py``.

Refs #1959. The pre-push gate inspects ``origin/main..HEAD`` and rejects a push
whose range carries an unsigned commit (the Codex Desktop/GUI push that
``preflight_push_unsigned_commits`` (#2138) cannot see). A commit is unsigned
when its raw object carries no ``gpgsig`` header (the shared
``_commit_signing.is_unsigned`` model). Covered: a signed range passes, an
unsigned commit in range fails loud, the anchored ``# unsigned-ack`` opt-in
passes (and an unanchored substring does NOT, the #1962 ACK bug), and an
empty/unresolvable range is a pass/skip.
"""

from __future__ import annotations

import argparse
import subprocess

import preflight_signed_commits as subject
import pytest

pytestmark = pytest.mark.shard_preflight

_SIGNED = "1111111111111111111111111111111111111111"
_UNSIGNED = "2222222222222222222222222222222222222222"


def _cp(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["git"], returncode=returncode, stdout=stdout, stderr="")


class _FakeGit:
    """A canned ``git`` runner keyed on the subcommand.

    ``rev_list`` is the list of shas ``rev-list <base>..HEAD`` returns;
    ``rev_list_rc`` overrides the exit code. ``unsigned`` is the set of shas
    whose ``cat-file commit`` object carries no ``gpgsig`` header.
    """

    def __init__(
        self,
        *,
        rev_list: list[str] | None = None,
        rev_list_rc: int = 0,
        unsigned: set[str] | None = None,
        raise_on: str | None = None,
    ) -> None:
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
        if sub == "rev-list":
            if self.rev_list_rc != 0:
                return _cp(returncode=self.rev_list_rc)
            return _cp(stdout="\n".join(self.rev_list) + "\n")
        if sub == "cat-file":
            sha = args[-1]
            headers = "tree 0\ncommitter a <a@b> 0 +0000\n"
            if sha not in self.unsigned:
                headers += "gpgsig -----BEGIN SSH SIGNATURE-----\n A\n -----END SSH SIGNATURE-----\n"
            return _cp(stdout=headers + "\nmsg\n")
        return _cp()


@pytest.fixture(autouse=True)
def _no_ack(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default every test to no opt-in unless it sets one explicitly."""
    monkeypatch.delenv(subject._ACK_ENV_VAR, raising=False)


def _args(base_ref: str = "origin/main") -> argparse.Namespace:
    return argparse.Namespace(command="verify", repo_root=".", base_ref=base_ref)


# ---------------------------------------------------------------------------
# check_signed_commits(): pass / fail / skip
# ---------------------------------------------------------------------------


def test_signed_range_passes() -> None:
    git = _FakeGit(rev_list=[_SIGNED, _SIGNED], unsigned=set())
    result = subject.check_signed_commits(runner=git, base_ref="origin/main")
    assert result.status == "pass"
    assert result.unsigned == ()


def test_unsigned_commit_in_range_fails() -> None:
    git = _FakeGit(rev_list=[_SIGNED, _UNSIGNED], unsigned={_UNSIGNED})
    result = subject.check_signed_commits(runner=git, base_ref="origin/main")
    assert result.status == "fail"
    assert result.unsigned == (_UNSIGNED,)


def test_empty_range_passes() -> None:
    git = _FakeGit(rev_list=[], unsigned={_UNSIGNED})
    result = subject.check_signed_commits(runner=git, base_ref="origin/main")
    assert result.status == "pass"


def test_unresolvable_base_is_skip() -> None:
    git = _FakeGit(rev_list_rc=128)
    result = subject.check_signed_commits(runner=git, base_ref="origin/nope")
    assert result.status == "skip"


def test_rev_list_error_is_skip() -> None:
    git = _FakeGit(raise_on="rev-list")
    result = subject.check_signed_commits(runner=git, base_ref="origin/main")
    assert result.status == "skip"


# ---------------------------------------------------------------------------
# commits_in_range()
# ---------------------------------------------------------------------------


def test_commits_in_range_strips_blanks() -> None:
    git = _FakeGit(rev_list=[_SIGNED, "", _UNSIGNED])
    assert subject.commits_in_range(git, "origin/main") == [_SIGNED, _UNSIGNED]
    assert git.calls[0] == ["rev-list", "origin/main..HEAD"]


# ---------------------------------------------------------------------------
# ack_present(): anchored marker, never an unanchored substring (#1962 bug)
# ---------------------------------------------------------------------------


def test_ack_present_full_line() -> None:
    assert subject.ack_present({subject._ACK_ENV_VAR: "# unsigned-ack"}) is True


def test_ack_present_marker_on_its_own_line_among_others() -> None:
    assert subject.ack_present({subject._ACK_ENV_VAR: "reviewed\n# unsigned-ack\nok"}) is True


def test_ack_absent_when_unset() -> None:
    assert subject.ack_present({}) is False


def test_ack_substring_does_not_opt_out() -> None:
    # The #1962 ACK bug: a marker embedded in a larger token must NOT opt out.
    assert subject.ack_present({subject._ACK_ENV_VAR: "x # unsigned-ack y"}) is False
    assert subject.ack_present({subject._ACK_ENV_VAR: "# unsigned-ack-not-really"}) is False


def test_ack_present_tolerates_trailing_cr() -> None:
    # A CRLF-tainted env value must still opt out (the marker line is
    # "# unsigned-ack\r"); the anchored regex tolerates the trailing CR.
    assert subject.ack_present({subject._ACK_ENV_VAR: "# unsigned-ack\r\nrest"}) is True
    assert subject.ack_present({subject._ACK_ENV_VAR: "# unsigned-ack\r"}) is True


# ---------------------------------------------------------------------------
# cmd_verify(): exit codes
# ---------------------------------------------------------------------------


def test_cmd_verify_pass_returns_zero() -> None:
    git = _FakeGit(rev_list=[_SIGNED], unsigned=set())
    assert subject.cmd_verify(_args(), runner=git) == 0


def test_cmd_verify_fail_returns_one_and_lists(capsys: pytest.CaptureFixture[str]) -> None:
    git = _FakeGit(rev_list=[_UNSIGNED], unsigned={_UNSIGNED})
    assert subject.cmd_verify(_args(), runner=git) == 1
    err = capsys.readouterr().err
    assert "UNSIGNED" in err
    assert _UNSIGNED in err


def test_cmd_verify_skip_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    git = _FakeGit(rev_list_rc=128)
    assert subject.cmd_verify(_args(), runner=git) == 0
    assert "SKIP" in capsys.readouterr().err


def test_cmd_verify_ack_bypasses_unsigned_loudly(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv(subject._ACK_ENV_VAR, "# unsigned-ack")
    git = _FakeGit(rev_list=[_UNSIGNED], unsigned={_UNSIGNED})
    # The opt-in is consulted only after a real unsigned commit is found (so git
    # IS queried), and the bypass is logged as a loud ::warning:: naming the sha.
    assert subject.cmd_verify(_args(), runner=git) == 0
    assert git.calls  # the range was actually resolved before the opt-in applied
    err = capsys.readouterr().err
    assert "::warning::" in err
    assert _UNSIGNED in err


def test_cmd_verify_ack_does_not_bypass_a_clean_range(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # With no unsigned commit, the opt-in is irrelevant: a normal pass, no warning.
    monkeypatch.setenv(subject._ACK_ENV_VAR, "# unsigned-ack")
    git = _FakeGit(rev_list=[_SIGNED], unsigned=set())
    assert subject.cmd_verify(_args(), runner=git) == 0
    assert "::warning::" not in capsys.readouterr().err


# ---------------------------------------------------------------------------
# main() / parser
# ---------------------------------------------------------------------------


def test_main_verify_runs_against_repo() -> None:
    # The default runner path (no injected runner) shells out to real git; an
    # unresolvable base ref is a skip (exit 0), covering _make_runner's closure.
    assert subject.main(["verify", "--base-ref", "refs/nope/missing"]) == 0


def test_main_requires_subcommand() -> None:
    with pytest.raises(SystemExit):
        subject.main([])


def test_main_block_exits_via_runpy(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy

    monkeypatch.setattr("sys.argv", ["preflight_signed_commits.py", "verify", "--base-ref", "refs/nope/x"])
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("preflight_signed_commits", run_name="__main__")
    assert exc_info.value.code == 0
