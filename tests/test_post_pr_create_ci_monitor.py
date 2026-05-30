from __future__ import annotations

import json
import subprocess
from pathlib import Path

import post_pr_create_ci_monitor as monitor
import pytest

pytestmark = pytest.mark.shard_preflight


def test_extract_pr_url_from_string_response() -> None:
    response = "created https://github.com/tvna/claude-md/pull/723"

    assert monitor.extract_pr_url(response) == "https://github.com/tvna/claude-md/pull/723"


def test_build_watch_command_prefers_pr_url() -> None:
    event = {
        "tool_name": monitor.TARGET_TOOL,
        "tool_response": {"url": "https://github.com/tvna/claude-md/pull/723"},
        "tool_input": {"owner": "tvna", "repo": "claude-md"},
    }

    assert monitor.build_watch_command(event) == (
        ["gh", "pr", "checks", "https://github.com/tvna/claude-md/pull/723", "--watch"],
        "https://github.com/tvna/claude-md/pull/723",
    )


def test_build_watch_command_uses_number_and_repo() -> None:
    event = {
        "tool_name": monitor.TARGET_TOOL,
        "tool_response": {"number": 723},
        "tool_input": {"owner": "tvna", "repo": "claude-md"},
    }

    assert monitor.build_watch_command(event) == (
        ["gh", "pr", "checks", "723", "--watch", "--repo", "tvna/claude-md"],
        "723",
    )


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
            ["gh", "pr", "checks", "https://github.com/tvna/claude-md/pull/723", "--watch"],
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
    assert "polling" in ctx
    assert "subscribe_pr_activity" in ctx
    assert "early-failure watch phase" in ctx
    assert "steady-state heartbeat" in ctx


def test_decide_reports_start_failure_with_early_failure_phase(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(argv: list[str], *, cwd: str | None = None) -> Path:
        raise OSError("no gh on PATH")

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

    log_path = monitor.start_monitor(["gh", "pr", "checks", "723", "--watch"], cwd="/repo")

    assert log_path == tmp_path / "claude-md-pr-ci-monitor-723.log"
    assert popen_calls[0]["argv"] == ["gh", "pr", "checks", "723", "--watch"]
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


# --- _walk: bounds guard (line 82) ---


def test_walk_bounds_limits_output() -> None:
    # Build a list-of-strings large enough to trigger the len(out) < 200 guard
    large_list = [str(i) for i in range(300)]
    result = monitor._walk(large_list)
    # The walk starts by appending the list itself, then each element
    # It stops at 200 items regardless of how many remain
    assert len(result) <= 200


# --- extract_pr_number: str decimal path (lines 112-113) ---


def test_extract_pr_number_from_str_decimal() -> None:
    # covers line 112-113
    result = monitor.extract_pr_number({"number": "42"})
    assert result == "42"


# --- extract_repo: owner+name combo (line 121) ---


def test_extract_repo_from_owner_and_name_fields() -> None:
    # covers line 121
    result = monitor.extract_repo({"owner": "tvna", "name": "claude-md"})
    assert result == "tvna/claude-md"


# --- _is_owner_repo: false paths (lines 128-131 via extract_repo) ---


def test_is_owner_repo_too_many_parts() -> None:
    assert monitor._is_owner_repo("a/b/c") is False


def test_is_owner_repo_invalid_chars() -> None:
    assert monitor._is_owner_repo("a/b c") is False


def test_is_owner_repo_single_part() -> None:
    assert monitor._is_owner_repo("onlyone") is False


# --- start_monitor: exception re-raise (lines 174-175) ---


def test_start_monitor_reraises_on_popen_failure(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(monitor.tempfile, "gettempdir", lambda: str(tmp_path))

    def boom(*args: object, **kwargs: object) -> None:
        raise OSError("popen failed")

    monkeypatch.setattr(subprocess, "Popen", boom)
    with pytest.raises(OSError, match="popen failed"):
        monitor.start_monitor(["gh", "pr", "checks", "1", "--watch"])


# --- main: malformed JSON and non-dict paths (lines 244-246, 249) ---


def test_main_malformed_json_returns_zero(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.stdin", type("Input", (), {"read": lambda self: "{{bad"})())
    assert monitor.main([]) == 0
    assert "malformed" in capsys.readouterr().err


def test_main_non_dict_event_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", type("Input", (), {"read": lambda self: json.dumps([1, 2])})())
    assert monitor.main([]) == 0


# --- extract_repo: non-dict item skip (line 121) ---


def test_extract_repo_skips_non_dict_items() -> None:
    # Passing a list that contains non-dict items exercises the continue on line 121
    result = monitor.extract_repo(["not-a-dict", 42, None])
    assert result is None


# --- extract_repo: REPO_KEYS fallback path (lines 128-131) ---


def test_extract_repo_from_repo_key_without_owner() -> None:
    # No 'owner' key, but 'repo' key contains an owner/repo string
    result = monitor.extract_repo({"repo": "tvna/claude-md"})
    assert result == "tvna/claude-md"


# --- __main__ block (line 257) ---


def test_main_block_raises_system_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy

    monkeypatch.setattr("sys.stdin", type("Input", (), {"read": lambda self: "   "})())
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(
            str(Path(__file__).parent.parent / "scripts" / "post_pr_create_ci_monitor.py"),
            run_name="__main__",
        )
    assert exc_info.value.code == 0
