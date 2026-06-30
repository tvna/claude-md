"""Tests for ``scripts/preflight_push_unsigned_commits.py``.

Refs #2138. Verifies that the PreToolUse hook denies a ``git push`` whose
pushed commits include an unsigned one, allows a push of only signed commits,
and falls open everywhere a deny would be a guess: a non-remote session, a
non-Bash tool, a non-push command, an ``# unsigned-ack`` marker, an
undeterminable range, or a git error. A commit is unsigned when its raw object
carries no ``gpgsig`` header (the verify-commit false-positive fix).

Codex review on PR #2140 hardened three cases, each covered below: every
refspec in a multi-refspec push is inspected; a bare refspec resolves its local
SOURCE ref by name (not ``HEAD``); and a ``git push`` chained after another
command (``git commit && git push``) is still detected.
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
    ``rev_list`` is the default commit list for any ``rev-list`` call;
    ``rev_list_map`` overrides it per local sha (the part after ``..`` for a
    range, or the sole sha for a new-branch scan) so distinct refspecs can ship
    distinct commits. ``unsigned`` is the set of shas whose ``cat-file commit``
    object carries no ``gpgsig`` header (the signed shas get one).
    """

    def __init__(
        self,
        *,
        rev_parse: dict[str, str] | None = None,
        rev_list: list[str] | None = None,
        rev_list_map: dict[str, list[str]] | None = None,
        rev_list_rc: int = 0,
        unsigned: set[str] | None = None,
        remotes: dict[str, str] | None = None,
        raise_on: str | None = None,
    ) -> None:
        self.rev_parse = rev_parse or {}
        self.rev_list = rev_list if rev_list is not None else []
        self.rev_list_map = rev_list_map or {}
        self.rev_list_rc = rev_list_rc
        self.unsigned = unsigned or set()
        # Configured remotes (name -> url) for `git remote -v`, used by
        # _git.resolve_remote_name on the new-branch path. Defaults to origin so
        # the existing --remotes=origin expectations hold (#2162).
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
        if sub == "rev-parse":
            ref = args[-1]
            sha = self.rev_parse.get(ref)
            if sha is None:
                return _cp(returncode=1)
            return _cp(stdout=sha + "\n")
        if sub == "rev-list":
            if self.rev_list_rc != 0:
                return _cp(returncode=self.rev_list_rc)
            key = args[1].rsplit("..", 1)[-1]
            commits = self.rev_list_map.get(key, self.rev_list)
            return _cp(stdout="\n".join(commits) + "\n")
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


def _existing_branch(branch: str, commits: list[str], unsigned: set[str]) -> _FakeGit:
    """A fake where *branch* exists on origin and ships *commits* (a bare push)."""
    return _FakeGit(
        rev_parse={branch: _LOCAL_SHA, f"refs/remotes/origin/{branch}": _REMOTE_SHA},
        rev_list=commits,
        unsigned=unsigned,
    )


@pytest.fixture
def remote(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")


# ---------------------------------------------------------------------------
# environment / target gates -> fail-open
# ---------------------------------------------------------------------------


def test_passthrough_when_not_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    monkeypatch.delenv("CODEX_CODE_REMOTE", raising=False)
    git = _existing_branch("feat/x", [_UNSIGNED], {_UNSIGNED})
    assert subject.decide(_bash_event("git push origin feat/x"), runner=git) is None
    assert git.calls == []  # never even shells out


def test_codex_remote_signal_activates(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    monkeypatch.setenv("CODEX_CODE_REMOTE", "true")
    git = _existing_branch("feat/x", [_UNSIGNED], {_UNSIGNED})
    result = subject.decide(_bash_event("git push origin feat/x"), runner=git)
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_passthrough_non_bash_tool(remote: None) -> None:
    git = _existing_branch("feat/x", [_UNSIGNED], {_UNSIGNED})
    event = {"tool_name": "Write", "tool_input": {"command": "git push origin feat/x"}}
    assert subject.decide(event, runner=git) is None


def test_passthrough_bash_non_push(remote: None) -> None:
    git = _existing_branch("feat/x", [_UNSIGNED], {_UNSIGNED})
    assert subject.decide(_bash_event("git status"), runner=git) is None
    assert subject.decide(_bash_event("git commit -m x"), runner=git) is None
    assert subject.decide(_bash_event('echo "git push origin feat/x"'), runner=git) is None


def test_passthrough_ack_marker(remote: None) -> None:
    git = _existing_branch("feat/x", [_UNSIGNED], {_UNSIGNED})
    cmd = "git push origin feat/x  # unsigned-ack"
    assert subject.decide(_bash_event(cmd), runner=git) is None


# ---------------------------------------------------------------------------
# signed-only push -> allow ; unsigned commit -> deny
# ---------------------------------------------------------------------------


def test_allows_signed_only_push(remote: None) -> None:
    git = _existing_branch("feat/x", [_SIGNED, _SIGNED], set())
    assert subject.decide(_bash_event("git push origin feat/x"), runner=git) is None


def test_denies_push_with_unsigned_commit(remote: None) -> None:
    git = _existing_branch("feat/x", [_SIGNED, _UNSIGNED], {_UNSIGNED})
    result = subject.decide(_bash_event("git push origin feat/x"), runner=git)
    assert result is not None
    reason = result["hookSpecificOutput"]["permissionDecisionReason"]
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert _UNSIGNED[:12] in reason
    assert "#2138" in reason


def test_denies_push_u_with_unsigned_commit(remote: None) -> None:
    git = _existing_branch("feat/x", [_UNSIGNED], {_UNSIGNED})
    result = subject.decide(_bash_event("git push -u origin feat/x"), runner=git)
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_bare_refspec_resolves_source_by_name_not_head(remote: None) -> None:
    # Codex review #2140: `git push origin other` while HEAD != other pushes the
    # local `other` ref. The gate must resolve `other`, not HEAD, or it misses an
    # unsigned commit on the pushed branch when HEAD is clean.
    git = _FakeGit(
        rev_parse={"other": _LOCAL_SHA, "refs/remotes/origin/other": _REMOTE_SHA},
        rev_list=[_UNSIGNED],
        unsigned={_UNSIGNED},
    )
    result = subject.decide(_bash_event("git push origin other"), runner=git)
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    # The source ref resolved was `other`, never `HEAD`.
    refs = [c[-1] for c in git.calls if c[0] == "rev-parse"]
    assert "other" in refs
    assert "HEAD" not in refs


def test_head_colon_refspec_uses_head_source(remote: None) -> None:
    git = _FakeGit(
        rev_parse={"HEAD": _LOCAL_SHA, "refs/remotes/origin/dst": _REMOTE_SHA},
        rev_list=[_UNSIGNED],
        unsigned={_UNSIGNED},
    )
    result = subject.decide(_bash_event("git push origin HEAD:dst"), runner=git)
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_inspects_every_refspec(remote: None) -> None:
    # Codex review #2140: a multi-refspec push must inspect ALL refspecs; an
    # unsigned commit on the SECOND must be caught even when the first is clean.
    git = _FakeGit(
        rev_parse={
            "clean": _LOCAL_SHA,
            "refs/remotes/origin/clean": _REMOTE_SHA,
            "dirty": _SIGNED,  # distinct local tip sha
            "refs/remotes/origin/dirty": _REMOTE_SHA,
        },
        rev_list_map={_LOCAL_SHA: [_SIGNED], _SIGNED: [_UNSIGNED]},
        unsigned={_UNSIGNED},
    )
    result = subject.decide(_bash_event("git push origin clean dirty"), runner=git)
    assert result is not None
    assert _UNSIGNED[:12] in result["hookSpecificOutput"]["permissionDecisionReason"]


def test_deletion_refspec_ships_nothing(remote: None) -> None:
    # `:dst` is a branch deletion; it carries no commit, so it is not flagged.
    git = _FakeGit(rev_parse={}, rev_list=[_UNSIGNED], unsigned={_UNSIGNED})
    assert subject.decide(_bash_event("git push origin :dst"), runner=git) is None


# ---------------------------------------------------------------------------
# chained push after a shell operator (Codex review #2140)
# ---------------------------------------------------------------------------


def test_chained_commit_then_push_is_inspected(remote: None) -> None:
    git = _existing_branch("feat/x", [_UNSIGNED], {_UNSIGNED})
    cmd = "git commit -m x && git push origin feat/x"
    result = subject.decide(_bash_event(cmd), runner=git)
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_rtk_rewritten_push_is_checked(remote: None) -> None:
    git = _existing_branch("feat/x", [_UNSIGNED], {_UNSIGNED})
    result = subject.decide(_bash_event("rtk git push origin feat/x"), runner=git)
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


# ---------------------------------------------------------------------------
# new branch (all-zeros remote sha) -> rev-list --not --remotes
# ---------------------------------------------------------------------------


def test_new_branch_scans_all_commits_not_on_remote(remote: None) -> None:
    git = _FakeGit(
        rev_parse={"feat/new": _LOCAL_SHA},  # remote ref absent -> unresolved
        rev_list=[_SIGNED, _UNSIGNED],
        unsigned={_UNSIGNED},
    )
    result = subject.decide(_bash_event("git push origin feat/new"), runner=git)
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    rev_list_calls = [c for c in git.calls if c[0] == "rev-list"]
    assert rev_list_calls == [["rev-list", _LOCAL_SHA, "--not", "--remotes=origin"]]


def test_existing_branch_uses_range(remote: None) -> None:
    git = _existing_branch("feat/x", [_SIGNED], set())
    subject.decide(_bash_event("git push origin feat/x"), runner=git)
    rev_list_calls = [c for c in git.calls if c[0] == "rev-list"]
    assert rev_list_calls == [["rev-list", f"{_REMOTE_SHA}..{_LOCAL_SHA}"]]


def test_all_zeros_remote_sha_treated_as_new_branch(remote: None) -> None:
    git = _FakeGit(
        rev_parse={"feat/x": _LOCAL_SHA, "refs/remotes/origin/feat/x": _ALL_ZEROS},
        rev_list=[_SIGNED],
        unsigned=set(),
    )
    subject.decide(_bash_event("git push origin feat/x"), runner=git)
    rev_list_calls = [c for c in git.calls if c[0] == "rev-list"]
    assert rev_list_calls == [["rev-list", _LOCAL_SHA, "--not", "--remotes=origin"]]


# ---------------------------------------------------------------------------
# fail-open paths
# ---------------------------------------------------------------------------


def test_passthrough_no_explicit_refspec(remote: None) -> None:
    git = _existing_branch("feat/x", [_UNSIGNED], {_UNSIGNED})
    assert subject.decide(_bash_event("git push"), runner=git) is None
    assert subject.decide(_bash_event("git push origin"), runner=git) is None


def test_passthrough_local_sha_unresolved(remote: None) -> None:
    git = _FakeGit(rev_parse={}, rev_list=[_UNSIGNED], unsigned={_UNSIGNED})
    assert subject.decide(_bash_event("git push origin feat/x"), runner=git) is None


def test_passthrough_empty_range(remote: None) -> None:
    git = _existing_branch("feat/x", [], {_UNSIGNED})
    assert subject.decide(_bash_event("git push origin feat/x"), runner=git) is None


def test_passthrough_on_rev_list_error(remote: None) -> None:
    git = _existing_branch("feat/x", [_UNSIGNED], {_UNSIGNED})
    git.raise_on = "rev-list"
    assert subject.decide(_bash_event("git push origin feat/x"), runner=git) is None


def test_passthrough_on_rev_list_nonzero(remote: None) -> None:
    git = _FakeGit(
        rev_parse={"feat/x": _LOCAL_SHA, "refs/remotes/origin/feat/x": _REMOTE_SHA},
        rev_list_rc=128,
        unsigned={_UNSIGNED},
    )
    assert subject.decide(_bash_event("git push origin feat/x"), runner=git) is None


def test_passthrough_on_rev_parse_error(remote: None) -> None:
    git = _existing_branch("feat/x", [_UNSIGNED], {_UNSIGNED})
    git.raise_on = "rev-parse"
    assert subject.decide(_bash_event("git push origin feat/x"), runner=git) is None


def test_cat_file_error_fails_open(remote: None) -> None:
    git = _existing_branch("feat/x", [_UNSIGNED], {_UNSIGNED})
    git.raise_on = "cat-file"
    assert subject.decide(_bash_event("git push origin feat/x"), runner=git) is None


def test_one_unresolvable_spec_does_not_block_others(remote: None) -> None:
    # The first refspec cannot be resolved (skipped, fail-open for it); the
    # second is a determinable unsigned push and is still caught.
    git = _FakeGit(
        rev_parse={"dirty": _LOCAL_SHA, "refs/remotes/origin/dirty": _REMOTE_SHA},
        rev_list=[_UNSIGNED],
        unsigned={_UNSIGNED},
    )
    result = subject.decide(_bash_event("git push origin missing dirty"), runner=git)
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


# ---------------------------------------------------------------------------
# _iter_push_specs() / _push_args_in_segment() / _specs_from_push_args()
# ---------------------------------------------------------------------------


class TestIterPushSpecs:
    def test_simple_push(self) -> None:
        assert subject._iter_push_specs("git push origin feat/x") == [("origin", "feat/x", "feat/x")]

    def test_u_flag(self) -> None:
        assert subject._iter_push_specs("git push -u origin feat/x") == [("origin", "feat/x", "feat/x")]

    def test_colon_refspec(self) -> None:
        assert subject._iter_push_specs("git push origin a:b") == [("origin", "a", "b")]

    def test_head_colon_refspec(self) -> None:
        assert subject._iter_push_specs("git push origin HEAD:b") == [("origin", "HEAD", "b")]

    def test_force_prefix_stripped(self) -> None:
        assert subject._iter_push_specs("git push origin +feat/x") == [("origin", "feat/x", "feat/x")]

    def test_multiple_refspecs(self) -> None:
        assert subject._iter_push_specs("git push origin a b") == [
            ("origin", "a", "a"),
            ("origin", "b", "b"),
        ]

    def test_deletion_skipped(self) -> None:
        assert subject._iter_push_specs("git push origin :b") == []

    def test_empty_remote_side_skipped(self) -> None:
        assert subject._iter_push_specs("git push origin a:") == []

    def test_leading_separator_empty_segment_skipped(self) -> None:
        assert subject._iter_push_specs("; git push origin feat/x") == [("origin", "feat/x", "feat/x")]

    def test_no_refspec_is_empty(self) -> None:
        assert subject._iter_push_specs("git push") == []
        assert subject._iter_push_specs("git push origin") == []

    def test_non_push_is_empty(self) -> None:
        assert subject._iter_push_specs("echo hello") == []
        assert subject._iter_push_specs("git status") == []

    def test_quoted_mention_is_not_a_push(self) -> None:
        assert subject._iter_push_specs('echo "git push origin feat/x"') == []

    def test_chained_after_operator(self) -> None:
        assert subject._iter_push_specs("git commit -m x && git push origin feat/x") == [
            ("origin", "feat/x", "feat/x")
        ]

    def test_rtk_prefix(self) -> None:
        assert subject._iter_push_specs("rtk git push origin feat/x") == [("origin", "feat/x", "feat/x")]

    def test_env_assignment_prefix(self) -> None:
        assert subject._iter_push_specs("GIT_TRACE=1 git push origin feat/x") == [
            ("origin", "feat/x", "feat/x")
        ]

    def test_git_global_option_before_push(self) -> None:
        assert subject._iter_push_specs("git -c k=v push origin feat/x") == [("origin", "feat/x", "feat/x")]
        assert subject._iter_push_specs("git -C /repo push origin feat/x") == [
            ("origin", "feat/x", "feat/x")
        ]

    def test_absolute_git_path(self) -> None:
        assert subject._iter_push_specs("/usr/bin/git push origin feat/x") == [
            ("origin", "feat/x", "feat/x")
        ]

    def test_double_dash_end_of_options(self) -> None:
        assert subject._iter_push_specs("git push origin -- feat/x") == [("origin", "feat/x", "feat/x")]  # dh-ok

    def test_flag_with_value_consumes_token(self) -> None:
        assert subject._iter_push_specs("git push -o ci=skip origin feat/x") == [
            ("origin", "feat/x", "feat/x")
        ]

    def test_unknown_flag_skipped(self) -> None:
        assert subject._iter_push_specs("git push --weird origin feat/x") == [("origin", "feat/x", "feat/x")]

    def test_malformed_quote_segment_skipped(self) -> None:
        assert subject._iter_push_specs('git push origin "feat/x') == []

    def test_git_non_push_subcommand_mentioning_push(self) -> None:
        # A git command whose path/args mention "push" but whose subcommand is
        # not push (passes the cheap "push" substring guard, rejected by the
        # tokenizing parser).
        assert subject._iter_push_specs("git add pushlog.txt") == []
        assert subject._iter_push_specs("git -c k=v log --grep=push") == []


# ---------------------------------------------------------------------------
# _is_unsigned() header-presence semantics live with the shared definition in
# tests/test_commit_signing.py; the deny/allow cases above exercise the import.
# ---------------------------------------------------------------------------


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
