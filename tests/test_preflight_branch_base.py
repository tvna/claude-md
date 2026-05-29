"""Tests for ``scripts/preflight_branch_base.py``.

Refs #745.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import preflight_branch_base as gate
import pytest

pytestmark = pytest.mark.shard_preflight


def _git(repo: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


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
