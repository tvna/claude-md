"""Tests for ``scripts/preflight_branch_base.py``.

Refs #745.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from unittest.mock import patch

import preflight_branch_base as gate
import pytest

pytestmark = pytest.mark.shard_preflight


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=repo, check=True, capture_output=True, text=True)


def _write_commit(repo: Path, name: str, content: str) -> None:
    (repo / name).write_text(content, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-m", f"commit {name}")


def _repo_with_stale_feature(tmp_path: Path) -> Path:
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
    _git(repo, "switch", "feature")
    return repo


class TestBranchFreshness:
    def test_head_containing_base_is_fresh(self, tmp_path: Path) -> None:
        repo = _repo_with_stale_feature(tmp_path)
        _git(repo, "merge", "--no-edit", "main")

        result = gate.check_base_freshness(repo=repo, base_ref="main")

        assert result.status == "pass"
        assert result.detail == "HEAD contains main"

    def test_head_missing_base_is_stale(self, tmp_path: Path) -> None:
        repo = _repo_with_stale_feature(tmp_path)

        result = gate.check_base_freshness(repo=repo, base_ref="main")

        assert result.status == "fail"
        assert "HEAD does not contain main" in result.detail


class TestCli:
    def test_verify_fails_when_branch_is_out_of_date(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        repo = _repo_with_stale_feature(tmp_path)

        exit_code = gate.main(["verify", "--repo-root", str(repo), "--base-ref", "main", "--skip-fetch"])

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "This branch is out-of-date with the base branch" in captured.err
        assert "git fetch origin main" in captured.err

    def test_verify_passes_when_branch_contains_base(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        repo = _repo_with_stale_feature(tmp_path)
        _git(repo, "merge", "--no-edit", "main")

        exit_code = gate.main(["verify", "--repo-root", str(repo), "--base-ref", "main", "--skip-fetch"])

        assert exit_code == 0
        assert "OK: branch contains base" in capsys.readouterr().out

    def test_verify_falls_back_to_remote_ref_when_no_base_ref(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        repo = _repo_with_stale_feature(tmp_path)

        exit_code = gate.main(["verify", "--repo-root", str(repo), "--skip-fetch"])

        assert exit_code == 1
        captured = capsys.readouterr()
        assert "out-of-date" in captured.err

    def test_verify_surfaces_runtime_error_on_fetch_failure(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        repo = _repo_with_stale_feature(tmp_path)

        with patch.object(gate, "fetch_base", side_effect=RuntimeError("fetch failed")):
            exit_code = gate.main(["verify", "--repo-root", str(repo)])

        assert exit_code == 1
        assert "branch base preflight failed" in capsys.readouterr().err


class TestRunGit:
    def test_raises_when_git_not_found(self, tmp_path: Path) -> None:
        with patch("_git.shutil.which", return_value=None), pytest.raises(RuntimeError, match="git executable not found"):
            gate.run_git(tmp_path, ["status"])


class TestFetchBase:
    def test_raises_on_nonzero_returncode(self, tmp_path: Path) -> None:
        fake = subprocess.CompletedProcess(["git"], returncode=128, stdout="", stderr="fatal: repo not found")
        with patch.object(gate, "run_git", return_value=fake), pytest.raises(RuntimeError, match="git fetch origin main failed"):
            gate.fetch_base(tmp_path, remote="origin", base_branch="main")

    def test_returns_fetch_head_on_success(self, tmp_path: Path) -> None:
        fake = subprocess.CompletedProcess(["git"], returncode=0, stdout="", stderr="")
        with patch.object(gate, "run_git", return_value=fake):
            ref = gate.fetch_base(tmp_path, remote="origin", base_branch="main")
        assert ref == "FETCH_HEAD"


class TestCheckBaseFreshness:
    def test_returns_fail_when_base_ref_unavailable(self, tmp_path: Path) -> None:
        fake_fail = subprocess.CompletedProcess(["git"], returncode=128, stdout="", stderr="unknown revision")

        def _run_git(_repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
            return fake_fail

        with patch.object(gate, "run_git", side_effect=_run_git):
            result = gate.check_base_freshness(repo=tmp_path, base_ref="nonexistent")

        assert result.status == "fail"
        assert "is not available" in result.detail

    def test_returns_fail_on_unexpected_merge_base_exit(self, tmp_path: Path) -> None:
        rev_ok = subprocess.CompletedProcess(["git"], returncode=0, stdout="abc123\n", stderr="")
        merge_bad = subprocess.CompletedProcess(["git"], returncode=2, stdout="", stderr="fatal: error")
        call_count = 0

        def _run_git(_repo: Path, args: list[str]) -> subprocess.CompletedProcess[str]:
            nonlocal call_count
            call_count += 1
            return rev_ok if call_count == 1 else merge_bad

        with patch.object(gate, "run_git", side_effect=_run_git):
            result = gate.check_base_freshness(repo=tmp_path, base_ref="main")

        assert result.status == "fail"
        assert "merge-base check failed" in result.detail
