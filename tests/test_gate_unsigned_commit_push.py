"""Tests for ``scripts/gate_unsigned_commit_push.py``.

Refs #1959.
"""

from __future__ import annotations

import io
import subprocess
from pathlib import Path

import gate_unsigned_commit_push as gate
import pytest
from _commit_signatures import CommitSignature

pytestmark = pytest.mark.shard_preflight


def _fake_unsigned() -> CommitSignature:
    return CommitSignature(sha="a" * 40, signed=False, subject="wip", acked=False)


# ---------------------------------------------------------------------------
# parse_push_sources (pure refspec parsing)
# ---------------------------------------------------------------------------


def test_parse_bare_push_inspects_head() -> None:
    assert gate.parse_push_sources("git push") == gate.PushPlan(False, ("HEAD",))
    assert gate.parse_push_sources("git push origin") == gate.PushPlan(False, ("HEAD",))


def test_parse_named_branch_refspec() -> None:
    # The Codex review case: a named branch must be inspected, not HEAD.
    assert gate.parse_push_sources("git push origin feature") == gate.PushPlan(False, ("feature",))


def test_parse_src_dst_refspec_uses_local_source() -> None:
    assert gate.parse_push_sources("git push origin HEAD:main") == gate.PushPlan(False, ("HEAD",))
    assert gate.parse_push_sources("git push origin local:remote") == gate.PushPlan(False, ("local",))


def test_parse_strips_force_plus_and_handles_multiple_refspecs() -> None:
    assert gate.parse_push_sources("git push origin +feature") == gate.PushPlan(False, ("feature",))
    assert gate.parse_push_sources("git push origin a b") == gate.PushPlan(False, ("a", "b"))


def test_parse_set_upstream_flag_is_not_a_positional() -> None:
    assert gate.parse_push_sources("git push -u origin feature") == gate.PushPlan(False, ("feature",))


def test_parse_value_flag_consumes_its_token() -> None:
    # ``-o ci.skip`` must not be mistaken for the remote/refspec positionals.
    assert gate.parse_push_sources("git push -o ci.skip origin feature") == gate.PushPlan(False, ("feature",))


def test_parse_all_branches() -> None:
    assert gate.parse_push_sources("git push --all origin") == gate.PushPlan(True, ())


def test_parse_delete_has_no_content() -> None:
    assert gate.parse_push_sources("git push --delete origin feature") == gate.PushPlan(False, ())
    assert gate.parse_push_sources("git push origin :stale") == gate.PushPlan(False, ())


def test_parse_malformed_command_falls_back_to_head() -> None:
    # An unbalanced quote makes shlex raise; fall back to HEAD rather than crash.
    assert gate.parse_push_sources("git push origin 'unterminated") == gate.PushPlan(False, ("HEAD",))


# ---------------------------------------------------------------------------
# decide() surface (helper monkeypatched so no git is needed)
# ---------------------------------------------------------------------------


def test_non_bash_tool_passes() -> None:
    assert gate.decide("Write", {"command": "git push origin x"}) is None


def test_non_push_command_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate, "_unsigned_in_push", lambda repo, command: [_fake_unsigned()])
    assert gate.decide("Bash", {"command": "git status"}) is None


def test_push_with_unsigned_commit_denies(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate, "_unsigned_in_push", lambda repo, command: [_fake_unsigned()])
    decision = gate.decide("Bash", {"command": "git push -u origin feature"})
    assert decision is not None
    output = decision["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny"
    assert "unsigned commit" in output["permissionDecisionReason"].lower()


def test_push_with_all_signed_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate, "_unsigned_in_push", lambda repo, command: [])
    assert gate.decide("Bash", {"command": "git push origin feature"}) is None


def test_ack_marker_in_command_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate, "_unsigned_in_push", lambda repo, command: [_fake_unsigned()])
    assert gate.decide("Bash", {"command": "git push origin feature  # unsigned-ack"}) is None


def test_rtk_prefixed_push_is_matched(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gate, "_unsigned_in_push", lambda repo, command: [_fake_unsigned()])
    decision = gate.decide("Bash", {"command": "rtk git push origin feature"})
    assert decision is not None
    assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_empty_command_passes() -> None:
    assert gate.decide("Bash", {"command": ""}) is None


# ---------------------------------------------------------------------------
# _unsigned_in_push() against a real repo (refspec-aware + fail-open)
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
    _git(repo, "update-ref", "refs/remotes/origin/main", base)
    _git(repo, "switch", "-c", "feature")
    _commit(repo, "f1.txt")  # unsigned, ahead of origin/main
    unsigned = gate._unsigned_in_push(repo, "git push origin feature")
    assert len(unsigned) == 1
    assert unsigned[0].subject == "commit f1.txt"


def test_unsigned_in_push_inspects_named_branch_not_head(tmp_path: Path) -> None:
    # The Codex review case: checked out on main (clean), but the command pushes
    # `feature`, which carries an unsigned commit. The gate must inspect feature.
    repo = _init_repo(tmp_path)
    base = _commit(repo, "base.txt")
    _git(repo, "update-ref", "refs/remotes/origin/main", base)
    _git(repo, "switch", "-c", "feature")
    _commit(repo, "f1.txt")
    _git(repo, "switch", "main")  # HEAD is now main; origin/main..HEAD is empty
    unsigned = gate._unsigned_in_push(repo, "git push origin feature")
    assert len(unsigned) == 1
    assert unsigned[0].subject == "commit f1.txt"


def test_unsigned_in_push_all_branches(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    base = _commit(repo, "base.txt")
    _git(repo, "update-ref", "refs/remotes/origin/main", base)
    _git(repo, "switch", "-c", "feature")
    _commit(repo, "f1.txt")
    _git(repo, "switch", "main")
    unsigned = gate._unsigned_in_push(repo, "git push --all origin")
    # feature's unsigned commit is caught even though it is not checked out.
    assert any(u.subject == "commit f1.txt" for u in unsigned)


def test_unsigned_in_push_delete_inspects_nothing(tmp_path: Path) -> None:
    repo = _init_repo(tmp_path)
    base = _commit(repo, "base.txt")
    _git(repo, "update-ref", "refs/remotes/origin/main", base)
    _git(repo, "switch", "-c", "feature")
    _commit(repo, "f1.txt")
    assert gate._unsigned_in_push(repo, "git push --delete origin feature") == []


def test_unsigned_in_push_fail_open_without_base(tmp_path: Path) -> None:
    # No origin/* ref resolves -> fail-open (empty), backstops take over.
    repo = _init_repo(tmp_path)
    _commit(repo, "base.txt")
    assert gate._unsigned_in_push(repo, "git push origin main") == []


def test_unsigned_in_push_fail_open_on_git_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    repo = _init_repo(tmp_path)
    base = _commit(repo, "base.txt")
    _git(repo, "update-ref", "refs/remotes/origin/main", base)
    _git(repo, "switch", "-c", "feature")
    _commit(repo, "f1.txt")

    def _boom(*_args: object, **_kwargs: object) -> list[object]:
        raise RuntimeError("git exploded")

    monkeypatch.setattr(gate, "list_signatures", _boom)
    assert gate._unsigned_in_push(repo, "git push origin feature") == []


def test_main_fail_open_without_event(monkeypatch: pytest.MonkeyPatch) -> None:
    # main() reads a PreToolUse event from stdin; an empty stdin yields no
    # decision and a clean exit 0 (fail-open at the I/O boundary).
    monkeypatch.setattr("sys.stdin", io.StringIO(""))
    assert gate.main([]) == 0
