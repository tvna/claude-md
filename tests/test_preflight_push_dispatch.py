"""Table-driven tests for the consolidated push gate dispatcher (#2410).

The dispatcher wires the four push-specific gates behind one PreToolUse process.
These tests prove the wiring preserves the pre-consolidation behaviour:

* fixed evaluation order with first-deny-wins (later checks short-circuit),
* verbatim pass-through of each gate's deny decision (no transformation),
* per-check deny-text equivalence against the real gate ``decide`` functions,
* audit-mode immunity: ``CLAUDE_GATE_MODE=audit`` cannot suppress a push deny
  (the ``auditable=False`` regression), and
* the fast-pass / fail-open surface (non-Bash, non-push, malformed stdin).
"""

from __future__ import annotations

import io
import json
import subprocess
from typing import Any

import preflight_push_base
import preflight_push_dispatch as subject
import preflight_push_nonempty
import preflight_push_session_branch
import preflight_push_unsigned_commits
import pytest

pytestmark = pytest.mark.shard_preflight


def _bash_event(command: str) -> dict[str, Any]:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _completed(stdout: str = "", stderr: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["git"], returncode, stdout=stdout, stderr=stderr)


def _reason(decision: dict[str, Any]) -> str:
    return decision["hookSpecificOutput"]["permissionDecisionReason"]


# ---------------------------------------------------------------------------
# Fast-pass surface (real _CHECKS; the top-level regex short-circuits)
# ---------------------------------------------------------------------------


def test_passthrough_non_bash_tool() -> None:
    assert subject.decide({"tool_name": "Write", "tool_input": {"command": "git push"}}) is None


def test_passthrough_non_push_command() -> None:
    assert subject.decide(_bash_event("git status")) is None
    assert subject.decide(_bash_event("ls -la")) is None
    assert subject.decide(_bash_event("git commit -m msg")) is None


def test_passthrough_empty_command() -> None:
    assert subject.decide({"tool_name": "Bash", "tool_input": {}}) is None


def test_passthrough_push_word_embedded_in_commit_message() -> None:
    # A commit message that merely mentions push mid-text must not trip the gate.
    assert subject.decide(_bash_event('git commit -m "blocks git\n  push calls"')) is None


def test_surface_declares_push() -> None:
    assert frozenset({"push"}) == subject.HOOK_GIT_SUBCOMMANDS


# ---------------------------------------------------------------------------
# Order and first-deny-wins
# ---------------------------------------------------------------------------


def test_first_deny_wins_short_circuits_later_checks(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def stub(name: str, denies: bool):
        def check(_event: dict[str, Any]) -> dict[str, Any] | None:
            calls.append(name)
            return {"sentinel": name} if denies else None

        return check

    monkeypatch.setattr(
        subject,
        "_CHECKS",
        (stub("first", False), stub("second", True), stub("third", False)),
    )
    result = subject.decide(_bash_event("git push origin branch"))
    assert result == {"sentinel": "second"}
    # The third check must never run once the second denies.
    assert calls == ["first", "second"]


def test_all_checks_pass_allows_push(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def passing(name: str):
        def check(_event: dict[str, Any]) -> dict[str, Any] | None:
            calls.append(name)
            return None

        return check

    monkeypatch.setattr(subject, "_CHECKS", (passing("a"), passing("b"), passing("c")))
    assert subject.decide(_bash_event("git push origin branch")) is None
    assert calls == ["a", "b", "c"]  # every check consulted when none denies


def test_dispatcher_wires_the_four_gates_in_fixed_order() -> None:
    # Guards the registration order the consolidated hook replaces (F7/F10).
    assert (
        preflight_push_unsigned_commits.decide,
        preflight_push_base.decide,
        preflight_push_session_branch.decide,
        preflight_push_nonempty.decide,
    ) == subject._CHECKS


def test_deny_decision_passed_through_verbatim(monkeypatch: pytest.MonkeyPatch) -> None:
    # The dispatcher returns the check's object unchanged (identity), so a gate's
    # deny text can never be rewritten in transit.
    sentinel = preflight_push_unsigned_commits._deny(["abc123def456"])
    monkeypatch.setattr(subject, "_CHECKS", (lambda _e: None, lambda _e: sentinel))
    result = subject.decide(_bash_event("git push origin branch"))
    assert result is sentinel
    assert "UNSIGNED" in _reason(result)


# ---------------------------------------------------------------------------
# Per-check deny-text equivalence against the real gate decide() functions
# ---------------------------------------------------------------------------


def test_equivalence_push_base_deny(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_runner(*_a: Any, **_k: Any) -> subprocess.CompletedProcess[str]:
        return _completed(stderr="::error::This branch is out-of-date with the base branch.", returncode=1)

    event = _bash_event("git push")
    expected = preflight_push_base.decide(event, runner=fake_runner)
    monkeypatch.setattr(subject, "_CHECKS", (lambda e: preflight_push_base.decide(e, runner=fake_runner),))
    got = subject.decide(event)
    assert got == expected
    assert got is not None
    assert "out-of-date" in _reason(got)


def test_equivalence_push_nonempty_deny(monkeypatch: pytest.MonkeyPatch) -> None:
    def fake_runner(_args: list[str]) -> subprocess.CompletedProcess[str]:
        # HEAD and origin/main resolve to the same sha -> nothing new to push.
        return _completed(stdout="deadbeef\n")

    event = _bash_event("git push origin branch")
    expected = preflight_push_nonempty.decide(event, runner=fake_runner)
    monkeypatch.setattr(subject, "_CHECKS", (lambda e: preflight_push_nonempty.decide(e, runner=fake_runner),))
    got = subject.decide(event)
    assert got == expected
    assert got is not None
    assert "ships no new work" in _reason(got)


def test_equivalence_push_session_branch_deny(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")
    monkeypatch.setattr(preflight_push_session_branch, "_read_authorized_branches", lambda: {"claude/issue-1-abc"})
    event = _bash_event("git push origin HEAD:some-other-branch")
    expected = preflight_push_session_branch.decide(event)
    monkeypatch.setattr(subject, "_CHECKS", (preflight_push_session_branch.decide,))
    got = subject.decide(event)
    assert got == expected
    assert got is not None
    assert "some-other-branch" in _reason(got)


def test_equivalence_push_unsigned_commits_deny(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CLAUDE_CODE_REMOTE", "true")

    def fake_runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        # rev-parse: resolve any ref to a sha; refs/remotes lookups miss (new
        # branch) so commits_to_push falls to "reachable from local tip".
        if args[:1] == ["rev-parse"]:
            ref = args[-1]
            if ref.startswith("refs/remotes/"):
                return _completed(returncode=1)
            return _completed(stdout="c0ffee1234567890\n")
        if args[:1] == ["rev-list"]:
            return _completed(stdout="c0ffee1234567890\n")
        if args[:1] == ["cat-file"]:
            # A raw commit object with NO gpgsig header -> classified unsigned.
            return _completed(stdout="tree deadbeef\nauthor x <x@x> 0 +0000\n\nmsg\n")
        return _completed(returncode=1)

    event = _bash_event("git push origin HEAD:claude/issue-1-abc")
    expected = preflight_push_unsigned_commits.decide(event, runner=fake_runner)
    monkeypatch.setattr(subject, "_CHECKS", (lambda e: preflight_push_unsigned_commits.decide(e, runner=fake_runner),))
    got = subject.decide(event)
    assert got == expected
    assert got is not None
    assert "UNSIGNED" in _reason(got)


# ---------------------------------------------------------------------------
# main(): audit-mode immunity and the stdin/stdout contract
# ---------------------------------------------------------------------------


def _run_main(monkeypatch: pytest.MonkeyPatch, event: dict[str, Any]) -> list[str]:
    output: list[str] = []
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    monkeypatch.setattr("sys.stdout", type("FakeOut", (), {"write": lambda self, s: output.append(s)})())
    rc = subject.main()
    assert rc == 0
    return output


def test_main_deny_survives_audit_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    # auditable=False regression: CLAUDE_GATE_MODE=audit must NOT suppress a push
    # deny surfaced by the dispatcher.
    from _hook_runtime import build_deny

    monkeypatch.setenv("CLAUDE_GATE_MODE", "audit")
    monkeypatch.setattr(subject, "_CHECKS", (lambda _e: build_deny("dispatcher test deny"),))
    output = _run_main(monkeypatch, _bash_event("git push origin branch"))
    parsed = json.loads("".join(output))
    assert parsed["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_main_silent_for_non_push(monkeypatch: pytest.MonkeyPatch) -> None:
    assert _run_main(monkeypatch, _bash_event("git status")) == []


def test_main_handles_malformed_json(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))
    assert subject.main() == 0
    assert "malformed" in capsys.readouterr().err
