from __future__ import annotations

import subprocess
from typing import Any

import preflight_push_base as subject
import pytest

pytestmark = pytest.mark.shard_preflight


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["python3"], returncode, stdout=stdout, stderr="")


def _completed_err(stderr: str, returncode: int = 1) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["python3"], returncode, stdout="", stderr=stderr)


def _bash_event(command: str) -> dict[str, Any]:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


# ---------------------------------------------------------------------------
# Fast-pass cases
# ---------------------------------------------------------------------------


def test_decide_passthrough_non_bash_tool() -> None:
    event = {"tool_name": "Write", "tool_input": {"command": "git push"}}
    assert subject.decide(event) is None


def test_decide_passthrough_bash_non_push() -> None:
    assert subject.decide(_bash_event("git status")) is None
    assert subject.decide(_bash_event("ls -la")) is None
    assert subject.decide(_bash_event("git commit -m msg")) is None
    # Commit message containing "git\n  push" embedded mid-text must not trigger
    assert subject.decide(_bash_event('git commit -m "blocks git\n  push calls"')) is None


def test_decide_passthrough_empty_command() -> None:
    assert subject.decide({"tool_name": "Bash", "tool_input": {}}) is None


# ---------------------------------------------------------------------------
# Push detection
# ---------------------------------------------------------------------------


def test_decide_allows_push_when_branch_fresh() -> None:
    def fake_runner(*_args: Any, **_kw: Any) -> subprocess.CompletedProcess[str]:
        return _completed("OK: branch contains base (HEAD contains FETCH_HEAD)")

    assert subject.decide(_bash_event("git push origin my-branch"), runner=fake_runner) is None


def test_decide_denies_push_when_branch_behind() -> None:
    def fake_runner(*_args: Any, **_kw: Any) -> subprocess.CompletedProcess[str]:
        return _completed_err("::error::This branch is out-of-date with the base branch.")

    result = subject.decide(_bash_event("git push"), runner=fake_runner)
    assert result is not None
    reason = result["hookSpecificOutput"]["permissionDecisionReason"]
    assert "out-of-date" in reason
    assert "Repair" in reason
    assert "merge FETCH_HEAD --no-edit" in reason
    # repair command must not recommend rebase (rewrites SHAs, conflicts with force-push rules)
    assert "git rebase" not in reason


def test_decide_denies_push_with_force_flag() -> None:
    def fake_runner(*_args: Any, **_kw: Any) -> subprocess.CompletedProcess[str]:
        return _completed_err("::error::This branch is out-of-date with the base branch.")

    result = subject.decide(_bash_event("git push --force-with-lease origin branch"), runner=fake_runner)
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_decide_allows_on_runner_error() -> None:
    def fake_runner(*_args: Any, **_kw: Any) -> subprocess.CompletedProcess[str]:
        raise OSError("network unreachable")

    # Fail-open: hook errors must not block the push
    assert subject.decide(_bash_event("git push"), runner=fake_runner) is None


def test_decide_detects_rtk_rewritten_push() -> None:
    # The rtk auto-rewrite hook turns ``git push`` into ``rtk git push`` (#1199);
    # the gate must still fire so the branch-base check is not bypassed.
    def fake_runner(*_args: Any, **_kw: Any) -> subprocess.CompletedProcess[str]:
        return _completed_err("::error::This branch is out-of-date with the base branch.")

    result = subject.decide(_bash_event("rtk git push origin my-branch"), runner=fake_runner)
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"
