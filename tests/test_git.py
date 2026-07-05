"""Tests for ``scripts/_git.py``.

Verifies the shared git runner's plumbing without depending on a real
repository: that it resolves git from PATH, raises when git is absent, and
forwards cwd/check/timeout to ``subprocess.run`` while always capturing text
output.

Refs #1005.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import _git
import pytest

pytestmark = pytest.mark.shard_preflight


class TestRunGit:
    def test_raises_when_git_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_git.shutil, "which", lambda _name: None)
        with pytest.raises(RuntimeError, match="git executable not found"):
            _git.run_git(["status"])

    def test_invokes_resolved_git_with_captured_text(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        captured: dict[str, Any] = {}
        monkeypatch.setattr(_git.shutil, "which", lambda _name: "/usr/bin/git")

        def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            captured["argv"] = argv
            captured["kwargs"] = kwargs
            return subprocess.CompletedProcess(argv, 0, stdout="ok", stderr="")

        monkeypatch.setattr(_git.subprocess, "run", fake_run)
        result = _git.run_git(["rev-parse", "HEAD"], cwd=Path("/repo"), timeout=5)

        kwargs: dict[str, Any] = captured["kwargs"]
        assert captured["argv"] == ["/usr/bin/git", "rev-parse", "HEAD"]
        assert kwargs["cwd"] == Path("/repo")
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["check"] is False
        assert kwargs["timeout"] == 5
        assert result.stdout == "ok"

    def test_check_true_is_forwarded(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: dict[str, Any] = {}
        monkeypatch.setattr(_git.shutil, "which", lambda _name: "/usr/bin/git")

        def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            seen.update(kwargs)
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        monkeypatch.setattr(_git.subprocess, "run", fake_run)
        _git.run_git(["fetch"], check=True)
        assert seen["check"] is True

    def test_returns_completed_process(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(_git.shutil, "which", lambda _name: "/usr/bin/git")
        sentinel = subprocess.CompletedProcess(["git"], 1, stdout="", stderr="boom")
        monkeypatch.setattr(_git.subprocess, "run", lambda *a, **k: sentinel)
        assert _git.run_git(["status"]) is sentinel


class TestMakeRunner:
    def test_binds_cwd_and_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: dict[str, Any] = {}
        monkeypatch.setattr(_git.shutil, "which", lambda _name: "/usr/bin/git")

        def fake_run(argv: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
            seen["argv"] = argv
            seen["kwargs"] = kwargs
            return subprocess.CompletedProcess(argv, 0, stdout="", stderr="")

        monkeypatch.setattr(_git.subprocess, "run", fake_run)
        runner = _git.make_runner(cwd=Path("/repo"), timeout=7)
        runner(["rev-parse", "HEAD"])
        assert seen["argv"] == ["/usr/bin/git", "rev-parse", "HEAD"]
        assert seen["kwargs"]["cwd"] == Path("/repo")
        assert seen["kwargs"]["timeout"] == 7

    def test_defaults_to_no_cwd_no_timeout(self, monkeypatch: pytest.MonkeyPatch) -> None:
        seen: dict[str, Any] = {}
        monkeypatch.setattr(_git.shutil, "which", lambda _name: "/usr/bin/git")
        monkeypatch.setattr(
            _git.subprocess,
            "run",
            lambda argv, **kwargs: seen.update(kwargs)
            or subprocess.CompletedProcess(argv, 0, stdout="", stderr=""),
        )
        _git.make_runner()(["status"])
        assert seen["cwd"] is None
        assert seen["timeout"] is None


class TestRevList:
    @staticmethod
    def _runner(
        result: subprocess.CompletedProcess[str] | Exception, calls: list[list[str]]
    ) -> _git.Runner:
        def run(args: list[str]) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            if isinstance(result, Exception):
                raise result
            return result

        return run

    def test_prefixes_rev_list_and_strips_blanks(self) -> None:
        calls: list[list[str]] = []
        runner = self._runner(
            subprocess.CompletedProcess(["git"], 0, stdout="a\n\n b \n", stderr=""), calls
        )
        assert _git.rev_list(runner, ["base..HEAD"]) == ["a", "b"]
        assert calls == [["rev-list", "base..HEAD"]]

    def test_empty_output_is_empty_list(self) -> None:
        runner = self._runner(subprocess.CompletedProcess(["git"], 0, stdout="\n", stderr=""), [])
        assert _git.rev_list(runner, ["base..HEAD"]) == []

    def test_nonzero_exit_returns_none(self) -> None:
        runner = self._runner(subprocess.CompletedProcess(["git"], 128, stdout="", stderr="no"), [])
        assert _git.rev_list(runner, ["bad..HEAD"]) is None

    def test_subprocess_error_returns_none(self) -> None:
        runner = self._runner(OSError("boom"), [])
        assert _git.rev_list(runner, ["base..HEAD"]) is None


class TestCommitsInRange:
    def test_strips_blanks(self) -> None:
        calls: list[list[str]] = []
        runner = TestRevList._runner(
            subprocess.CompletedProcess(["git"], 0, stdout="a\n\n b \n", stderr=""), calls
        )
        assert _git.commits_in_range(runner, "origin/main") == ["a", "b"]
        assert calls == [["rev-list", "origin/main..HEAD"]]

    def test_unresolvable_returns_none(self) -> None:
        calls: list[list[str]] = []
        runner = TestRevList._runner(
            subprocess.CompletedProcess(["git"], 128, stdout="", stderr="no"), calls
        )
        assert _git.commits_in_range(runner, "origin/nope") is None


class TestIsAllZeros:
    def test_sha1_all_zeros(self) -> None:
        assert _git.is_all_zeros("0" * 40) is True

    def test_sha256_all_zeros(self) -> None:
        assert _git.is_all_zeros("0" * 64) is True

    def test_real_sha_is_not_all_zeros(self) -> None:
        assert _git.is_all_zeros("a" * 40) is False

    def test_partial_zeros_is_not_all_zeros(self) -> None:
        assert _git.is_all_zeros("0" * 39 + "1") is False


class TestResolveRemoteName:
    @staticmethod
    def _runner(remote_v: str, rc: int = 0) -> _git.Runner:
        def run(args: list[str]) -> subprocess.CompletedProcess[str]:
            assert args == ["remote", "-v"]
            return subprocess.CompletedProcess(["git"], rc, stdout=remote_v, stderr="")

        return run

    _REMOTE_V = (
        "origin\thttps://example.test/repo.git (fetch)\n"
        "origin\thttps://example.test/repo.git (push)\n"
    )

    def test_configured_name_passthrough(self) -> None:
        assert _git.resolve_remote_name(self._runner(self._REMOTE_V), "origin") == "origin"

    def test_url_maps_to_name(self) -> None:
        got = _git.resolve_remote_name(self._runner(self._REMOTE_V), "https://example.test/repo.git")
        assert got == "origin"

    def test_unknown_url_returns_none(self) -> None:
        assert _git.resolve_remote_name(self._runner(self._REMOTE_V), "https://other/x.git") is None

    def test_empty_remote_returns_none(self) -> None:
        # No git call needed for an empty remote.
        assert _git.resolve_remote_name(self._runner("", rc=1), "") is None

    def test_git_error_returns_none(self) -> None:
        def run(args: list[str]) -> subprocess.CompletedProcess[str]:
            raise OSError("boom")

        assert _git.resolve_remote_name(run, "origin") is None

    def test_nonzero_exit_returns_none(self) -> None:
        assert _git.resolve_remote_name(self._runner("", rc=2), "origin") is None

    def test_skips_blank_and_short_lines(self) -> None:
        # A blank or single-field line in `git remote -v` output is skipped.
        out = "\nbroken\n" + self._REMOTE_V
        assert _git.resolve_remote_name(self._runner(out), "origin") == "origin"


class TestCommitsToPush:
    _REMOTE_V = (
        "origin\thttps://example.test/repo.git (fetch)\n"
        "origin\thttps://example.test/repo.git (push)\n"
    )

    def _runner(self, commits: list[str], calls: list[list[str]]) -> _git.Runner:
        def run(args: list[str]) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            if args[0] == "remote":
                return subprocess.CompletedProcess(["git"], 0, stdout=self._REMOTE_V, stderr="")
            return subprocess.CompletedProcess(["git"], 0, stdout="\n".join(commits) + "\n", stderr="")

        return run

    @staticmethod
    def _rev_list(calls: list[list[str]]) -> list[list[str]]:
        return [c for c in calls if c[0] == "rev-list"]

    def test_existing_branch_uses_range(self) -> None:
        calls: list[list[str]] = []
        runner = self._runner(["c1"], calls)
        result = _git.commits_to_push(runner, local_sha="L", remote_sha="R", remote="origin")
        assert result == ["c1"]
        # The existing-branch range needs no remote resolution.
        assert calls == [["rev-list", "R..L"]]

    def test_new_branch_scopes_to_remote_name(self) -> None:
        calls: list[list[str]] = []
        runner = self._runner(["c1", "c2"], calls)
        result = _git.commits_to_push(runner, local_sha="L", remote_sha=None, remote="origin")
        assert result == ["c1", "c2"]
        assert self._rev_list(calls) == [["rev-list", "L", "--not", "--remotes=origin"]]

    def test_new_branch_url_remote_maps_to_name(self) -> None:
        calls: list[list[str]] = []
        runner = self._runner(["c1"], calls)
        _git.commits_to_push(
            runner, local_sha="L", remote_sha=None, remote="https://example.test/repo.git"
        )
        assert self._rev_list(calls) == [["rev-list", "L", "--not", "--remotes=origin"]]

    def test_new_branch_unknown_url_falls_back_to_all_remotes(self) -> None:
        # The #2162 fix: a URL that matches no configured remote scopes to all
        # remote-tracking refs, never a bogus --remotes=<url> that scans history.
        calls: list[list[str]] = []
        runner = self._runner(["c1"], calls)
        _git.commits_to_push(runner, local_sha="L", remote_sha=None, remote="https://other/x.git")
        assert self._rev_list(calls) == [["rev-list", "L", "--not", "--remotes"]]

    def test_new_branch_none_remote_falls_back_to_all_remotes(self) -> None:
        calls: list[list[str]] = []
        runner = self._runner(["c1"], calls)
        _git.commits_to_push(runner, local_sha="L", remote_sha=None, remote=None)
        assert self._rev_list(calls) == [["rev-list", "L", "--not", "--remotes"]]

    def test_all_zeros_remote_treated_as_new_branch(self) -> None:
        calls: list[list[str]] = []
        runner = self._runner(["c1"], calls)
        _git.commits_to_push(runner, local_sha="L", remote_sha="0" * 40, remote="origin")
        assert self._rev_list(calls) == [["rev-list", "L", "--not", "--remotes=origin"]]

    def test_undeterminable_propagates_none(self) -> None:
        def run(args: list[str]) -> subprocess.CompletedProcess[str]:
            return subprocess.CompletedProcess(["git"], 128, stdout="", stderr="boom")

        assert _git.commits_to_push(run, local_sha="L", remote_sha="R", remote="origin") is None


_OTHER_TIP = "3333333333333333333333333333333333333333"
_REMOTE_OID = "4444444444444444444444444444444444444444"
_ZEROS = "0" * 40


class TestParsePushRefs:
    def test_reads_four_fields(self) -> None:
        payload = f"refs/heads/feat {_OTHER_TIP} refs/heads/feat {_REMOTE_OID}\n"
        refs = _git.parse_push_refs(payload)
        assert refs == [_git.PushRef("refs/heads/feat", _OTHER_TIP, "refs/heads/feat", _REMOTE_OID)]

    def test_skips_blank_and_malformed(self) -> None:
        payload = f"\nnot enough fields\nrefs/heads/a {_OTHER_TIP} refs/heads/a {_REMOTE_OID}\n   \n"
        refs = _git.parse_push_refs(payload)
        assert [r.local_ref for r in refs] == ["refs/heads/a"]

    def test_delete_line(self) -> None:
        # A deletion line is "(delete) <zeros> <remote-ref> <remote-oid>": four fields.
        refs = _git.parse_push_refs(f"(delete) {_ZEROS} refs/heads/old {_REMOTE_OID}")
        assert refs == [_git.PushRef("(delete)", _ZEROS, "refs/heads/old", _REMOTE_OID)]


class TestReadPushRefs:
    def test_defaults_remote_to_origin(self) -> None:
        env = {_git._PUSH_REFS_ENV_VAR: f"refs/heads/a {_OTHER_TIP} refs/heads/a {_REMOTE_OID}"}
        refs, remote = _git.read_push_refs(env)
        assert len(refs) == 1
        assert remote == "origin"

    def test_uses_named_remote(self) -> None:
        env = {
            _git._PUSH_REFS_ENV_VAR: f"refs/heads/a {_OTHER_TIP} refs/heads/a {_REMOTE_OID}",
            _git._PUSH_REMOTE_ENV_VAR: "upstream",
        }
        _refs, remote = _git.read_push_refs(env)
        assert remote == "upstream"

    def test_empty_when_unset(self) -> None:
        refs, _remote = _git.read_push_refs({})
        assert refs == []


class TestCommitsForPushedRefs:
    _SIGNED = "1111111111111111111111111111111111111111"
    _UNSIGNED = "2222222222222222222222222222222222222222"

    def _ref(self, local_oid: str, remote_oid: str, name: str = "refs/heads/feat") -> _git.PushRef:
        return _git.PushRef(name, local_oid, name, remote_oid)

    def _runner(
        self, rev_list_map: dict[str, list[str]], calls: list[list[str]], *, rc: int = 0
    ) -> _git.Runner:
        def run(args: list[str]) -> subprocess.CompletedProcess[str]:
            calls.append(args)
            if args[0] == "remote":
                return subprocess.CompletedProcess(
                    ["git"],
                    0,
                    stdout="origin\thttps://example.test/repo.git (fetch)\n"
                    "origin\thttps://example.test/repo.git (push)\n",
                    stderr="",
                )
            if args[0] == "rev-list":
                if rc != 0:
                    return subprocess.CompletedProcess(["git"], rc, stdout="", stderr="")
                key = args[1].rsplit("..", 1)[-1]
                commits = rev_list_map.get(key, [])
                return subprocess.CompletedProcess(["git"], 0, stdout="\n".join(commits) + "\n", stderr="")
            return subprocess.CompletedProcess(["git"], 0, stdout="", stderr="")

        return run

    def test_existing_branch_uses_range(self) -> None:
        calls: list[list[str]] = []
        runner = self._runner({_OTHER_TIP: [self._SIGNED]}, calls)
        commits, undeterminable = _git.commits_for_pushed_refs(
            runner, [self._ref(_OTHER_TIP, _REMOTE_OID)], "origin"
        )
        assert commits == [self._SIGNED]
        assert undeterminable is False
        rev_list_calls = [c for c in calls if c[0] == "rev-list"]
        assert rev_list_calls == [["rev-list", f"{_REMOTE_OID}..{_OTHER_TIP}"]]

    def test_new_branch_scopes_to_remote(self) -> None:
        calls: list[list[str]] = []
        runner = self._runner({_OTHER_TIP: [self._UNSIGNED]}, calls)
        commits, undeterminable = _git.commits_for_pushed_refs(
            runner, [self._ref(_OTHER_TIP, _ZEROS)], "origin"
        )
        assert commits == [self._UNSIGNED]
        assert undeterminable is False
        rev_list_calls = [c for c in calls if c[0] == "rev-list"]
        assert rev_list_calls == [["rev-list", _OTHER_TIP, "--not", "--remotes=origin"]]

    def test_delete_refspec_ships_nothing(self) -> None:
        calls: list[list[str]] = []
        runner = self._runner({}, calls)
        commits, undeterminable = _git.commits_for_pushed_refs(
            runner, [self._ref(_ZEROS, _REMOTE_OID)], "origin"
        )
        assert commits == []
        assert undeterminable is False
        assert [c for c in calls if c[0] == "rev-list"] == []

    def test_dedups_commits_across_refs_preserving_order(self) -> None:
        calls: list[list[str]] = []
        runner = self._runner({_OTHER_TIP: [self._UNSIGNED, self._SIGNED]}, calls)
        refs = [
            self._ref(_OTHER_TIP, _REMOTE_OID, "refs/heads/a"),
            self._ref(_OTHER_TIP, _REMOTE_OID, "refs/heads/b"),
        ]
        commits, _undeterminable = _git.commits_for_pushed_refs(runner, refs, "origin")
        assert commits == [self._UNSIGNED, self._SIGNED]

    def test_all_undeterminable(self) -> None:
        calls: list[list[str]] = []
        runner = self._runner({}, calls, rc=128)
        commits, undeterminable = _git.commits_for_pushed_refs(
            runner, [self._ref(_OTHER_TIP, _REMOTE_OID)], "origin"
        )
        assert commits == []
        assert undeterminable is True

    def test_undeterminable_ref_does_not_drop_resolvable_one(self) -> None:
        def run(args: list[str]) -> subprocess.CompletedProcess[str]:
            if args[0] == "rev-list" and args[1].endswith(_OTHER_TIP):
                return subprocess.CompletedProcess(["git"], 128, stdout="", stderr="")
            if args[0] == "rev-list":
                return subprocess.CompletedProcess(["git"], 0, stdout=self._SIGNED + "\n", stderr="")
            return subprocess.CompletedProcess(["git"], 0, stdout="", stderr="")

        refs = [
            self._ref(_OTHER_TIP, _REMOTE_OID, "refs/heads/a"),
            self._ref(_REMOTE_OID, _OTHER_TIP, "refs/heads/b"),
        ]
        commits, undeterminable = _git.commits_for_pushed_refs(run, refs, "origin")
        assert commits == [self._SIGNED]
        assert undeterminable is True
