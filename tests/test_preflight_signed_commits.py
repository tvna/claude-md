"""Tests for ``scripts/preflight_signed_commits.py``.

Refs #1959. The pre-push gate inspects ``origin/main..HEAD`` and rejects a push
whose range carries an unsigned commit (the Codex Desktop/GUI push that
``preflight_push_unsigned_commits`` (#2138) cannot see). A commit is unsigned
when its raw object carries no ``gpgsig`` header (the shared
``_commit_signing.is_unsigned`` model). Covered: a signed range passes, an
unsigned commit in range fails loud, the anchored ``# unsigned-ack`` opt-in
passes (and an unanchored substring does NOT, the #1962 ACK bug), and an
empty/unresolvable range is a pass/skip.

Refs #2162. The gate now inspects the refs actually being pushed when the
pre-push hook bridges them through ``PREFLIGHT_PUSH_REFS`` /
``PREFLIGHT_PUSH_REMOTE``: a push of a non-HEAD branch with an unsigned commit
is rejected, a tag / non-HEAD push is NOT blocked by unsigned commits reachable
only from HEAD, new-branch (all-zeros remote oid) and delete (all-zeros local
oid) refspecs behave, and an absent payload falls back to ``origin/main..HEAD``.
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

    ``rev_list`` is the default sha list any ``rev-list`` call returns;
    ``rev_list_map`` overrides it per local sha (the part after ``..`` for a
    range, or the sole sha for a new-branch scan) so distinct pushed refs can
    ship distinct commits. ``rev_list_rc`` overrides the exit code. ``unsigned``
    is the set of shas whose ``cat-file commit`` object carries no ``gpgsig``
    header.
    """

    def __init__(
        self,
        *,
        rev_list: list[str] | None = None,
        rev_list_map: dict[str, list[str]] | None = None,
        rev_list_rc: int = 0,
        unsigned: set[str] | None = None,
        remotes: dict[str, str] | None = None,
        raise_on: str | None = None,
    ) -> None:
        self.rev_list = rev_list if rev_list is not None else []
        self.rev_list_map = rev_list_map or {}
        self.rev_list_rc = rev_list_rc
        self.unsigned = unsigned or set()
        # Configured remotes (name -> url) for `git remote -v`, consulted by
        # _git.resolve_remote_name on the new-branch path. Defaults to origin so
        # the --remotes=origin expectations hold (#2162).
        self.remotes = remotes if remotes is not None else {"origin": "https://example.test/repo.git"}
        self.raise_on = raise_on
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        sub = args[0]
        if self.raise_on is not None and sub == self.raise_on:
            raise OSError("boom")
        if sub == "remote":
            lines = [f"{name}\t{url} (fetch)\n{name}\t{url} (push)" for name, url in self.remotes.items()]
            return _cp(stdout="\n".join(lines) + "\n")
        if sub == "rev-list":
            if self.rev_list_rc != 0:
                return _cp(returncode=self.rev_list_rc)
            key = args[1].rsplit("..", 1)[-1]
            commits = self.rev_list_map.get(key, self.rev_list)
            return _cp(stdout="\n".join(commits) + "\n")
        if sub == "cat-file":
            sha = args[-1]
            headers = "tree 0\ncommitter a <a@b> 0 +0000\n"
            if sha not in self.unsigned:
                headers += "gpgsig -----BEGIN SSH SIGNATURE-----\n A\n -----END SSH SIGNATURE-----\n"
            return _cp(stdout=headers + "\nmsg\n")
        return _cp()


@pytest.fixture(autouse=True)
def _no_ack(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default every test to no opt-in and no pushed-ref payload.

    Clearing the pushed-ref env vars keeps the fixed-range cmd_verify tests on
    the origin/main..HEAD fallback regardless of an ambient pre-push environment.
    """
    monkeypatch.delenv(subject._ACK_ENV_VAR, raising=False)
    monkeypatch.delenv(subject._PUSH_REFS_ENV_VAR, raising=False)
    monkeypatch.delenv(subject._PUSH_REMOTE_ENV_VAR, raising=False)


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
# parse_push_refs() / read_push_refs(): pre-push stdin payload
# ---------------------------------------------------------------------------

_OTHER_TIP = "3333333333333333333333333333333333333333"
_REMOTE_OID = "4444444444444444444444444444444444444444"
_ZEROS = "0" * 40


def test_parse_push_refs_reads_four_fields() -> None:
    payload = f"refs/heads/feat {_OTHER_TIP} refs/heads/feat {_REMOTE_OID}\n"
    refs = subject.parse_push_refs(payload)
    assert refs == [subject.PushRef("refs/heads/feat", _OTHER_TIP, "refs/heads/feat", _REMOTE_OID)]


def test_parse_push_refs_skips_blank_and_malformed() -> None:
    payload = f"\nnot enough fields\nrefs/heads/a {_OTHER_TIP} refs/heads/a {_REMOTE_OID}\n   \n"
    refs = subject.parse_push_refs(payload)
    assert [r.local_ref for r in refs] == ["refs/heads/a"]


def test_parse_push_refs_delete_line() -> None:
    # A deletion line is "(delete) <zeros> <remote-ref> <remote-oid>": four fields.
    refs = subject.parse_push_refs(f"(delete) {_ZEROS} refs/heads/old {_REMOTE_OID}")
    assert refs == [subject.PushRef("(delete)", _ZEROS, "refs/heads/old", _REMOTE_OID)]


def test_read_push_refs_defaults_remote_to_origin() -> None:
    env = {subject._PUSH_REFS_ENV_VAR: f"refs/heads/a {_OTHER_TIP} refs/heads/a {_REMOTE_OID}"}
    refs, remote = subject.read_push_refs(env)
    assert len(refs) == 1
    assert remote == "origin"


def test_read_push_refs_uses_named_remote() -> None:
    env = {
        subject._PUSH_REFS_ENV_VAR: f"refs/heads/a {_OTHER_TIP} refs/heads/a {_REMOTE_OID}",
        subject._PUSH_REMOTE_ENV_VAR: "upstream",
    }
    _refs, remote = subject.read_push_refs(env)
    assert remote == "upstream"


def test_read_push_refs_empty_when_unset() -> None:
    refs, _remote = subject.read_push_refs({})
    assert refs == []


# ---------------------------------------------------------------------------
# check_pushed_refs(): inspect the commits each pushed ref ships
# ---------------------------------------------------------------------------


def _ref(local_oid: str, remote_oid: str, name: str = "refs/heads/feat") -> subject.PushRef:
    return subject.PushRef(name, local_oid, name, remote_oid)


def test_pushed_existing_branch_uses_range() -> None:
    git = _FakeGit(rev_list_map={_OTHER_TIP: [_SIGNED]}, unsigned=set())
    result = subject.check_pushed_refs(
        runner=git, refs=[_ref(_OTHER_TIP, _REMOTE_OID)], remote="origin"
    )
    assert result.status == "pass"
    rev_list_calls = [c for c in git.calls if c[0] == "rev-list"]
    assert rev_list_calls == [["rev-list", f"{_REMOTE_OID}..{_OTHER_TIP}"]]


def test_pushed_unsigned_commit_fails() -> None:
    git = _FakeGit(rev_list_map={_OTHER_TIP: [_SIGNED, _UNSIGNED]}, unsigned={_UNSIGNED})
    result = subject.check_pushed_refs(
        runner=git, refs=[_ref(_OTHER_TIP, _REMOTE_OID)], remote="origin"
    )
    assert result.status == "fail"
    assert result.unsigned == (_UNSIGNED,)


def test_pushed_new_branch_scopes_to_remote() -> None:
    git = _FakeGit(rev_list_map={_OTHER_TIP: [_UNSIGNED]}, unsigned={_UNSIGNED})
    result = subject.check_pushed_refs(
        runner=git, refs=[_ref(_OTHER_TIP, _ZEROS)], remote="origin"
    )
    assert result.status == "fail"
    rev_list_calls = [c for c in git.calls if c[0] == "rev-list"]
    assert rev_list_calls == [["rev-list", _OTHER_TIP, "--not", "--remotes=origin"]]


def test_pushed_new_branch_url_remote_maps_to_name() -> None:
    # A direct-URL push passes the URL as the remote; it must map back to the
    # configured remote name, not scope --remotes to the URL (#2162).
    git = _FakeGit(
        rev_list_map={_OTHER_TIP: [_UNSIGNED]},
        unsigned={_UNSIGNED},
        remotes={"origin": "https://example.test/repo.git"},
    )
    result = subject.check_pushed_refs(
        runner=git, refs=[_ref(_OTHER_TIP, _ZEROS)], remote="https://example.test/repo.git"
    )
    assert result.status == "fail"
    rev_list_calls = [c for c in git.calls if c[0] == "rev-list"]
    assert rev_list_calls == [["rev-list", _OTHER_TIP, "--not", "--remotes=origin"]]


def test_pushed_new_branch_unknown_url_scopes_to_all_remotes() -> None:
    # A URL matching no configured remote falls back to all remote-tracking refs,
    # never a bogus --remotes=<url> that would scan the whole history (#2162).
    git = _FakeGit(
        rev_list_map={_OTHER_TIP: [_SIGNED]},
        unsigned=set(),
        remotes={"origin": "https://example.test/repo.git"},
    )
    subject.check_pushed_refs(
        runner=git, refs=[_ref(_OTHER_TIP, _ZEROS)], remote="https://unconfigured/x.git"
    )
    rev_list_calls = [c for c in git.calls if c[0] == "rev-list"]
    assert rev_list_calls == [["rev-list", _OTHER_TIP, "--not", "--remotes"]]


def test_pushed_delete_refspec_ships_nothing() -> None:
    git = _FakeGit(rev_list=[_UNSIGNED], unsigned={_UNSIGNED})
    result = subject.check_pushed_refs(
        runner=git, refs=[_ref(_ZEROS, _REMOTE_OID)], remote="origin"
    )
    assert result.status == "pass"
    assert [c for c in git.calls if c[0] == "rev-list"] == []


def test_pushed_dedups_commits_across_refs() -> None:
    # Two refs ship the same sha; it is inspected once.
    git = _FakeGit(rev_list_map={_OTHER_TIP: [_UNSIGNED]}, unsigned={_UNSIGNED})
    refs = [
        _ref(_OTHER_TIP, _REMOTE_OID, "refs/heads/a"),
        _ref(_OTHER_TIP, _REMOTE_OID, "refs/heads/b"),
    ]
    result = subject.check_pushed_refs(runner=git, refs=refs, remote="origin")
    assert result.unsigned == (_UNSIGNED,)
    cat_file_calls = [c for c in git.calls if c[0] == "cat-file"]
    assert len(cat_file_calls) == 1


def test_pushed_all_undeterminable_is_skip() -> None:
    git = _FakeGit(rev_list_rc=128)
    result = subject.check_pushed_refs(
        runner=git, refs=[_ref(_OTHER_TIP, _REMOTE_OID)], remote="origin"
    )
    assert result.status == "skip"


def test_pushed_undeterminable_ref_does_not_block_signed_one() -> None:
    # One ref's range cannot resolve (skipped, fail-open for it); the other ships
    # only signed commits, so the overall result is a pass.
    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        if args[0] == "rev-list" and args[1].endswith(_OTHER_TIP):
            return _cp(returncode=128)  # first ref undeterminable
        if args[0] == "rev-list":
            return _cp(stdout=_SIGNED + "\n")
        if args[0] == "cat-file":
            return _cp(stdout="tree 0\ngpgsig x\n\nmsg\n")
        return _cp()

    refs = [
        _ref(_OTHER_TIP, _REMOTE_OID, "refs/heads/a"),
        _ref(_REMOTE_OID, _OTHER_TIP, "refs/heads/b"),
    ]
    result = subject.check_pushed_refs(runner=runner, refs=refs, remote="origin")
    assert result.status == "pass"


# ---------------------------------------------------------------------------
# cmd_verify(): pushed-ref payload vs origin/main..HEAD fallback (#2162)
# ---------------------------------------------------------------------------


def test_cmd_verify_inspects_pushed_branch_not_head(monkeypatch: pytest.MonkeyPatch) -> None:
    # HEAD is on a signed branch (the fallback range would pass), but a push of
    # other-branch ships an unsigned commit; the gate must inspect the pushed ref.
    monkeypatch.setenv(
        subject._PUSH_REFS_ENV_VAR,
        f"refs/heads/other {_OTHER_TIP} refs/heads/other {_REMOTE_OID}",
    )
    git = _FakeGit(rev_list=[_SIGNED], rev_list_map={_OTHER_TIP: [_UNSIGNED]}, unsigned={_UNSIGNED})
    assert subject.cmd_verify(_args(), runner=git) == 1


def test_cmd_verify_tag_push_not_blocked_by_head_unsigned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A non-HEAD ref push (a tag) ships only signed commits; an unsigned commit
    # reachable only from HEAD (the fallback range) must NOT block it.
    monkeypatch.setenv(
        subject._PUSH_REFS_ENV_VAR,
        f"refs/tags/v1 {_OTHER_TIP} refs/tags/v1 {_REMOTE_OID}",
    )
    git = _FakeGit(rev_list=[_UNSIGNED], rev_list_map={_OTHER_TIP: [_SIGNED]}, unsigned={_UNSIGNED})
    assert subject.cmd_verify(_args(), runner=git) == 0


def test_cmd_verify_pushed_delete_is_pass(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(
        subject._PUSH_REFS_ENV_VAR,
        f"(delete) {_ZEROS} refs/heads/old {_REMOTE_OID}",
    )
    git = _FakeGit(rev_list=[_UNSIGNED], unsigned={_UNSIGNED})
    assert subject.cmd_verify(_args(), runner=git) == 0


def test_cmd_verify_falls_back_to_head_range_without_payload() -> None:
    # No PREFLIGHT_PUSH_REFS (cleared by the autouse fixture): the origin/main..
    # HEAD fallback runs, preserving the manual-invocation behaviour.
    git = _FakeGit(rev_list=[_UNSIGNED], unsigned={_UNSIGNED})
    assert subject.cmd_verify(_args(), runner=git) == 1
    assert git.calls[0] == ["rev-list", "origin/main..HEAD"]


def test_cmd_verify_pushed_ack_bypasses_loudly(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # The session-scoped opt-in still applies to the pushed-ref path.
    monkeypatch.setenv(
        subject._PUSH_REFS_ENV_VAR,
        f"refs/heads/other {_OTHER_TIP} refs/heads/other {_REMOTE_OID}",
    )
    monkeypatch.setenv(subject._ACK_ENV_VAR, "# unsigned-ack")
    git = _FakeGit(rev_list_map={_OTHER_TIP: [_UNSIGNED]}, unsigned={_UNSIGNED})
    assert subject.cmd_verify(_args(), runner=git) == 0
    assert "::warning::" in capsys.readouterr().err


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
