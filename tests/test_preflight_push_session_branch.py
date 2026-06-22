"""Tests for scripts/preflight_push_session_branch.py.

Refs #785. Verifies that the PreToolUse hook blocks git push commands that
target a branch other than the session-designated branch and allows pushes
that correctly target the session branch (either directly or via
local:remote refspec syntax).
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import preflight_push_session_branch as subject
import pytest

pytestmark = pytest.mark.shard_preflight

_SESSION_BRANCH = "claude/stoic-johnson-ryJlF"


def _bash_event(command: str) -> dict[str, Any]:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _with_session(
    branches: str | set[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    authorized = {branches} if isinstance(branches, str) else set(branches)
    monkeypatch.setattr(subject, "_read_authorized_branches", lambda: authorized)


# ---------------------------------------------------------------------------
# decide() -- environment gate
# ---------------------------------------------------------------------------


def test_decide_passthrough_when_not_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("CLAUDE_CODE_REMOTE", raising=False)
    assert subject.decide(_bash_event("git push origin feat/x")) is None


def test_decide_passthrough_when_remote_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "false")
    assert subject.decide(_bash_event("git push origin feat/x")) is None


def test_decide_passthrough_non_bash_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, monkeypatch)
    event = {"tool_name": "Write", "tool_input": {"command": "git push"}}
    assert subject.decide(event) is None


def test_decide_passthrough_bash_non_push(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, monkeypatch)
    assert subject.decide(_bash_event("git status")) is None
    assert subject.decide(_bash_event("git commit -m msg")) is None
    assert subject.decide(_bash_event("ls -la")) is None


def test_decide_passthrough_no_session_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    # Empty authorized set (bootstrap / unrecorded session) -- fail-open.
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.setattr(subject, "_read_authorized_branches", set)
    assert subject.decide(_bash_event("git push origin other-branch")) is None


# ---------------------------------------------------------------------------
# decide() -- no explicit refspec (fail-open)
# ---------------------------------------------------------------------------


def test_decide_allows_push_no_args(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, monkeypatch)
    assert subject.decide(_bash_event("git push")) is None


def test_decide_allows_push_remote_only(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, monkeypatch)
    assert subject.decide(_bash_event("git push origin")) is None


# ---------------------------------------------------------------------------
# decide() -- allowed pushes
# ---------------------------------------------------------------------------


def test_decide_allows_push_to_session_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, monkeypatch)
    assert subject.decide(_bash_event(f"git push origin {_SESSION_BRANCH}")) is None


def test_decide_allows_push_u_to_session_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, monkeypatch)
    assert subject.decide(_bash_event(f"git push -u origin {_SESSION_BRANCH}")) is None


def test_decide_allows_local_colon_session_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, monkeypatch)
    cmd = f"git push origin feat/other:{_SESSION_BRANCH}"
    assert subject.decide(_bash_event(cmd)) is None


def test_decide_allows_head_colon_session_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, monkeypatch)
    cmd = f"git push origin HEAD:{_SESSION_BRANCH}"
    assert subject.decide(_bash_event(cmd)) is None


def test_decide_allows_forced_push_to_session_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, monkeypatch)
    cmd = f"git push --force-with-lease origin {_SESSION_BRANCH}"
    assert subject.decide(_bash_event(cmd)) is None


def test_decide_allows_push_to_head(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, monkeypatch)
    assert subject.decide(_bash_event("git push origin HEAD")) is None


# ---------------------------------------------------------------------------
# decide() -- denied pushes
# ---------------------------------------------------------------------------


def test_decide_denies_push_to_other_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, monkeypatch)
    result = subject.decide(_bash_event("git push origin feat/my-feature"))
    assert result is not None
    reason = result["hookSpecificOutput"]["permissionDecisionReason"]
    assert _SESSION_BRANCH in reason
    assert "feat/my-feature" in reason
    assert "permissionDecision" in result["hookSpecificOutput"]
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_decide_denies_push_u_to_other_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, monkeypatch)
    result = subject.decide(_bash_event("git push -u origin fix/bug-123"))
    assert result is not None
    reason = result["hookSpecificOutput"]["permissionDecisionReason"]
    assert "fix/bug-123" in reason


def test_decide_denies_local_colon_wrong_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, monkeypatch)
    result = subject.decide(_bash_event("git push origin local-branch:wrong-branch"))
    assert result is not None
    reason = result["hookSpecificOutput"]["permissionDecisionReason"]
    assert "wrong-branch" in reason


def test_decide_deny_message_names_session_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, monkeypatch)
    result = subject.decide(_bash_event("git push origin feat/xyz"))
    assert result is not None
    reason = result["hookSpecificOutput"]["permissionDecisionReason"]
    assert _SESSION_BRANCH in reason
    assert f"<local-branch>:{_SESSION_BRANCH}" in reason


def test_decide_deny_message_references_issue(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, monkeypatch)
    result = subject.decide(_bash_event("git push origin feat/xyz"))
    assert result is not None
    reason = result["hookSpecificOutput"]["permissionDecisionReason"]
    assert "#785" in reason


def test_decide_denies_force_push_to_other_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, monkeypatch)
    result = subject.decide(_bash_event("git push -f origin other-branch"))
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


# ---------------------------------------------------------------------------
# decide() -- multi-factor authorized set (Refs #1513)
# ---------------------------------------------------------------------------


def test_decide_allows_push_to_any_set_member(monkeypatch: pytest.MonkeyPatch) -> None:
    # Paired work / post-merge: the set carries more than one branch; a push
    # to EITHER member is allowed.
    branch_b = "claude/follow-up-branch"
    _with_session({_SESSION_BRANCH, branch_b}, monkeypatch)
    assert subject.decide(_bash_event(f"git push origin {_SESSION_BRANCH}")) is None
    assert subject.decide(_bash_event(f"git push origin {branch_b}")) is None


def test_decide_denies_main_even_when_in_set(monkeypatch: pytest.MonkeyPatch) -> None:
    # Invariant 1: a protected branch is rejected even if a stale entry names it.
    _with_session({_SESSION_BRANCH, "main"}, monkeypatch)
    result = subject.decide(_bash_event("git push origin main"))
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_decide_denies_unauthorized_prior_session_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # Invariant 2: a prior session's branch never added to the set stays denied.
    _with_session(_SESSION_BRANCH, monkeypatch)
    result = subject.decide(
        _bash_event("git push origin claude/hopeful-turing-pex8i2")
    )
    assert result is not None
    reason = result["hookSpecificOutput"]["permissionDecisionReason"]
    assert "claude/hopeful-turing-pex8i2" in reason
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_decide_denies_rtk_rewritten_push_to_other_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    # The rtk auto-rewrite hook prefixes ``git push`` with ``rtk`` (#1199); the
    # session-branch gate must still detect it and deny the off-branch push.
    _with_session(_SESSION_BRANCH, monkeypatch)
    result = subject.decide(_bash_event("rtk git push origin feat/my-feature"))
    assert result is not None
    reason = result["hookSpecificOutput"]["permissionDecisionReason"]
    assert "feat/my-feature" in reason
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_decide_allows_rtk_rewritten_push_to_session_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, monkeypatch)
    assert subject.decide(_bash_event(f"rtk git push origin {_SESSION_BRANCH}")) is None


# ---------------------------------------------------------------------------
# _extract_push_remote_ref() -- parser unit tests
# ---------------------------------------------------------------------------


class TestExtractPushRemoteRef:
    def test_returns_none_for_no_push(self) -> None:
        assert subject._extract_push_remote_ref("git status") is None

    def test_returns_none_for_push_no_args(self) -> None:
        assert subject._extract_push_remote_ref("git push") is None

    def test_returns_none_for_push_remote_only(self) -> None:
        assert subject._extract_push_remote_ref("git push origin") is None

    def test_returns_branch_for_simple_push(self) -> None:
        assert subject._extract_push_remote_ref("git push origin feat/x") == "feat/x"

    def test_returns_remote_ref_for_colon_refspec(self) -> None:
        assert subject._extract_push_remote_ref("git push origin local:remote") == "remote"

    def test_strips_force_prefix(self) -> None:
        assert subject._extract_push_remote_ref("git push origin +feat/x") == "feat/x"

    def test_handles_u_flag(self) -> None:
        assert subject._extract_push_remote_ref("git push -u origin feat/x") == "feat/x"

    def test_handles_set_upstream_flag(self) -> None:
        assert subject._extract_push_remote_ref("git push --set-upstream origin feat/x") == "feat/x"

    def test_handles_force_flag(self) -> None:
        assert subject._extract_push_remote_ref("git push -f origin feat/x") == "feat/x"

    def test_handles_force_with_lease(self) -> None:
        assert subject._extract_push_remote_ref("git push --force-with-lease origin feat/x") == "feat/x"

    def test_handles_double_dash_separator(self) -> None:
        assert subject._extract_push_remote_ref("git push origin -- feat/x") == "feat/x"

    def test_handles_flag_with_value_equals_form(self) -> None:
        assert subject._extract_push_remote_ref("git push --push-option=ci-skip origin feat/x") == "feat/x"

    def test_head_colon_remote(self) -> None:
        assert subject._extract_push_remote_ref("git push origin HEAD:session/branch") == "session/branch"

    def test_stops_at_shell_and(self) -> None:
        # The parser captures up to the shell operator; extra commands ignored.
        ref = subject._extract_push_remote_ref("git push origin feat/x && echo done")
        assert ref == "feat/x"


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
    _with_session(_SESSION_BRANCH, monkeypatch)
    event = _bash_event("git push origin feat/wrong")
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


def test_main_silent_for_allowed_push(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, monkeypatch)
    event = _bash_event(f"git push origin {_SESSION_BRANCH}")
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
