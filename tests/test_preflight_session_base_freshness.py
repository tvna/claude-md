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
    contain the current main tip -- the Fact 3 stale-base shape. ``main_sha`` is
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
