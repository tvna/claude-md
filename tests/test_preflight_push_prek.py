from __future__ import annotations

import json
import subprocess
from typing import Any

import preflight_push_prek as subject
import pytest

pytestmark = pytest.mark.shard_preflight


def _completed(stdout: str = "", returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["python3"], returncode, stdout=stdout, stderr="")


def _completed_err(stderr: str, returncode: int = 1) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(["python3"], returncode, stdout="", stderr=stderr)


def _bash_event(command: str) -> dict[str, Any]:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _uv_runner(prek_ok: bool):
    """Build a fake runner: prek (uv) returns a passing or failing result."""

    def fake_runner(cmd: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
        return _completed("prek OK") if prek_ok else _completed_err("prek: trailing newline")

    return fake_runner


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
    assert subject.decide(_bash_event('git commit -m "blocks git\n  push calls"')) is None


def test_decide_passthrough_empty_command() -> None:
    assert subject.decide({"tool_name": "Bash", "tool_input": {}}) is None


# ---------------------------------------------------------------------------
# prek passes
# ---------------------------------------------------------------------------


def test_decide_allows_push_when_prek_passes() -> None:
    assert subject.decide(_bash_event("git push origin main"), runner=_uv_runner(True)) is None


def test_decide_allows_push_with_force_flag_when_prek_passes() -> None:
    assert subject.decide(_bash_event("git push --force-with-lease"), runner=_uv_runner(True)) is None


# ---------------------------------------------------------------------------
# prek check failures
# ---------------------------------------------------------------------------


def test_decide_denies_push_when_prek_fails() -> None:
    calls: list[list[str]] = []

    def fake_runner(cmd: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return _completed_err("Fixing trailing newline in translations.json")

    result = subject.decide(_bash_event("git push"), runner=fake_runner)
    assert result is not None
    reason = result["hookSpecificOutput"]["permissionDecisionReason"]
    assert "prek" in reason
    assert "Refs #901" in reason
    assert len(calls) == 1


def test_decide_failopen_on_prek_subprocess_error(capsys: pytest.CaptureFixture[str]) -> None:
    calls: list[list[str]] = []

    def fake_runner(cmd: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        raise OSError("uv not found")

    result = subject.decide(_bash_event("git push"), runner=fake_runner)
    assert result is None
    assert len(calls) == 1  # prek failed open; no further checks
    assert "warning" in capsys.readouterr().err


def test_decide_failopen_on_prek_timeout(capsys: pytest.CaptureFixture[str]) -> None:
    calls: list[list[str]] = []

    def fake_runner(cmd: list[str], **_kw: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        raise subprocess.TimeoutExpired(cmd, 60)

    result = subject.decide(_bash_event("git push"), runner=fake_runner)
    assert result is None
    assert "warning" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# main() entry point
# ---------------------------------------------------------------------------


def test_main_emits_deny_json(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    event = _bash_event("git push origin main")
    monkeypatch.setattr(subject, "decide", lambda e, **_: subject._deny("test reason"))

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


def test_main_silent_for_non_push(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    output: list[str] = []
    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(_bash_event("git status"))))
    monkeypatch.setattr(
        "sys.stdout",
        type("FakeOut", (), {"write": lambda self, s: output.append(s)})(),
    )
    monkeypatch.setattr(subject, "decide", lambda e, **kw: None)

    rc = subject.main()
    assert rc == 0
    assert output == []


def test_main_handles_malformed_json(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))
    rc = subject.main()
    assert rc == 0
    assert "malformed" in capsys.readouterr().err


def test_main_handles_non_dict_input(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps([1, 2, 3])))
    rc = subject.main()
    assert rc == 0
