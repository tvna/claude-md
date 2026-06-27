"""Tests for scripts/preflight_session_base_freshness.py (Refs #1632, Fact 3).

The gate shifts the pre-push branch-base check LEFT to session start and the
first commit, reusing ``preflight_main_freshness`` (stamp IO + fetch) and
``preflight_branch_base`` (HEAD-contains-base). These tests build real tiny git
repos so the staleness verdict is exercised against actual git plumbing, and
monkeypatch the module globals / the remote env so the hook decision is unit
tested without a live remote.
"""

from __future__ import annotations

import subprocess
from datetime import UTC, datetime
from pathlib import Path

import preflight_branch_base
import preflight_main_freshness as pmf
import preflight_session_base_freshness as gate
import pytest

pytestmark = pytest.mark.shard_preflight


def _now() -> datetime:
    return datetime.now(UTC)


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _rev(repo: Path, ref: str) -> str:
    return subprocess.run(
        ["git", "rev-parse", ref], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _write_commit(repo: Path, name: str, content: str) -> None:
    (repo / name).write_text(content, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-m", f"commit {name}")


def _stale_repo(tmp_path: Path) -> tuple[Path, str]:
    """Return (repo, main_sha) for a feature branch cut from an OLD main.

    main advances past where feature was branched, so HEAD (feature) does not
    contain the current main tip; the Fact 3 stale-base shape. ``main_sha`` is
    the advanced main tip, i.e. what a session-start stamp would record.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _write_commit(repo, "base.txt", "base-1\n")
    _git(repo, "switch", "-c", "feature")
    _write_commit(repo, "feature.txt", "feature\n")
    _git(repo, "switch", "main")
    _write_commit(repo, "base2.txt", "base-2\n")
    main_sha = _rev(repo, "main")
    _git(repo, "switch", "feature")
    return repo, main_sha


def _ffable_stale_repo(tmp_path: Path) -> tuple[Path, str]:
    """Return (repo, main_sha) for a branch cut from an OLD main with NO local work.

    HEAD is an ancestor of the advanced main tip, so the branch is a pure
    fast-forward to main: the freshly-cut-branch-before-first-commit shape that
    the session-start auto-update targets. ``main_sha`` is the advanced tip.
    """
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _write_commit(repo, "base.txt", "base-1\n")
    _git(repo, "switch", "-c", "feature")  # cut feature at the old base, no work
    _git(repo, "switch", "main")
    _write_commit(repo, "base2.txt", "base-2\n")  # main advances
    main_sha = _rev(repo, "main")
    _git(repo, "switch", "feature")
    return repo, main_sha


def _point_module_at(
    monkeypatch: pytest.MonkeyPatch, repo: Path, stamp: Path, *, remote: bool = True
) -> None:
    monkeypatch.setattr(gate, "REPO_ROOT", repo)
    monkeypatch.setattr(gate, "STAMP_FILE", stamp)
    if remote:
        monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    else:
        monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)


_COMMIT_EVENT = {"tool_name": "Bash", "tool_input": {"command": "git add -A && git commit -m x"}}


class TestBaseIsStale:
    def test_stale_when_head_lacks_recorded_base(self, tmp_path: Path) -> None:
        repo, main_sha = _stale_repo(tmp_path)
        stamp = tmp_path / "STAMP"
        pmf.write_stamp(main_sha, path=stamp)
        assert gate.base_is_stale(repo=repo, stamp_path=stamp) is True

    def test_fresh_after_rebase(self, tmp_path: Path) -> None:
        repo, main_sha = _stale_repo(tmp_path)
        stamp = tmp_path / "STAMP"
        pmf.write_stamp(main_sha, path=stamp)
        _git(repo, "rebase", "main")
        assert gate.base_is_stale(repo=repo, stamp_path=stamp) is False

    def test_none_when_no_stamp(self, tmp_path: Path) -> None:
        repo, _ = _stale_repo(tmp_path)
        assert gate.base_is_stale(repo=repo, stamp_path=tmp_path / "absent") is None


class TestForcePushBlocked:
    @pytest.mark.parametrize(
        "branch,expected",
        [
            ("claude/my-feature", True),
            ("feature/foo", True),
            ("fix/some-bug", True),
            ("dependabot/update-pkg", False),
            ("dependabot/npm_and_yarn/x-1.0", False),
            ("main", False),
            (None, False),
        ],
    )
    def test_force_push_blocked(self, branch: str | None, expected: bool) -> None:
        assert gate._force_push_blocked(branch) is expected


class TestDecide:
    def test_denies_commit_on_stale_base(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, main_sha = _stale_repo(tmp_path)
        stamp = tmp_path / "STAMP"
        pmf.write_stamp(main_sha, path=stamp)
        _point_module_at(monkeypatch, repo, stamp)

        decision = gate.decide(_COMMIT_EVENT)

        assert decision is not None
        reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
        assert "stale" in reason
        # "feature" branch is subject to non_fast_forward -> shows runbook, not rebase
        assert gate._RUNBOOK in reason
        assert "git rebase origin/main" not in reason

    def test_denies_commit_non_fast_forward_branch_shows_runbook(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """claude/* branch (non_fast_forward) must point to the server-side runbook."""
        repo, main_sha = _stale_repo(tmp_path)
        stamp = tmp_path / "STAMP"
        pmf.write_stamp(main_sha, path=stamp)
        _point_module_at(monkeypatch, repo, stamp)
        monkeypatch.setattr(gate, "_current_branch", lambda *_: "claude/my-feature")

        decision = gate.decide(_COMMIT_EVENT)

        assert decision is not None
        reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
        assert "stale" in reason
        assert gate._RUNBOOK in reason
        assert "git rebase origin/main" not in reason

    def test_denies_commit_dependabot_branch_shows_rebase(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """dependabot/* branch (force-push allowed) must show the git rebase path."""
        repo, main_sha = _stale_repo(tmp_path)
        stamp = tmp_path / "STAMP"
        pmf.write_stamp(main_sha, path=stamp)
        _point_module_at(monkeypatch, repo, stamp)
        monkeypatch.setattr(gate, "_current_branch", lambda *_: "dependabot/update-pkg")

        decision = gate.decide(_COMMIT_EVENT)

        assert decision is not None
        reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
        assert "stale" in reason
        assert "git rebase origin/main" in reason
        assert gate._RUNBOOK not in reason

    def test_allows_commit_after_rebase(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, main_sha = _stale_repo(tmp_path)
        stamp = tmp_path / "STAMP"
        pmf.write_stamp(main_sha, path=stamp)
        _git(repo, "rebase", "main")
        _point_module_at(monkeypatch, repo, stamp)

        assert gate.decide(_COMMIT_EVENT) is None

    def test_allows_non_commit_command(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, main_sha = _stale_repo(tmp_path)
        stamp = tmp_path / "STAMP"
        pmf.write_stamp(main_sha, path=stamp)
        _point_module_at(monkeypatch, repo, stamp)

        event = {"tool_name": "Bash", "tool_input": {"command": "git status"}}
        assert gate.decide(event) is None

    def test_fail_open_without_stamp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, _ = _stale_repo(tmp_path)
        _point_module_at(monkeypatch, repo, tmp_path / "absent")
        assert gate.decide(_COMMIT_EVENT) is None

    def test_no_decision_when_not_remote(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, main_sha = _stale_repo(tmp_path)
        stamp = tmp_path / "STAMP"
        pmf.write_stamp(main_sha, path=stamp)
        _point_module_at(monkeypatch, repo, stamp, remote=False)
        assert gate.decide(_COMMIT_EVENT) is None

    def test_no_decision_for_non_bash_tool(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, main_sha = _stale_repo(tmp_path)
        stamp = tmp_path / "STAMP"
        pmf.write_stamp(main_sha, path=stamp)
        _point_module_at(monkeypatch, repo, stamp)
        assert gate.decide({"tool_name": "Write", "tool_input": {}}) is None


class TestCheckCommand:
    def test_check_exits_1_on_stale(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo, main_sha = _stale_repo(tmp_path)
        stamp = tmp_path / "STAMP"
        pmf.write_stamp(main_sha, path=stamp)
        _point_module_at(monkeypatch, repo, stamp)
        assert gate.main(["check"]) == 1
        assert "stale" in capsys.readouterr().err

    def test_check_exits_0_when_fresh(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, main_sha = _stale_repo(tmp_path)
        stamp = tmp_path / "STAMP"
        pmf.write_stamp(main_sha, path=stamp)
        _git(repo, "rebase", "main")
        _point_module_at(monkeypatch, repo, stamp)
        assert gate.main(["check"]) == 0

    def test_check_exits_0_when_no_stamp(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        repo, _ = _stale_repo(tmp_path)
        _point_module_at(monkeypatch, repo, tmp_path / "absent")
        assert gate.main(["check"]) == 0


class TestSessionStart:
    def test_no_op_when_not_remote(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
        called = False

        def _boom(*a: object, **k: object) -> object:
            nonlocal called
            called = True
            raise AssertionError("must not fetch when not remote")

        monkeypatch.setattr(pmf, "fetch_and_record", _boom)
        assert gate.main(["session-start"]) == 0
        assert called is False

    def test_warns_on_stale_base(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
        monkeypatch.setattr(gate, "_current_branch", lambda *_: "claude/test-feature")
        monkeypatch.setattr(
            pmf,
            "fetch_and_record",
            lambda **k: pmf.FreshnessStamp(sha="a" * 40, fetched_at=_now()),
        )
        monkeypatch.setattr(
            preflight_branch_base,
            "check_base_freshness",
            lambda **k: preflight_branch_base.BranchBaseResult(status="fail", detail="stale"),
        )
        assert gate.main(["session-start"]) == 0
        out = capsys.readouterr().out
        assert "STALE BRANCH BASE" in out
        # claude/* branch is non_fast_forward -> shows runbook, not rebase
        assert gate._RUNBOOK in out
        assert "git rebase origin/main" not in out

    def test_warns_on_stale_base_dependabot_shows_rebase(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """dependabot/* branch can force-push -> session-start warning shows git rebase."""
        monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
        monkeypatch.setattr(gate, "_current_branch", lambda *_: "dependabot/update-pkg")
        monkeypatch.setattr(
            pmf,
            "fetch_and_record",
            lambda **k: pmf.FreshnessStamp(sha="a" * 40, fetched_at=_now()),
        )
        monkeypatch.setattr(
            preflight_branch_base,
            "check_base_freshness",
            lambda **k: preflight_branch_base.BranchBaseResult(status="fail", detail="stale"),
        )
        assert gate.main(["session-start"]) == 0
        out = capsys.readouterr().out
        assert "STALE BRANCH BASE" in out
        assert "git rebase origin/main" in out
        assert gate._RUNBOOK not in out

    def test_silent_when_fresh(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
        monkeypatch.setattr(
            pmf,
            "fetch_and_record",
            lambda **k: pmf.FreshnessStamp(sha="b" * 40, fetched_at=_now()),
        )
        monkeypatch.setattr(
            preflight_branch_base,
            "check_base_freshness",
            lambda **k: preflight_branch_base.BranchBaseResult(status="pass", detail="ok"),
        )
        assert gate.main(["session-start"]) == 0
        assert capsys.readouterr().out == ""

    def test_fail_open_on_fetch_error(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")

        def _boom(**k: object) -> object:
            raise RuntimeError("network down")

        monkeypatch.setattr(pmf, "fetch_and_record", _boom)
        assert gate.main(["session-start"]) == 0
        assert capsys.readouterr().out == ""

    def test_auto_updates_ffable_stale_base(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Clean + fast-forwardable stale base is auto-updated, not just warned about."""
        repo, main_sha = _ffable_stale_repo(tmp_path)
        stamp = tmp_path / "STAMP"
        _point_module_at(monkeypatch, repo, stamp)
        pmf.write_stamp(main_sha, path=stamp)
        # No live remote in the tiny repo: fetch_and_record just records the SHA.
        monkeypatch.setattr(pmf, "fetch_and_record", lambda **k: pmf.write_stamp(main_sha, path=stamp))
        assert gate.base_is_stale(repo=repo, stamp_path=stamp) is True  # precondition

        assert gate.main(["session-start"]) == 0

        out = capsys.readouterr().out
        assert "AUTO-UPDATED" in out
        # The branch now contains the recorded base -> no longer stale.
        assert gate.base_is_stale(repo=repo, stamp_path=stamp) is False

    def test_warns_when_not_ffable(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A diverged (non-fast-forwardable) stale base falls back to the warning."""
        repo, main_sha = _stale_repo(tmp_path)  # feature has its own commit -> diverged
        stamp = tmp_path / "STAMP"
        _point_module_at(monkeypatch, repo, stamp)
        monkeypatch.setattr(pmf, "fetch_and_record", lambda **k: pmf.write_stamp(main_sha, path=stamp))

        assert gate.main(["session-start"]) == 0

        out = capsys.readouterr().out
        assert "STALE BRANCH BASE" in out
        assert "AUTO-UPDATED" not in out
        # Base is untouched (still stale): the diverged branch was left for the operator.
        assert gate.base_is_stale(repo=repo, stamp_path=stamp) is True


    def test_no_auto_update_on_detached_head(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A detached HEAD (no branch) must warn, not silently fast-forward HEAD."""
        repo, main_sha = _ffable_stale_repo(tmp_path)
        _git(repo, "checkout", "--detach")  # detach at the feature tip
        before = _rev(repo, "HEAD")
        stamp = tmp_path / "STAMP"
        _point_module_at(monkeypatch, repo, stamp)
        pmf.write_stamp(main_sha, path=stamp)
        monkeypatch.setattr(pmf, "fetch_and_record", lambda **k: pmf.write_stamp(main_sha, path=stamp))

        assert gate.main(["session-start"]) == 0

        out = capsys.readouterr().out
        assert "STALE BRANCH BASE" in out
        assert "AUTO-UPDATED" not in out
        assert _rev(repo, "HEAD") == before  # detached HEAD was not moved


class TestTryAutoUpdateBase:
    def test_updated_when_clean_and_ffable(self, tmp_path: Path) -> None:
        repo, main_sha = _ffable_stale_repo(tmp_path)
        assert gate._try_auto_update_base(main_sha, repo=repo) == "updated"
        assert _rev(repo, "HEAD") == main_sha

    def test_skipped_when_not_ffable(self, tmp_path: Path) -> None:
        repo, main_sha = _stale_repo(tmp_path)  # diverged
        before = _rev(repo, "HEAD")
        assert gate._try_auto_update_base(main_sha, repo=repo) == "skipped"
        assert _rev(repo, "HEAD") == before  # untouched

    def test_skipped_when_tracked_change_present(self, tmp_path: Path) -> None:
        # A tracked, uncommitted change makes the tree dirty -> skip, so the
        # auto fast-forward never moves HEAD over local work. base.txt is
        # tracked (committed before feature was cut). Refs #2093 item 2.
        repo, main_sha = _ffable_stale_repo(tmp_path)
        (repo / "base.txt").write_text("locally edited\n", encoding="utf-8")
        before = _rev(repo, "HEAD")
        assert gate._try_auto_update_base(main_sha, repo=repo) == "skipped"
        assert _rev(repo, "HEAD") == before  # untouched

    def test_updated_with_untracked_files_present(self, tmp_path: Path) -> None:
        # Untracked files do not block the fast-forward: --ff-only never touches
        # them, so a freshly-cut branch carrying stray untracked files still
        # updates. The cleanliness check uses --untracked-files=no. Refs #2093.
        repo, main_sha = _ffable_stale_repo(tmp_path)
        (repo / "scratch.txt").write_text("untracked\n", encoding="utf-8")
        assert gate._try_auto_update_base(main_sha, repo=repo) == "updated"
        assert _rev(repo, "HEAD") == main_sha
        assert (repo / "scratch.txt").read_text(encoding="utf-8") == "untracked\n"

    def test_skipped_on_git_error(self, tmp_path: Path) -> None:
        repo, _ = _ffable_stale_repo(tmp_path)
        # A non-existent target SHA makes the is-ancestor check fail -> skip.
        assert gate._try_auto_update_base("0" * 40, repo=repo) == "skipped"
