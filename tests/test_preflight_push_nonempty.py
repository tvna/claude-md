from __future__ import annotations

import json
import subprocess
from typing import Any

import preflight_push_nonempty as subject
import pytest

pytestmark = pytest.mark.shard_preflight


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["git"], returncode, stdout=stdout, stderr="")


def _bash_event(command: str) -> dict[str, Any]:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _runner_for(shas: dict[str, str]) -> subject._Runner:
    """Build a runner that resolves ``rev-parse --verify --quiet <ref>`` to *shas*.

    A ref absent from *shas* resolves to a non-zero exit (unresolvable ref).
    """

    def runner(args: list[str]) -> subprocess.CompletedProcess[str]:
        assert args[:3] == ["rev-parse", "--verify", "--quiet"]
        ref = args[3]
        if ref in shas:
            return _completed(shas[ref])
        return _completed("", returncode=1)

    return runner


# ---------------------------------------------------------------------------
# Fast-pass cases
# ---------------------------------------------------------------------------


def test_decide_passthrough_non_bash_tool() -> None:
    event = {"tool_name": "Write", "tool_input": {"command": "git push"}}
    assert subject.decide(event, runner=_runner_for({})) is None


def test_decide_passthrough_bash_non_push() -> None:
    r = _runner_for({"HEAD": "aaa", "origin/main": "aaa"})
    assert subject.decide(_bash_event("git status"), runner=r) is None
    assert subject.decide(_bash_event("git commit -m msg"), runner=r) is None
    # Commit message that embeds "git\n  push" mid-text must not trigger.
    assert subject.decide(_bash_event('git commit -m "blocks git\n  push calls"'), runner=r) is None


def test_decide_passthrough_empty_command() -> None:
    assert subject.decide({"tool_name": "Bash", "tool_input": {}}, runner=_runner_for({})) is None


# ---------------------------------------------------------------------------
# Core gate: HEAD == base tip
# ---------------------------------------------------------------------------


def test_decide_denies_push_when_head_equals_base() -> None:
    r = _runner_for({"HEAD": "deadbeef", "origin/main": "deadbeef"})
    result = subject.decide(_bash_event("git push origin HEAD:session"), runner=r)
    assert result is not None
    out = result["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    reason = out["permissionDecisionReason"]
    assert "no new work" in reason
    assert "#1130" in reason


def test_decide_allows_push_when_head_advanced() -> None:
    r = _runner_for({"HEAD": "feedface", "origin/main": "deadbeef"})
    assert subject.decide(_bash_event("git push origin HEAD:session"), runner=r) is None


def test_decide_denies_rtk_rewritten_empty_push() -> None:
    # The rtk auto-rewrite hook prefixes ``git push`` with ``rtk`` (#1199); the
    # empty-push gate must still fire when HEAD has not advanced past the base.
    r = _runner_for({"HEAD": "deadbeef", "origin/main": "deadbeef"})
    result = subject.decide(_bash_event("rtk git push origin HEAD:session"), runner=r)
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_decide_denies_push_with_set_upstream_flag() -> None:
    r = _runner_for({"HEAD": "deadbeef", "origin/main": "deadbeef"})
    result = subject.decide(_bash_event("git push -u origin HEAD:session"), runner=r)
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


# ---------------------------------------------------------------------------
# Fail-open cases
# ---------------------------------------------------------------------------


def test_decide_allows_when_base_ref_missing() -> None:
    # Fresh clone with no origin/main ref locally: cannot compare, fail-open.
    r = _runner_for({"HEAD": "deadbeef"})
    assert subject.decide(_bash_event("git push origin HEAD:session"), runner=r) is None


def test_decide_allows_when_head_unresolvable() -> None:
    r = _runner_for({"origin/main": "deadbeef"})
    assert subject.decide(_bash_event("git push"), runner=r) is None


def test_decide_allows_on_runner_error() -> None:
    def boom(_args: list[str]) -> subprocess.CompletedProcess[str]:
        raise OSError("git not found")

    assert subject.decide(_bash_event("git push"), runner=boom) is None


def test_decide_allows_delete_push() -> None:
    # A deletion ships no HEAD; even when HEAD == base it must not be blocked.
    r = _runner_for({"HEAD": "deadbeef", "origin/main": "deadbeef"})
    assert subject.decide(_bash_event("git push origin --delete session"), runner=r) is None
    assert subject.decide(_bash_event("git push origin -d session"), runner=r) is None


def test_decide_allows_dry_run_push() -> None:
    r = _runner_for({"HEAD": "deadbeef", "origin/main": "deadbeef"})
    assert subject.decide(_bash_event("git push --dry-run origin HEAD:session"), runner=r) is None
    assert subject.decide(_bash_event("git push -n origin HEAD:session"), runner=r) is None


def test_skip_flag_regex_not_fooled_by_substring() -> None:
    # A branch literally named "-delete"-ish must not falsely match the skip flags.
    r = _runner_for({"HEAD": "deadbeef", "origin/main": "deadbeef"})
    result = subject.decide(_bash_event("git push origin HEAD:feature-delete-thing"), runner=r)
    assert result is not None
    assert result["hookSpecificOutput"]["permissionDecision"] == "deny"


# ---------------------------------------------------------------------------
# main() entry point
# ---------------------------------------------------------------------------


def test_main_emits_deny_json(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    event = _bash_event("git push origin HEAD:session")

    def fake_decide(e: dict[str, Any], **_: Any) -> dict[str, Any] | None:
        return subject._deny("test reason")

    monkeypatch.setattr(subject, "decide", fake_decide)

    output: list[str] = []
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    monkeypatch.setattr("sys.stdout", type("FakeOut", (), {"write": lambda self, s: output.append(s)})())

    rc = subject.main()
    assert rc == 0
    parsed = json.loads("".join(output))
    assert parsed["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_main_silent_for_non_push(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    event = _bash_event("git status")
    output: list[str] = []
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(event)))
    monkeypatch.setattr("sys.stdout", type("FakeOut", (), {"write": lambda self, s: output.append(s)})())
    monkeypatch.setattr(subject, "decide", lambda e, **kw: None)

    rc = subject.main()
    assert rc == 0
    assert output == []


def test_main_handles_malformed_json(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))
    rc = subject.main()
    assert rc == 0
    assert "malformed" in capsys.readouterr().err
