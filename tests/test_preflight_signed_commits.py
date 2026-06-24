"""Tests for ``scripts/preflight_signed_commits.py``.

Refs #1959.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import preflight_signed_commits as gate
import pytest

pytestmark = pytest.mark.shard_preflight


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-c", "commit.gpgsign=false", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "main")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    return repo


def _commit(repo: Path, name: str, message: str = "commit") -> None:
    (repo / name).write_text(name, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-m", message)


def _run(repo: Path) -> int:
    return gate.main(["verify", "--repo-root", str(repo)])


def test_unsigned_commit_in_branch_range_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _init_repo(tmp_path)
    _commit(repo, "base.txt")
    _git(repo, "switch", "-c", "feature")
    _commit(repo, "f1.txt")
    # Make `main` the resolvable base so the range is main..HEAD.
    assert _run(repo) == 1
    err = capsys.readouterr().err
    assert "Unsigned commit" in err
    assert "unsigned-ack" in err  # repair hint mentions the opt-in


def test_acked_unsigned_commit_passes(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    _commit(repo, "base.txt")
    _git(repo, "switch", "-c", "feature")
    _commit(repo, "f1.txt", message="wip\n\nunsigned-ack: scratch")
    assert _run(repo) == 0


def test_empty_range_passes(tmp_path: Path) -> None:
    # HEAD == base: no commits ahead, nothing to inspect.
    repo = _init_repo(tmp_path)
    _commit(repo, "base.txt")
    _git(repo, "switch", "-c", "feature")
    assert _run(repo) == 0


def test_fallback_to_head_when_no_base(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # No `main`/`origin/main`: the only branch is `trunk`, so the gate inspects
    # HEAD alone and still catches the unsigned tip.
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-b", "trunk")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _commit(repo, "a.txt")
    assert _run(repo) == 1
    out = capsys.readouterr()
    assert "no base ref" in out.err
    assert "Unsigned commit" in out.err


def test_unknown_command_raises() -> None:
    with pytest.raises(SystemExit):
        gate.main(["bogus"])


def test_verify_fails_loud_on_git_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    # A git failure while reading the range must fail the gate loudly (exit 1),
    # never pass silently (CLAUDE.md section 4).
    repo = _init_repo(tmp_path)
    _commit(repo, "base.txt")

    def _boom(*_args: object, **_kwargs: object) -> list[object]:
        raise RuntimeError("git exploded")

    monkeypatch.setattr(gate, "list_signatures", _boom)
    assert _run(repo) == 1
    assert "signed-commits preflight failed" in capsys.readouterr().err
