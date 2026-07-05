"""Tests for ``scripts/preflight_coauthor_trailer.py``.

Refs #2307, #2302. The pre-push gate inspects ``origin/main..HEAD`` and
rejects a commit whose ``Co-authored-by:``/``Co-Authored-By:`` trailer names
the same identity (email, case-insensitive) as the commit's own author; the
redundant footer that squash-merge duplicated on PR #2302. Covered: a clean
range passes, a redundant self-trailer fails loud, a legitimate
different-author trailer is allowed, a duplicated-across-commits trailer that
is still self-redundant on each commit fails, an empty/unresolvable range is
a pass/skip, and the CLI exit codes (0 / 1 / 64).
"""

from __future__ import annotations

import argparse
import subprocess

import preflight_coauthor_trailer as subject
import pytest

pytestmark = pytest.mark.shard_preflight

_SHA_A = "1111111111111111111111111111111111111111"
_SHA_B = "2222222222222222222222222222222222222222"

_CLAUDE_EMAIL = "noreply@anthropic.com"
_HUMAN_EMAIL = "dev@example.com"

_SELF_REDUNDANT_BODY = (
    f"fix: do the thing\n\nCo-Authored-By: Claude {_CLAUDE_EMAIL}\n"
)
_LEGIT_COAUTHOR_BODY = f"fix: pair on the thing\n\nCo-authored-by: Jane Dev <{_HUMAN_EMAIL}>\n"
_PLAIN_BODY = "fix: do the thing\n\nNo trailer here.\n"


def _cp(returncode: int = 0, stdout: str = "") -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(args=["git"], returncode=returncode, stdout=stdout, stderr="")


class _FakeGit:
    """A canned ``git`` runner keyed on the subcommand.

    ``rev_list`` is the sha list any ``rev-list`` call returns. ``commits``
    maps a sha to ``(author_email, body)``; ``git log -1 --format=...`` reads
    from it. ``rev_list_rc`` overrides the rev-list exit code so an
    unresolvable range can be simulated. ``raise_on`` triggers an OSError for
    the named subcommand, simulating a git/subprocess failure.
    """

    def __init__(
        self,
        *,
        rev_list: list[str] | None = None,
        rev_list_map: dict[str, list[str]] | None = None,
        commits: dict[str, tuple[str, str]] | None = None,
        rev_list_rc: int = 0,
        raise_on: str | None = None,
    ) -> None:
        self.rev_list = rev_list if rev_list is not None else []
        self.rev_list_map = rev_list_map or {}
        self.commits = commits or {}
        self.rev_list_rc = rev_list_rc
        self.raise_on = raise_on
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        self.calls.append(args)
        sub = args[0]
        if self.raise_on is not None and sub == self.raise_on:
            raise OSError("boom")
        if sub == "remote":
            return _cp(
                stdout="origin\thttps://example.test/repo.git (fetch)\n"
                "origin\thttps://example.test/repo.git (push)\n"
            )
        if sub == "rev-list":
            if self.rev_list_rc != 0:
                return _cp(returncode=self.rev_list_rc)
            if self.rev_list_map:
                key = args[1].rsplit("..", 1)[-1]
                commits = self.rev_list_map.get(key, [])
                return _cp(stdout="\n".join(commits) + "\n")
            return _cp(stdout="\n".join(self.rev_list) + "\n")
        if sub == "log":
            sha = args[-1]
            if sha not in self.commits:
                return _cp(returncode=128)
            email, body = self.commits[sha]
            return _cp(stdout=f"{email}{subject._FIELD_SEP}{body}")
        return _cp()


@pytest.fixture(autouse=True)
def _no_pushed_refs(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default every test to no pushed-ref payload (the base-ref fallback)."""
    monkeypatch.delenv("PREFLIGHT_PUSH_REFS", raising=False)
    monkeypatch.delenv("PREFLIGHT_PUSH_REMOTE", raising=False)


def _args(base_ref: str = "origin/main") -> argparse.Namespace:
    return argparse.Namespace(command="verify", repo_root=".", base_ref=base_ref)


_OTHER_TIP = "3333333333333333333333333333333333333333"
_REMOTE_OID = "4444444444444444444444444444444444444444"
_ZEROS = "0" * 40


# ---------------------------------------------------------------------------
# check_coauthor_trailers(): pass / fail / skip
# ---------------------------------------------------------------------------


def test_clean_range_passes() -> None:
    git = _FakeGit(
        rev_list=[_SHA_A],
        commits={_SHA_A: (_CLAUDE_EMAIL, _PLAIN_BODY)},
    )
    result = subject.check_coauthor_trailers(runner=git, base_ref="origin/main")
    assert result.status == "pass"
    assert result.violations == ()


def test_self_redundant_trailer_fails() -> None:
    git = _FakeGit(
        rev_list=[_SHA_A],
        commits={_SHA_A: (_CLAUDE_EMAIL, _SELF_REDUNDANT_BODY)},
    )
    result = subject.check_coauthor_trailers(runner=git, base_ref="origin/main")
    assert result.status == "fail"
    assert len(result.violations) == 1
    assert result.violations[0].sha == _SHA_A
    assert result.violations[0].trailer_email == _CLAUDE_EMAIL


def test_self_redundant_trailer_matches_case_insensitively() -> None:
    git = _FakeGit(
        rev_list=[_SHA_A],
        commits={_SHA_A: (_CLAUDE_EMAIL.upper(), _SELF_REDUNDANT_BODY)},
    )
    result = subject.check_coauthor_trailers(runner=git, base_ref="origin/main")
    assert result.status == "fail"


def test_legitimate_different_author_coauthor_passes() -> None:
    git = _FakeGit(
        rev_list=[_SHA_A],
        commits={_SHA_A: (_CLAUDE_EMAIL, _LEGIT_COAUTHOR_BODY)},
    )
    result = subject.check_coauthor_trailers(runner=git, base_ref="origin/main")
    assert result.status == "pass"


def test_duplicated_across_commits_each_self_redundant_fails() -> None:
    # Two commits, each independently carrying a self-redundant trailer (the
    # exact PR #2302 shape): both are reported.
    git = _FakeGit(
        rev_list=[_SHA_A, _SHA_B],
        commits={
            _SHA_A: (_CLAUDE_EMAIL, _SELF_REDUNDANT_BODY),
            _SHA_B: (_CLAUDE_EMAIL, _SELF_REDUNDANT_BODY),
        },
    )
    result = subject.check_coauthor_trailers(runner=git, base_ref="origin/main")
    assert result.status == "fail"
    assert len(result.violations) == 2
    assert {v.sha for v in result.violations} == {_SHA_A, _SHA_B}


def test_empty_range_passes() -> None:
    git = _FakeGit(rev_list=[])
    result = subject.check_coauthor_trailers(runner=git, base_ref="origin/main")
    assert result.status == "pass"


def test_unresolvable_base_is_skip() -> None:
    git = _FakeGit(rev_list_rc=128)
    result = subject.check_coauthor_trailers(runner=git, base_ref="origin/nope")
    assert result.status == "skip"


def test_rev_list_error_is_skip() -> None:
    git = _FakeGit(raise_on="rev-list")
    result = subject.check_coauthor_trailers(runner=git, base_ref="origin/main")
    assert result.status == "skip"


def test_unreadable_commit_is_skipped_not_a_violation() -> None:
    # log raising is a fail-open per-commit skip, not a false positive.
    git = _FakeGit(rev_list=[_SHA_A], raise_on="log")
    result = subject.check_coauthor_trailers(runner=git, base_ref="origin/main")
    assert result.status == "pass"


# ---------------------------------------------------------------------------
# find_redundant_trailers(): trailer parsing edge cases
# ---------------------------------------------------------------------------


def test_trailer_key_matched_case_insensitively() -> None:
    body = f"fix: x\n\nco-authored-by: Claude <{_CLAUDE_EMAIL}>\n"
    git = _FakeGit(commits={_SHA_A: (_CLAUDE_EMAIL, body)})
    violations = subject.find_redundant_trailers(git, [_SHA_A])
    assert len(violations) == 1


def test_mention_in_prose_is_not_a_trailer() -> None:
    body = f"fix: mentions co-authored-by <{_CLAUDE_EMAIL}> in prose, not as a trailer line"
    git = _FakeGit(commits={_SHA_A: (_CLAUDE_EMAIL, body)})
    violations = subject.find_redundant_trailers(git, [_SHA_A])
    assert violations == []


def test_multiple_trailers_only_self_redundant_one_reported() -> None:
    body = (
        f"fix: x\n\nCo-authored-by: Jane Dev <{_HUMAN_EMAIL}>\n"
        f"Co-Authored-By: Claude <{_CLAUDE_EMAIL}>\n"
    )
    git = _FakeGit(commits={_SHA_A: (_CLAUDE_EMAIL, body)})
    violations = subject.find_redundant_trailers(git, [_SHA_A])
    assert len(violations) == 1
    assert violations[0].trailer_email == _CLAUDE_EMAIL


# ---------------------------------------------------------------------------
# check_pushed_refs(): inspect the commits each pushed ref ships (#2333 review)
# ---------------------------------------------------------------------------


def _ref(local_oid: str, remote_oid: str, name: str = "refs/heads/feat") -> subject.PushRef:
    return subject.PushRef(name, local_oid, name, remote_oid)


def test_pushed_existing_branch_uses_range() -> None:
    git = _FakeGit(
        rev_list_map={_OTHER_TIP: [_SHA_A]},
        commits={_SHA_A: (_CLAUDE_EMAIL, _PLAIN_BODY)},
    )
    result = subject.check_pushed_refs(
        runner=git, refs=[_ref(_OTHER_TIP, _REMOTE_OID)], remote="origin"
    )
    assert result.status == "pass"
    rev_list_calls = [c for c in git.calls if c[0] == "rev-list"]
    assert rev_list_calls == [["rev-list", f"{_REMOTE_OID}..{_OTHER_TIP}"]]


def test_pushed_self_redundant_trailer_fails() -> None:
    git = _FakeGit(
        rev_list_map={_OTHER_TIP: [_SHA_A]},
        commits={_SHA_A: (_CLAUDE_EMAIL, _SELF_REDUNDANT_BODY)},
    )
    result = subject.check_pushed_refs(
        runner=git, refs=[_ref(_OTHER_TIP, _REMOTE_OID)], remote="origin"
    )
    assert result.status == "fail"
    assert result.violations[0].sha == _SHA_A


def test_pushed_new_branch_scopes_to_remote() -> None:
    git = _FakeGit(
        rev_list_map={_OTHER_TIP: [_SHA_A]},
        commits={_SHA_A: (_CLAUDE_EMAIL, _PLAIN_BODY)},
    )
    subject.check_pushed_refs(runner=git, refs=[_ref(_OTHER_TIP, _ZEROS)], remote="origin")
    rev_list_calls = [c for c in git.calls if c[0] == "rev-list"]
    assert rev_list_calls == [["rev-list", _OTHER_TIP, "--not", "--remotes=origin"]]


def test_pushed_delete_refspec_ships_nothing() -> None:
    git = _FakeGit(rev_list=[_SHA_A], commits={_SHA_A: (_CLAUDE_EMAIL, _SELF_REDUNDANT_BODY)})
    result = subject.check_pushed_refs(
        runner=git, refs=[_ref(_ZEROS, _REMOTE_OID)], remote="origin"
    )
    assert result.status == "pass"
    assert [c for c in git.calls if c[0] == "rev-list"] == []


def test_pushed_all_undeterminable_is_skip() -> None:
    git = _FakeGit(rev_list_rc=128)
    result = subject.check_pushed_refs(
        runner=git, refs=[_ref(_OTHER_TIP, _REMOTE_OID)], remote="origin"
    )
    assert result.status == "skip"


# ---------------------------------------------------------------------------
# cmd_verify(): pushed-ref payload vs base-ref fallback (#2333 review)
# ---------------------------------------------------------------------------


def test_cmd_verify_inspects_pushed_branch_not_head(monkeypatch: pytest.MonkeyPatch) -> None:
    # HEAD is on a clean branch (the fallback range would pass), but a push of
    # other-branch ships a self-redundant trailer; the gate must inspect the
    # pushed ref, not the fixed origin/main..HEAD range.
    monkeypatch.setenv(
        "PREFLIGHT_PUSH_REFS",
        f"refs/heads/other {_OTHER_TIP} refs/heads/other {_REMOTE_OID}",
    )
    git = _FakeGit(
        rev_list=[_SHA_A],
        rev_list_map={_OTHER_TIP: [_SHA_B]},
        commits={
            _SHA_A: (_CLAUDE_EMAIL, _PLAIN_BODY),
            _SHA_B: (_CLAUDE_EMAIL, _SELF_REDUNDANT_BODY),
        },
    )
    assert subject.cmd_verify(_args(), runner=git) == 1


def test_cmd_verify_tag_push_not_blocked_by_head_redundant_trailer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A non-HEAD ref push (a tag) ships a clean commit; a self-redundant
    # trailer reachable only from HEAD (the fallback range) must NOT block it.
    monkeypatch.setenv(
        "PREFLIGHT_PUSH_REFS",
        f"refs/tags/v1 {_OTHER_TIP} refs/tags/v1 {_REMOTE_OID}",
    )
    git = _FakeGit(
        rev_list=[_SHA_A],
        rev_list_map={_OTHER_TIP: [_SHA_B]},
        commits={
            _SHA_A: (_CLAUDE_EMAIL, _SELF_REDUNDANT_BODY),
            _SHA_B: (_CLAUDE_EMAIL, _PLAIN_BODY),
        },
    )
    assert subject.cmd_verify(_args(), runner=git) == 0


def test_cmd_verify_falls_back_to_head_range_without_payload() -> None:
    # No PREFLIGHT_PUSH_REFS (cleared by the autouse fixture): the origin/main..
    # HEAD fallback runs, preserving the manual-invocation behaviour.
    git = _FakeGit(rev_list=[_SHA_A], commits={_SHA_A: (_CLAUDE_EMAIL, _SELF_REDUNDANT_BODY)})
    assert subject.cmd_verify(_args(), runner=git) == 1
    assert git.calls[0] == ["rev-list", "origin/main..HEAD"]


# ---------------------------------------------------------------------------
# cmd_verify(): exit codes
# ---------------------------------------------------------------------------


def test_cmd_verify_pass_returns_zero() -> None:
    git = _FakeGit(rev_list=[_SHA_A], commits={_SHA_A: (_CLAUDE_EMAIL, _PLAIN_BODY)})
    assert subject.cmd_verify(_args(), runner=git) == 0


def test_cmd_verify_fail_returns_one_and_lists(capsys: pytest.CaptureFixture[str]) -> None:
    git = _FakeGit(rev_list=[_SHA_A], commits={_SHA_A: (_CLAUDE_EMAIL, _SELF_REDUNDANT_BODY)})
    assert subject.cmd_verify(_args(), runner=git) == 1
    err = capsys.readouterr().err
    assert "::error::" in err
    assert _SHA_A in err
    assert _CLAUDE_EMAIL in err


def test_cmd_verify_skip_returns_zero(capsys: pytest.CaptureFixture[str]) -> None:
    git = _FakeGit(rev_list_rc=128)
    assert subject.cmd_verify(_args(), runner=git) == 0
    assert "SKIP" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# main() / parser
# ---------------------------------------------------------------------------


def test_main_verify_runs_against_repo() -> None:
    # The default runner path (no injected runner) shells out to real git; an
    # unresolvable base ref is a skip (exit 0), covering the production runner.
    assert subject.main(["verify", "--base-ref", "refs/nope/missing"]) == 0


def test_main_unknown_subcommand_exits_64(capsys: pytest.CaptureFixture[str]) -> None:
    assert subject.main(["bogus"]) == 64
    assert "::error::" in capsys.readouterr().err


def test_main_no_subcommand_exits_64() -> None:
    assert subject.main([]) == 64


def test_main_block_exits_via_runpy(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy

    monkeypatch.setattr(
        "sys.argv", ["preflight_coauthor_trailer.py", "verify", "--base-ref", "refs/nope/x"]
    )
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("preflight_coauthor_trailer", run_name="__main__")
    assert exc_info.value.code == 0
