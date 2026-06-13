"""Tests for scripts/preflight_session_branch_authz.py.

Refs #1658, #1632, #785. Verifies the early branch-authorization gate denies
creating/switching to an unauthorized branch (Bash) and editing a repo file
while on an unauthorized branch (Edit/Write), before any work is done, while
leaving authorized-branch work and out-of-repo edits untouched. Mirrors the
test structure of ``tests/test_preflight_commit_session_branch.py``.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any
from unittest.mock import patch

import preflight_session_branch_authz as subject
import pytest

pytestmark = pytest.mark.shard_preflight

_SESSION_BRANCH = "claude/stoic-johnson-ryJlF"


def _bash_event(command: str) -> dict[str, Any]:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _edit_event(file_path: str, tool: str = "Edit") -> dict[str, Any]:
    key = "notebook_path" if tool == "NotebookEdit" else "file_path"
    return {"tool_name": tool, "tool_input": {key: file_path}}


def _repo_path(rel: str = "scripts/example.py") -> str:
    return str(subject.REPO_ROOT / rel)


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
    assert subject.decide(_bash_event("git switch -c feat/x")) is None
    assert subject.decide(_edit_event(_repo_path())) is None


def test_decide_passthrough_when_remote_false(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "false")
    assert subject.decide(_bash_event("git switch -c feat/x")) is None


def test_decide_passthrough_unrelated_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, "feat/other", monkeypatch)
    event = {"tool_name": "Read", "tool_input": {"file_path": _repo_path()}}
    assert subject.decide(event) is None


def test_decide_passthrough_bash_non_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, _SESSION_BRANCH, monkeypatch)
    assert subject.decide(_bash_event("git status")) is None
    assert subject.decide(_bash_event("git commit -m x")) is None
    assert subject.decide(_bash_event("ls -la")) is None


def test_decide_passthrough_no_session_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.setattr(subject, "_read_authorized_branches", set)
    monkeypatch.setattr(subject, "_current_branch", lambda: "feat/other")
    assert subject.decide(_bash_event("git switch -c feat/x")) is None
    assert subject.decide(_edit_event(_repo_path())) is None


# ---------------------------------------------------------------------------
# decide() -- Bash branch creation / switch
# ---------------------------------------------------------------------------


def test_denies_switch_create_unauthorized(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, _SESSION_BRANCH, monkeypatch)
    result = subject.decide(_bash_event("git switch -c claude/issue-1651-foo"))
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    reason = result["hookSpecificOutput"]["permissionDecisionReason"]
    assert "claude/issue-1651-foo" in reason
    assert _SESSION_BRANCH in reason


def test_denies_checkout_b_unauthorized(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, _SESSION_BRANCH, monkeypatch)
    result = subject.decide(_bash_event("git checkout -b feat/elsewhere"))
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "feat/elsewhere" in result["hookSpecificOutput"]["permissionDecisionReason"]


def test_denies_plain_switch_unauthorized(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, _SESSION_BRANCH, monkeypatch)
    result = subject.decide(_bash_event("git switch other/branch"))
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    assert "other/branch" in result["hookSpecificOutput"]["permissionDecisionReason"]


def test_denies_create_equals_form(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, _SESSION_BRANCH, monkeypatch)
    result = subject.decide(_bash_event("git switch --create=feat/eq"))
    assert result is not None
    assert "feat/eq" in result["hookSpecificOutput"]["permissionDecisionReason"]


def test_denies_chained_create(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, _SESSION_BRANCH, monkeypatch)
    cmd = "git fetch origin && git checkout -b feat/chained"
    result = subject.decide(_bash_event(cmd))
    assert result is not None
    assert "feat/chained" in result["hookSpecificOutput"]["permissionDecisionReason"]


def test_denies_switch_to_protected_main(monkeypatch: pytest.MonkeyPatch) -> None:
    # main is never authorized for commit/push, so switching to it to work is denied.
    _with_session({_SESSION_BRANCH, "main"}, _SESSION_BRANCH, monkeypatch)
    result = subject.decide(_bash_event("git switch main"))
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_allows_switch_to_authorized(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, _SESSION_BRANCH, monkeypatch)
    assert subject.decide(_bash_event(f"git switch {_SESSION_BRANCH}")) is None


def test_allows_recreate_authorized_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    # Recreating a branch whose name is already authorized is fine.
    _with_session(_SESSION_BRANCH, _SESSION_BRANCH, monkeypatch)
    assert subject.decide(_bash_event(f"git switch -c {_SESSION_BRANCH}")) is None


def test_allows_switch_to_any_set_member(monkeypatch: pytest.MonkeyPatch) -> None:
    branch_b = "claude/follow-up"
    _with_session({_SESSION_BRANCH, branch_b}, _SESSION_BRANCH, monkeypatch)
    assert subject.decide(_bash_event(f"git switch {branch_b}")) is None


def test_passthrough_plain_checkout(monkeypatch: pytest.MonkeyPatch) -> None:
    # Plain ``git checkout <arg>`` is ambiguous (branch vs pathspec); not gated
    # here -- the Edit/Write surface and commit-time gate cover it.
    _with_session(_SESSION_BRANCH, _SESSION_BRANCH, monkeypatch)
    assert subject.decide(_bash_event("git checkout other/branch")) is None
    assert subject.decide(_bash_event("git checkout README.md")) is None


def test_passthrough_detach(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, _SESSION_BRANCH, monkeypatch)
    assert subject.decide(_bash_event("git switch --detach abc123")) is None
    assert subject.decide(_bash_event("git switch -d abc123")) is None


def test_passthrough_checkout_pathspec_after_dashdash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _with_session(_SESSION_BRANCH, _SESSION_BRANCH, monkeypatch)
    assert subject.decide(_bash_event("git checkout -- some/file.py")) is None


def test_passthrough_switch_dash(monkeypatch: pytest.MonkeyPatch) -> None:
    # ``git switch -`` (previous branch) cannot be resolved statically -> fail open.
    _with_session(_SESSION_BRANCH, _SESSION_BRANCH, monkeypatch)
    assert subject.decide(_bash_event("git switch -")) is None


def test_passthrough_switch_text_in_commit_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A commit whose MESSAGE mentions an example switch/checkout command must
    # not be mistaken for a real branch operation (regression: the detection is
    # anchored to a segment head, not matched anywhere in the command).
    _with_session(_SESSION_BRANCH, _SESSION_BRANCH, monkeypatch)
    cmd = "git commit -m 'docs: explain git switch -c foo and git checkout -b bar'"
    assert subject.decide(_bash_event(cmd)) is None


def test_passthrough_switch_text_in_heredoc_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A heredoc commit body containing indented example commands must pass.
    _with_session(_SESSION_BRANCH, _SESSION_BRANCH, monkeypatch)
    cmd = (
        "git commit -F - <<'EOF'\n"
        "feat: add gate\n\n"
        "  Bash: deny git switch -c / git checkout -b / git switch <branch>\n"
        "EOF"
    )
    assert subject.decide(_bash_event(cmd)) is None


def test_passthrough_echoed_switch(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, _SESSION_BRANCH, monkeypatch)
    assert subject.decide(_bash_event("echo 'git switch -c feat/x'")) is None


# ---------------------------------------------------------------------------
# decide() -- Edit/Write first-edit surface
# ---------------------------------------------------------------------------


def test_denies_edit_on_unauthorized_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, "claude/issue-1651-foo", monkeypatch)
    result = subject.decide(_edit_event(_repo_path()))
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
    reason = result["hookSpecificOutput"]["permissionDecisionReason"]
    assert "claude/issue-1651-foo" in reason
    assert _SESSION_BRANCH in reason


@pytest.mark.parametrize("tool", ["Edit", "Write", "MultiEdit", "NotebookEdit"])
def test_denies_all_edit_tools_on_unauthorized_branch(
    tool: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    _with_session(_SESSION_BRANCH, "feat/wrong", monkeypatch)
    rel = "notebooks/x.ipynb" if tool == "NotebookEdit" else "scripts/x.py"
    result = subject.decide(_edit_event(_repo_path(rel), tool=tool))
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_allows_edit_on_authorized_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, _SESSION_BRANCH, monkeypatch)
    assert subject.decide(_edit_event(_repo_path())) is None


def test_allows_edit_outside_repo(monkeypatch: pytest.MonkeyPatch) -> None:
    # Plan files and other out-of-repo paths are unconstrained even on a
    # non-authorized branch.
    _with_session(_SESSION_BRANCH, "feat/wrong", monkeypatch)
    assert subject.decide(_edit_event("/tmp/claude-plans/plan.md")) is None


def test_passthrough_edit_detached_head(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, None, monkeypatch)
    assert subject.decide(_edit_event(_repo_path())) is None


def test_passthrough_edit_no_path(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, "feat/wrong", monkeypatch)
    assert subject.decide({"tool_name": "Edit", "tool_input": {}}) is None


def test_deny_message_references_issue(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, "feat/wrong", monkeypatch)
    result = subject.decide(_edit_event(_repo_path()))
    assert result is not None
    reason = result["hookSpecificOutput"]["permissionDecisionReason"]
    assert "#1658" in reason
    assert f"git switch {_SESSION_BRANCH}" in reason


# ---------------------------------------------------------------------------
# _resolve_target()
# ---------------------------------------------------------------------------


class TestResolveTarget:
    def test_switch_create_short(self) -> None:
        assert subject._resolve_target("switch", ["-c", "feat/x"]) == ("create", "feat/x")

    def test_switch_create_long(self) -> None:
        assert subject._resolve_target("switch", ["--create", "feat/x"]) == (
            "create",
            "feat/x",
        )

    def test_checkout_create(self) -> None:
        assert subject._resolve_target("checkout", ["-b", "feat/x"]) == ("create", "feat/x")

    def test_switch_plain(self) -> None:
        assert subject._resolve_target("switch", ["feat/x"]) == ("switch", "feat/x")

    def test_checkout_plain_not_gated(self) -> None:
        assert subject._resolve_target("checkout", ["feat/x"]) is None

    def test_detach_returns_none(self) -> None:
        assert subject._resolve_target("switch", ["--detach", "abc123"]) is None

    def test_dashdash_stops(self) -> None:
        assert subject._resolve_target("checkout", ["--", "feat/x"]) is None

    def test_create_missing_value(self) -> None:
        assert subject._resolve_target("switch", ["-c"]) is None

    def test_create_value_is_flag(self) -> None:
        assert subject._resolve_target("switch", ["-c", "--quiet"]) is None

    def test_orphan_checkout(self) -> None:
        assert subject._resolve_target("checkout", ["--orphan", "gh-pages"]) == (
            "create",
            "gh-pages",
        )


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


# ---------------------------------------------------------------------------
# _target_hint()
# ---------------------------------------------------------------------------


class TestTargetHint:
    def test_prefers_non_protected(self) -> None:
        assert subject._target_hint({"main", _SESSION_BRANCH}) == _SESSION_BRANCH

    def test_falls_back_to_protected_only(self) -> None:
        assert subject._target_hint({"main"}) == "main"


# ---------------------------------------------------------------------------
# main() entry point
# ---------------------------------------------------------------------------


def test_main_emits_deny_json(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, _SESSION_BRANCH, monkeypatch)
    event = _bash_event("git switch -c feat/wrong")
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


def test_main_silent_for_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    _with_session(_SESSION_BRANCH, _SESSION_BRANCH, monkeypatch)
    event = _bash_event(f"git switch {_SESSION_BRANCH}")
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
