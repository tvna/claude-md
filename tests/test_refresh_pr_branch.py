"""Tests for ``scripts/refresh_pr_branch.py``.

Builds real temporary git repositories (commit signing disabled) and a
manually populated ``refs/remotes/origin/main`` tracking ref so the
deterministic behind-branch refresh path can be exercised end to end
without a network remote. Refs #1361 (R2).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
import refresh_pr_branch as rpb

pytestmark = pytest.mark.shard_preflight


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _commit(repo: Path, name: str, content: str) -> None:
    (repo / name).write_text(content)
    _git(repo, "add", name)
    _git(repo, "commit", "-m", f"commit {name}")


def _head(repo: Path) -> str:
    return _git(repo, "rev-parse", "HEAD").stdout.strip()


def _set_origin_main(repo: Path, sha: str) -> None:
    _git(repo, "update-ref", "refs/remotes/origin/main", sha)


def _base_repo(tmp_path: Path) -> Path:
    """Repo on branch ``feature`` with a base commit shared by origin/main."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main", "-q")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    # base file with enough lines that separated edits do not collide.
    _commit(repo, "f.txt", "\n".join(str(i) for i in range(1, 21)) + "\n")
    base_sha = _head(repo)
    _set_origin_main(repo, base_sha)
    _git(repo, "checkout", "-q", "-b", "feature")
    return repo


def _advance_origin_main(repo: Path, *, line: int, value: str) -> None:
    """Add a commit on main editing one line, then move origin/main to it."""
    _git(repo, "checkout", "-q", "main")
    lines = (repo / "f.txt").read_text().splitlines()
    lines[line - 1] = value
    (repo / "f.txt").write_text("\n".join(lines) + "\n")
    _git(repo, "commit", "-aqm", f"main edit line {line}")
    _set_origin_main(repo, _head(repo))
    _git(repo, "checkout", "-q", "feature")


class TestHelpers:
    def test_current_branch(self, tmp_path: Path) -> None:
        repo = _base_repo(tmp_path)
        assert rpb.current_branch(cwd=repo) == "feature"

    def test_worktree_clean_then_dirty(self, tmp_path: Path) -> None:
        repo = _base_repo(tmp_path)
        assert rpb.worktree_dirty(cwd=repo) is False
        (repo / "f.txt").write_text("changed\n")
        assert rpb.worktree_dirty(cwd=repo) is True

    def test_behind_count_zero_when_up_to_date(self, tmp_path: Path) -> None:
        repo = _base_repo(tmp_path)
        assert rpb.behind_count("origin", "main", cwd=repo) == 0

    def test_behind_count_counts_advances(self, tmp_path: Path) -> None:
        repo = _base_repo(tmp_path)
        _advance_origin_main(repo, line=1, value="TOP")
        _advance_origin_main(repo, line=20, value="BOTTOM")
        assert rpb.behind_count("origin", "main", cwd=repo) == 2

    def test_merge_would_conflict_false_for_separated_edits(self, tmp_path: Path) -> None:
        repo = _base_repo(tmp_path)
        # feature edits bottom line; origin/main edits top line -> no conflict.
        lines = (repo / "f.txt").read_text().splitlines()
        lines[19] = "FEATURE-BOTTOM"
        (repo / "f.txt").write_text("\n".join(lines) + "\n")
        _git(repo, "commit", "-aqm", "feature edit")
        _advance_origin_main(repo, line=1, value="MAIN-TOP")
        assert rpb.merge_would_conflict("origin", "main", cwd=repo) is False

    def test_merge_would_conflict_true_for_same_line(self, tmp_path: Path) -> None:
        repo = _base_repo(tmp_path)
        lines = (repo / "f.txt").read_text().splitlines()
        lines[0] = "FEATURE-TOP"
        (repo / "f.txt").write_text("\n".join(lines) + "\n")
        _git(repo, "commit", "-aqm", "feature edit top")
        _advance_origin_main(repo, line=1, value="MAIN-TOP")
        assert rpb.merge_would_conflict("origin", "main", cwd=repo) is True


class TestRefresh:
    def test_up_to_date_is_noop(self, tmp_path: Path) -> None:
        repo = _base_repo(tmp_path)
        code, msg = rpb.refresh(cwd=repo, do_fetch=False)
        assert code == 0
        assert "already up to date" in msg

    def test_behind_conflict_free_merges(self, tmp_path: Path) -> None:
        repo = _base_repo(tmp_path)
        _advance_origin_main(repo, line=1, value="MAIN-TOP")
        before = _head(repo)
        code, msg = rpb.refresh(cwd=repo, do_fetch=False)
        assert code == 0
        assert "Merged" in msg
        # HEAD advanced (a merge commit was created) and is now up to date.
        assert _head(repo) != before
        assert rpb.behind_count("origin", "main", cwd=repo) == 0

    def test_behind_conflict_is_not_merged(self, tmp_path: Path) -> None:
        repo = _base_repo(tmp_path)
        lines = (repo / "f.txt").read_text().splitlines()
        lines[0] = "FEATURE-TOP"
        (repo / "f.txt").write_text("\n".join(lines) + "\n")
        _git(repo, "commit", "-aqm", "feature edit top")
        _advance_origin_main(repo, line=1, value="MAIN-TOP")
        before = _head(repo)
        code, msg = rpb.refresh(cwd=repo, do_fetch=False)
        assert code == rpb._CONFLICT_EXIT
        assert "CONFLICTS" in msg
        assert "update-pr-branch-recovery.md" in msg
        # No merge happened.
        assert _head(repo) == before

    def test_dry_run_does_not_merge(self, tmp_path: Path) -> None:
        repo = _base_repo(tmp_path)
        _advance_origin_main(repo, line=1, value="MAIN-TOP")
        before = _head(repo)
        code, msg = rpb.refresh(cwd=repo, do_fetch=False, dry_run=True)
        assert code == 0
        assert "[dry-run]" in msg
        assert _head(repo) == before

    def test_refuses_on_base_branch(self, tmp_path: Path) -> None:
        repo = _base_repo(tmp_path)
        _git(repo, "checkout", "-q", "main")
        code, msg = rpb.refresh(cwd=repo, do_fetch=False)
        assert code == rpb._PRECONDITION_EXIT
        assert "base branch" in msg

    def test_refuses_dirty_worktree(self, tmp_path: Path) -> None:
        repo = _base_repo(tmp_path)
        _advance_origin_main(repo, line=1, value="MAIN-TOP")
        (repo / "f.txt").write_text("uncommitted\n")
        code, msg = rpb.refresh(cwd=repo, do_fetch=False)
        assert code == rpb._PRECONDITION_EXIT
        assert "uncommitted" in msg

    def test_refuses_detached_head(self, tmp_path: Path) -> None:
        repo = _base_repo(tmp_path)
        _git(repo, "checkout", "-q", "--detach")
        code, msg = rpb.refresh(cwd=repo, do_fetch=False)
        assert code == rpb._PRECONDITION_EXIT
        assert "detached" in msg.lower()

    def test_missing_ref_is_precondition_error(self, tmp_path: Path) -> None:
        repo = _base_repo(tmp_path)
        code, msg = rpb.refresh(cwd=repo, base="nonexistent", do_fetch=False)
        assert code == rpb._PRECONDITION_EXIT


class TestMain:
    def test_main_up_to_date_exits_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _base_repo(tmp_path)
        monkeypatch.chdir(repo)
        rc = rpb.main(["--no-fetch"])
        assert rc == 0
        assert "already up to date" in capsys.readouterr().out

    def test_main_conflict_exits_two_on_stderr(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        repo = _base_repo(tmp_path)
        lines = (repo / "f.txt").read_text().splitlines()
        lines[0] = "FEATURE-TOP"
        (repo / "f.txt").write_text("\n".join(lines) + "\n")
        _git(repo, "commit", "-aqm", "feature edit top")
        _advance_origin_main(repo, line=1, value="MAIN-TOP")
        monkeypatch.chdir(repo)
        rc = rpb.main(["--no-fetch"])
        assert rc == rpb._CONFLICT_EXIT
        assert "CONFLICTS" in capsys.readouterr().err


class TestFetchFailure:
    def test_fetch_failure_is_precondition_error(self, tmp_path: Path) -> None:
        # do_fetch=True on a repo with no remote "origin" -> fetch fails ->
        # lines 116-118 (_PRECONDITION_EXIT return in refresh()).
        repo = _base_repo(tmp_path)
        code, msg = rpb.refresh(cwd=repo, do_fetch=True)
        assert code == rpb._PRECONDITION_EXIT
        assert "fetch" in msg
