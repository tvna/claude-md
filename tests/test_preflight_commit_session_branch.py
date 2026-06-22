"""Tests for scripts/preflight_commit_session_branch.py.

Refs #1181, #785. Verifies that the PreToolUse hook blocks ``git commit``
commands issued while the checked-out branch is not the session-designated
branch, and allows commits made on the session branch. Mirrors the test
structure of ``tests/test_preflight_push_session_branch.py``.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import preflight_commit_session_branch as subject
import pytest

pytestmark = pytest.mark.shard_preflight

_SESSION_BRANCH = "claude/stoic-johnson-ryJlF"


def _bash_event(command: str) -> dict[str, Any]:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _with_session(
    session: str | set[str],
    current: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    authorized = {session} if isinstance(session, str) else set(session)
    monkeypatch.setattr(subject, "_read_authorized_branches", lambda: authorized)
    monkeypatch.setattr(subject, "_current_branch", lambda: current)


# ---------------------------------------------------------------------------
# decide() -- environment gate
# ---------------------------------------------------------------------------


def test_decide_passthrough_when_not_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    assert subject.decide(_bash_event("git commit -m x")) is None


def test_decide_passthrough_when_remote_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "false")
    assert subject.decide(_bash_event("git commit -m x")) is None


def test_decide_passthrough_non_bash_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, "other/branch", monkeypatch)
    event = {"tool_name": "Write", "tool_input": {"command": "git commit -m x"}}
    assert subject.decide(event) is None


def test_decide_passthrough_bash_non_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, "other/branch", monkeypatch)
    assert subject.decide(_bash_event("git status")) is None
    assert subject.decide(_bash_event("git push origin HEAD")) is None
    assert subject.decide(_bash_event("ls -la")) is None


def test_decide_passthrough_commit_tree(monkeypatch: pytest.MonkeyPatch) -> None:
    # ``git commit-tree`` is plumbing, not the porcelain commit we gate.
    _with_session(_SESSION_BRANCH, "other/branch", monkeypatch)
    assert subject.decide(_bash_event("git commit-tree abc123 -m x")) is None


def test_decide_passthrough_no_session_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    # Empty authorized set (bootstrap / unrecorded session) -- fail-open.
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.setattr(subject, "_read_authorized_branches", set)
    monkeypatch.setattr(subject, "_current_branch", lambda: "other/branch")
    assert subject.decide(_bash_event("git commit -m x")) is None


def test_decide_passthrough_detached_head(monkeypatch: pytest.MonkeyPatch) -> None:
    # Unknown current branch (detached HEAD / read error) -- fail-open.
    _with_session(_SESSION_BRANCH, None, monkeypatch)
    assert subject.decide(_bash_event("git commit -m x")) is None


# ---------------------------------------------------------------------------
# decide() -- allowed commits (on the session branch)
# ---------------------------------------------------------------------------


def test_decide_allows_commit_on_session_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, _SESSION_BRANCH, monkeypatch)
    assert subject.decide(_bash_event("git commit -m 'msg'")) is None


def test_decide_allows_chained_commit_on_session_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_session(_SESSION_BRANCH, _SESSION_BRANCH, monkeypatch)
    cmd = "git add -A && git commit -m 'msg'"
    assert subject.decide(_bash_event(cmd)) is None


# ---------------------------------------------------------------------------
# decide() -- denied commits (on a non-session branch)
# ---------------------------------------------------------------------------


def test_decide_denies_commit_on_other_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, "feat/other-issue", monkeypatch)
    result = subject.decide(_bash_event("git commit -m 'work'"))
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    reason = result["hookSpecificOutput"]["permissionDecisionReason"]
    assert _SESSION_BRANCH in reason
    assert "feat/other-issue" in reason


def test_decide_denies_chained_commit_on_other_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_session(_SESSION_BRANCH, "feat/other-issue", monkeypatch)
    cmd = "git add -A && git commit -m 'work'"
    result = subject.decide(_bash_event(cmd))
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_decide_deny_message_names_both_branches(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_session(_SESSION_BRANCH, "feat/xyz", monkeypatch)
    result = subject.decide(_bash_event("git commit -m m"))
    assert result is not None
    reason = result["hookSpecificOutput"]["permissionDecisionReason"]
    assert _SESSION_BRANCH in reason
    assert "feat/xyz" in reason
    assert f"git switch {_SESSION_BRANCH}" in reason


def test_decide_deny_message_references_issue(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, "feat/xyz", monkeypatch)
    result = subject.decide(_bash_event("git commit -m m"))
    assert result is not None
    reason = result["hookSpecificOutput"]["permissionDecisionReason"]
    assert "#1181" in reason
    assert "#785" in reason


def test_decide_denies_commit_amend_on_other_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_session(_SESSION_BRANCH, "feat/other", monkeypatch)
    result = subject.decide(_bash_event("git commit --amend --no-edit"))
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


# ---------------------------------------------------------------------------
# decide() -- multi-factor authorized set (Refs #1513)
# ---------------------------------------------------------------------------


def test_decide_allows_commit_on_any_set_member(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Paired work / post-merge: a commit on EITHER authorized branch passes.
    branch_b = "claude/follow-up-branch"
    _with_session({_SESSION_BRANCH, branch_b}, branch_b, monkeypatch)
    assert subject.decide(_bash_event("git commit -m work")) is None


def test_decide_denies_commit_on_main_even_when_in_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Invariant 1: committing on a protected branch is denied even if a stale
    # entry names it.
    _with_session({_SESSION_BRANCH, "main"}, "main", monkeypatch)
    result = subject.decide(_bash_event("git commit -m work"))
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_decide_denies_commit_on_unauthorized_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Invariant 2: a branch never added to the set stays denied.
    _with_session(_SESSION_BRANCH, "claude/hopeful-turing-pex8i2", monkeypatch)
    result = subject.decide(_bash_event("git commit -m work"))
    assert result is not None
    reason = result["hookSpecificOutput"]["permissionDecisionReason"]
    assert "claude/hopeful-turing-pex8i2" in reason
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


# ---------------------------------------------------------------------------
# _current_branch()
# ---------------------------------------------------------------------------


class TestCurrentBranch:
    def test_returns_branch_from_head(self, tmp_path: Path) -> None:
        f = tmp_path / "HEAD"
        f.write_text("ref: refs/heads/claude/test-branch\n")
        with patch.object(subject, "_HEAD_FILE", f):
            assert subject._current_branch() == "claude/test-branch"

    def test_returns_none_on_detached_head(self, tmp_path: Path) -> None:
        f = tmp_path / "HEAD"
        f.write_text("a1b2c3d4e5f6a1b2c3d4e5f6a1b2c3d4e5f6a1b2\n")
        with patch.object(subject, "_HEAD_FILE", f):
            assert subject._current_branch() is None

    def test_returns_none_when_head_missing(self, tmp_path: Path) -> None:
        with patch.object(subject, "_HEAD_FILE", tmp_path / "MISSING"):
            assert subject._current_branch() is None

    def test_returns_none_when_ref_empty(self, tmp_path: Path) -> None:
        f = tmp_path / "HEAD"
        f.write_text("ref: refs/heads/\n")
        with patch.object(subject, "_HEAD_FILE", f):
            assert subject._current_branch() is None


# ---------------------------------------------------------------------------
# _read_authorized_branches()
# ---------------------------------------------------------------------------


class TestReadAuthorizedBranches:
    def test_reads_set_from_file(self, tmp_path: Path) -> None:
        f = tmp_path / "CLAUDE_SESSION_BRANCH"
        f.write_text("claude/a\nclaude/b\n")
        with patch.object(subject, "_SESSION_BRANCH_FILE", f):
            assert subject._read_authorized_branches() == {"claude/a", "claude/b"}

    def test_empty_set_when_file_missing(self, tmp_path: Path) -> None:
        with patch.object(subject, "_SESSION_BRANCH_FILE", tmp_path / "MISSING"):
            assert subject._read_authorized_branches() == set()


# ---------------------------------------------------------------------------
# main() entry point
# ---------------------------------------------------------------------------


def test_main_emits_deny_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, "feat/wrong", monkeypatch)
    event = _bash_event("git commit -m wrong")
    output: list[str] = []
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    monkeypatch.setattr(
        "sys.stdout",
        type("FakeOut", (), {"write": lambda self, s: output.append(s)})(),
    )
    rc = subject.main()
    assert rc == 0
    parsed = json.loads("".join(output))
    assert parsed["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_main_silent_for_allowed_commit(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, _SESSION_BRANCH, monkeypatch)
    event = _bash_event("git commit -m ok")
    output: list[str] = []
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    monkeypatch.setattr(
        "sys.stdout",
        type("FakeOut", (), {"write": lambda self, s: output.append(s)})(),
    )
    rc = subject.main()
    assert rc == 0
    assert output == []


def test_main_handles_malformed_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))
    rc = subject.main()
    assert rc == 0
    assert "malformed" in capsys.readouterr().err


def test_main_handles_non_dict_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("[1, 2, 3]"))
    rc = subject.main()
    assert rc == 0
