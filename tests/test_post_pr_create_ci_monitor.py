from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import post_pr_create_ci_monitor as monitor
import pytest

pytestmark = pytest.mark.shard_preflight

_CI_WATCH_SCRIPT = str(Path(__file__).resolve().parent.parent / "scripts" / "_ci_watch.py")


def test_extract_pr_url_from_string_response() -> None:
    response = "created https://github.com/tvna/claude-md/pull/723"

    assert monitor.extract_pr_url(response) == "https://github.com/tvna/claude-md/pull/723"


def test_build_watch_command_prefers_pr_url() -> None:
    event = {
        "tool_name": monitor.TARGET_TOOL,
        "tool_response": {"url": "https://github.com/tvna/claude-md/pull/723"},
        "tool_input": {"owner": "tvna", "repo": "claude-md"},
    }
    result = monitor.build_watch_command(event)
    assert result is not None
    cmd, ref = result

    assert cmd == [sys.executable, _CI_WATCH_SCRIPT, "--pr", "https://github.com/tvna/claude-md/pull/723"]
    assert ref == "https://github.com/tvna/claude-md/pull/723"


def test_build_watch_command_uses_number_and_repo() -> None:
    event = {
        "tool_name": monitor.TARGET_TOOL,
        "tool_response": {"number": 723},
        "tool_input": {"owner": "tvna", "repo": "claude-md"},
    }
    result = monitor.build_watch_command(event)
    assert result is not None
    cmd, ref = result

    assert cmd == [sys.executable, _CI_WATCH_SCRIPT, "--pr", "723", "--repo", "tvna/claude-md"]
    assert ref == "723"


def test_decide_ignores_non_target_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_start(*args: object, **kwargs: object) -> Path:
        raise AssertionError("monitor must not start")

    monkeypatch.setattr(monitor, "start_monitor", fail_start)

    assert monitor.decide({"tool_name": "mcp__github__update_pull_request"}) is None


def test_decide_starts_monitor_and_returns_context(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls: list[tuple[list[str], str | None]] = []
    log_path = tmp_path / "monitor.log"

    def fake_start(argv: list[str], *, cwd: str | None = None) -> Path:
        calls.append((argv, cwd))
        return log_path

    monkeypatch.setattr(monitor, "start_monitor", fake_start)
    event = {
        "tool_name": monitor.TARGET_TOOL,
        "cwd": "/repo",
        "tool_response": {"url": "https://github.com/tvna/claude-md/pull/723"},
    }

    output = monitor.decide(event)

    assert calls == [
        (
            [sys.executable, _CI_WATCH_SCRIPT, "--pr", "https://github.com/tvna/claude-md/pull/723"],
            "/repo",
        )
    ]
    assert output is not None
    hook = output["hookSpecificOutput"]
    assert hook["hookEventName"] == "PostToolUse"
    ctx = hook["additionalContext"]
    assert "polling/heartbeat CI monitor started automatically" in ctx
    assert str(log_path) in ctx
    assert "NOT webhook-backed" in ctx
    assert "subscribe_pr_activity" in ctx
    assert "early-failure watch phase" in ctx
    assert "terminal state" in ctx
    assert "steady-state heartbeat" in ctx


def test_decide_reports_missing_pr_reference() -> None:
    output = monitor.decide({"tool_name": monitor.TARGET_TOOL, "tool_response": {"ok": True}})

    assert output is not None
    ctx = output["hookSpecificOutput"]["additionalContext"]
    assert "did not contain a PR URL or number" in ctx
    assert "subscribe_pr_activity" in ctx
    assert "early-failure watch phase" in ctx
    assert "steady-state heartbeat" in ctx


def test_decide_reports_start_failure_with_early_failure_phase(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(argv: list[str], *, cwd: str | None = None) -> Path:
        raise OSError("no python on PATH")

    monkeypatch.setattr(monitor, "start_monitor", boom)
    event = {
        "tool_name": monitor.TARGET_TOOL,
        "tool_response": {"url": "https://github.com/tvna/claude-md/pull/723"},
    }

    output = monitor.decide(event)

    assert output is not None
    ctx = output["hookSpecificOutput"]["additionalContext"]
    assert "failed to start automatically" in ctx
    assert "early-failure watch phase" in ctx
    assert "steady-state heartbeat" in ctx
    assert "subscribe_pr_activity" in ctx


def test_start_monitor_launches_detached_process(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    popen_calls: list[dict[str, object]] = []

    class FakePopen:
        def __init__(self, argv: list[str], **kwargs: object) -> None:
            popen_calls.append({"argv": argv, **kwargs})

    monkeypatch.setattr(subprocess, "Popen", FakePopen)
    monkeypatch.setattr(monitor.tempfile, "gettempdir", lambda: str(tmp_path))

    argv = [sys.executable, _CI_WATCH_SCRIPT, "--pr", "723"]
    log_path = monitor.start_monitor(argv, cwd="/repo")

    assert log_path == tmp_path / "claude-md-pr-ci-monitor-723.log"
    assert popen_calls[0]["argv"] == argv
    assert popen_calls[0]["cwd"] == "/repo"
    assert popen_calls[0]["stdin"] == subprocess.DEVNULL
    assert popen_calls[0]["stderr"] == subprocess.STDOUT
    assert popen_calls[0]["start_new_session"] is True


def test_main_emits_post_tool_context(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(monitor, "start_monitor", lambda argv, *, cwd=None: Path("/tmp/monitor.log"))
    event = {
        "tool_name": monitor.TARGET_TOOL,
        "tool_response": {"url": "https://github.com/tvna/claude-md/pull/723"},
    }
    monkeypatch.setattr("sys.stdin", type("Input", (), {"read": lambda self: json.dumps(event)})())

    assert monitor.main([]) == 0

    out = json.loads(capsys.readouterr().out)
    assert out["hookSpecificOutput"]["hookEventName"] == "PostToolUse"
