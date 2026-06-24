"""Tests for ``scripts/gate_unsigned_commit_push.py``.

Refs #1959.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import gate_unsigned_commit_push as gate
import pytest
from _commit_signatures import CommitSignature

pytestmark = pytest.mark.shard_preflight


def _fake_unsigned() -> CommitSignature:
    return CommitSignature(sha="a" * 40, signed=False, subject="wip", acked=False)


# ---------------------------------------------------------------------------
# decide() surface (helper monkeypatched so no git is needed)
# ---------------------------------------------------------------------------


def test_non_bash_tool_passes() -> None:
    assert gate.decide("Write", {"command": "git push origin x"}) is None


def test_non_push_command_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate, "_unsigned_in_push", lambda repo: [_fake_unsigned()])
    assert gate.decide("Bash", {"command": "git status"}) is None


def test_push_with_unsigned_commit_denies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate, "_unsigned_in_push", lambda repo: [_fake_unsigned()])
    decision = gate.decide("Bash", {"command": "git push -u origin feature"})
    assert decision is not None
    output = decision["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert "unsigned commit" in output["permissionDecisionReason"].lower()


def test_push_with_all_signed_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate, "_unsigned_in_push", lambda repo: [])
    assert gate.decide("Bash", {"command": "git push origin feature"}) is None


def test_ack_marker_in_command_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate, "_unsigned_in_push", lambda repo: [_fake_unsigned()])
    assert gate.decide("Bash", {"command": "git push origin feature  # unsigned-ack"}) is None


def test_rtk_prefixed_push_is_matched(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate, "_unsigned_in_push", lambda repo: [_fake_unsigned()])
    decision = gate.decide("Bash", {"command": "rtk git push origin feature"})
    assert decision is not None
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_empty_command_passes() -> None:
    assert gate.decide("Bash", {"command": ""}) is None


# ---------------------------------------------------------------------------
# _unsigned_in_push() against a real repo (fail-open + detection)
# ---------------------------------------------------------------------------


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


def _commit(repo: Path, name: str) -> str:
    (repo / name).write_text(name, encoding="utf-8")
    _git(repo, "add", name)
    _git(repo, "commit", "-m", f"commit {name}")
    return subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def test_unsigned_in_push_detects_commits_ahead_of_remote(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    base = _commit(repo, "base.txt")
    # Simulate a published remote-tracking ref at the base.
    _git(repo, "update-ref", "refs/remotes/origin/main", base)
    _git(repo, "switch", "-c", "feature")
    _commit(repo, "f1.txt")  # unsigned, ahead of origin/main
    unsigned = gate._unsigned_in_push(repo)
    assert len(unsigned) == 1
    assert unsigned[0].subject == "commit f1.txt"


def test_unsigned_in_push_fail_open_without_base(tmp_path: Path) -> None:
    # No origin/* ref resolves -> fail-open (empty), backstops take over.
    repo = _init_repo(tmp_path)
    _commit(repo, "base.txt")
    assert gate._unsigned_in_push(repo) == []


def test_unsigned_in_push_fail_open_on_detached_head(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    sha = _commit(repo, "base.txt")
    _git(repo, "update-ref", "refs/remotes/origin/main", sha)
    _git(repo, "checkout", "--detach", sha)
    assert gate._unsigned_in_push(repo) == []
