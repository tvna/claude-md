from __future__ import annotations

import json
import subprocess
from typing import Any

import check_pr_mergeability as subject
import pytest

pytestmark = pytest.mark.shard_preflight


def _completed(data: Any, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        ["gh"],
        returncode,
        stdout=json.dumps(data) if not isinstance(data, str) else data,
        stderr="",
    )


def _pr_event(tool_name: str, response: Any, tool_input: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "tool_response": response,
        "tool_input": tool_input or {"owner": "tvna", "repo": "claude-md"},
    }


# ---------------------------------------------------------------------------
# _extract_pr_info
# ---------------------------------------------------------------------------


def test_extract_pr_info_from_url_in_response() -> None:
    event = _pr_event(
        "mcp__github__create_pull_request",
        {"html_url": "https://github.com/tvna/claude-md/pull/99"},
    )
    owner, repo, number = subject._extract_pr_info(event)

    assert owner == "tvna"
    assert repo == "claude-md"
    assert number == "99"


def test_extract_pr_info_from_number_in_response() -> None:
    event = _pr_event(
        "mcp__github__create_pull_request",
        {"number": 42},
    )
    owner, repo, number = subject._extract_pr_info(event)

    assert number == "42"
    assert owner == "tvna"
    assert repo == "claude-md"


def test_extract_pr_info_returns_none_when_missing() -> None:
    event = _pr_event("mcp__github__create_pull_request", {})
    owner, repo, number = subject._extract_pr_info(event)

    assert number is None


# ---------------------------------------------------------------------------
# decide_post_tool_use — target tool filtering
# ---------------------------------------------------------------------------


def test_decide_ignores_non_target_tool() -> None:
    event = _pr_event("mcp__github__update_pull_request", {"number": 1})
    assert subject.decide_post_tool_use(event) is None


def test_decide_handles_update_pull_request_branch() -> None:
    calls: list[list[str]] = []

    def fake_runner(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        calls.append(cmd)
        return _completed({"mergeable": True, "mergeable_state": "clean"})

    event = _pr_event(
        "mcp__github__update_pull_request_branch",
        {"html_url": "https://github.com/tvna/claude-md/pull/10"},
    )
    result = subject.decide_post_tool_use(event, runner=fake_runner, sleeper=lambda _: None)

    assert result is not None
    ctx = result["hookSpecificOutput"]["additionalContext"]
    assert "clean" in ctx


# ---------------------------------------------------------------------------
# decide_post_tool_use — mergeability states
# ---------------------------------------------------------------------------


def test_decide_returns_dirty_warning() -> None:
    def fake_runner(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return _completed({"mergeable": False, "mergeable_state": "dirty"})

    event = _pr_event(
        "mcp__github__create_pull_request",
        {"html_url": "https://github.com/tvna/claude-md/pull/5"},
    )
    result = subject.decide_post_tool_use(event, runner=fake_runner, sleeper=lambda _: None)

    assert result is not None
    ctx = result["hookSpecificOutput"]["additionalContext"]
    assert "MERGE CONFLICT" in ctx
    assert "dirty" in ctx


def test_decide_returns_clean_ok() -> None:
    def fake_runner(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return _completed({"mergeable": True, "mergeable_state": "clean"})

    event = _pr_event(
        "mcp__github__create_pull_request",
        {"html_url": "https://github.com/tvna/claude-md/pull/7"},
    )
    result = subject.decide_post_tool_use(event, runner=fake_runner, sleeper=lambda _: None)

    assert result is not None
    ctx = result["hookSpecificOutput"]["additionalContext"]
    assert "clean" in ctx
    assert "MERGE CONFLICT" not in ctx


def test_decide_returns_blocked_advisory() -> None:
    def fake_runner(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return _completed({"mergeable": True, "mergeable_state": "blocked"})

    event = _pr_event(
        "mcp__github__create_pull_request",
        {"html_url": "https://github.com/tvna/claude-md/pull/8"},
    )
    result = subject.decide_post_tool_use(event, runner=fake_runner, sleeper=lambda _: None)

    assert result is not None
    ctx = result["hookSpecificOutput"]["additionalContext"]
    assert "blocked" in ctx


def test_decide_polls_until_mergeable_non_null() -> None:
    responses = [
        {"mergeable": None, "mergeable_state": "unknown"},
        {"mergeable": None, "mergeable_state": "unknown"},
        {"mergeable": True, "mergeable_state": "clean"},
    ]
    call_count = 0
    sleeps: list[float] = []

    def fake_runner(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        nonlocal call_count
        data = responses[min(call_count, len(responses) - 1)]
        call_count += 1
        return _completed(data)

    def fake_sleeper(secs: float) -> None:
        sleeps.append(secs)

    event = _pr_event(
        "mcp__github__create_pull_request",
        {"html_url": "https://github.com/tvna/claude-md/pull/9"},
    )
    result = subject.decide_post_tool_use(event, runner=fake_runner, sleeper=fake_sleeper)

    assert call_count == 3
    assert len(sleeps) == 2
    assert result is not None
    assert "clean" in result["hookSpecificOutput"]["additionalContext"]


def test_decide_times_out_gracefully() -> None:
    def fake_runner(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return _completed({"mergeable": None, "mergeable_state": "unknown"})

    event = _pr_event(
        "mcp__github__create_pull_request",
        {"html_url": "https://github.com/tvna/claude-md/pull/11"},
    )
    result = subject.decide_post_tool_use(event, runner=fake_runner, sleeper=lambda _: None)

    assert result is not None
    ctx = result["hookSpecificOutput"]["additionalContext"]
    assert "timed out" in ctx


def test_decide_skips_when_no_pr_number() -> None:
    event = _pr_event("mcp__github__create_pull_request", {})
    result = subject.decide_post_tool_use(event)

    assert result is not None
    ctx = result["hookSpecificOutput"]["additionalContext"]
    assert "skipped" in ctx


def test_decide_skips_when_api_fails() -> None:
    def fake_runner(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return _completed("", returncode=1)

    event = _pr_event(
        "mcp__github__create_pull_request",
        {"html_url": "https://github.com/tvna/claude-md/pull/12"},
    )
    result = subject.decide_post_tool_use(event, runner=fake_runner, sleeper=lambda _: None)

    assert result is not None
    ctx = result["hookSpecificOutput"]["additionalContext"]
    assert "failed" in ctx


# ---------------------------------------------------------------------------
# run_session_start
# ---------------------------------------------------------------------------


def test_session_start_emits_banner_for_dirty_pr(capsys: pytest.CaptureFixture[str]) -> None:
    pr_list = [
        {
            "number": 55,
            "url": "https://github.com/tvna/claude-md/pull/55",
            "headRepositoryOwner": {"login": "tvna"},
            "headRepository": {"name": "claude-md"},
        }
    ]

    def fake_runner(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        if "pr" in cmd and "list" in cmd:
            return _completed(pr_list)
        return _completed({"mergeable": False, "mergeable_state": "dirty"})

    subject.run_session_start(runner=fake_runner, sleeper=lambda _: None)

    out = capsys.readouterr().out
    assert "MERGE CONFLICT WARNING" in out
    assert "pull/55" in out


def test_session_start_silent_when_all_clean(capsys: pytest.CaptureFixture[str]) -> None:
    pr_list = [
        {
            "number": 60,
            "url": "https://github.com/tvna/claude-md/pull/60",
            "headRepositoryOwner": {"login": "tvna"},
            "headRepository": {"name": "claude-md"},
        }
    ]

    def fake_runner(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        if "pr" in cmd and "list" in cmd:
            return _completed(pr_list)
        return _completed({"mergeable": True, "mergeable_state": "clean"})

    subject.run_session_start(runner=fake_runner, sleeper=lambda _: None)

    out = capsys.readouterr().out
    assert out == ""


def test_session_start_emits_banner_for_behind_pr(capsys: pytest.CaptureFixture[str]) -> None:
    pr_list = [
        {
            "number": 70,
            "url": "https://github.com/tvna/claude-md/pull/70",
            "headRepositoryOwner": {"login": "tvna"},
            "headRepository": {"name": "claude-md"},
        }
    ]

    def fake_runner(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        if "pr" in cmd and "list" in cmd:
            return _completed(pr_list)
        return _completed({"mergeable": True, "mergeable_state": "behind"})

    subject.run_session_start(runner=fake_runner, sleeper=lambda _: None)

    out = capsys.readouterr().out
    assert "OUT-OF-DATE WARNING" in out
    assert "pull/70" in out
    assert "MERGE CONFLICT" not in out


def test_session_start_emits_both_banners_for_dirty_and_behind(capsys: pytest.CaptureFixture[str]) -> None:
    pr_list = [
        {
            "number": 71,
            "url": "https://github.com/tvna/claude-md/pull/71",
            "headRepositoryOwner": {"login": "tvna"},
            "headRepository": {"name": "claude-md"},
        },
        {
            "number": 72,
            "url": "https://github.com/tvna/claude-md/pull/72",
            "headRepositoryOwner": {"login": "tvna"},
            "headRepository": {"name": "claude-md"},
        },
    ]
    states = {"71": "dirty", "72": "behind"}

    def fake_runner(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        if "pr" in cmd and "list" in cmd:
            return _completed(pr_list)
        # Identify PR by URL path component in the API path argument
        path_arg = next((a for a in cmd if "/pulls/" in a), "")
        number = path_arg.split("/pulls/")[-1] if path_arg else ""
        state = states.get(number, "clean")
        mergeable = state != "dirty"
        return _completed({"mergeable": mergeable, "mergeable_state": state})

    subject.run_session_start(runner=fake_runner, sleeper=lambda _: None)

    out = capsys.readouterr().out
    assert "MERGE CONFLICT WARNING" in out
    assert "OUT-OF-DATE WARNING" in out
    assert "pull/71" in out
    assert "pull/72" in out


def test_session_start_silent_when_no_open_prs(capsys: pytest.CaptureFixture[str]) -> None:
    def fake_runner(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return _completed([])

    subject.run_session_start(runner=fake_runner, sleeper=lambda _: None)

    out = capsys.readouterr().out
    assert out == ""


# ---------------------------------------------------------------------------
# main() entry point
# ---------------------------------------------------------------------------


def test_main_session_start_mode(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    called: list[bool] = []

    def fake_run_session_start(**_: Any) -> None:
        called.append(True)

    monkeypatch.setattr(subject, "run_session_start", fake_run_session_start)

    rc = subject.main(["session-start"])
    assert rc == 0
    assert called == [True]


def test_main_posttooluse_mode_emits_json(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    event = _pr_event(
        "mcp__github__create_pull_request",
        {"html_url": "https://github.com/tvna/claude-md/pull/77"},
    )
    stdin_data = json.dumps(event)

    output: list[str] = []
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
    monkeypatch.setattr("sys.stdout", type("FakeOut", (), {"write": lambda self, s: output.append(s)})())

    def fake_runner(cmd: list[str], **_: Any) -> subprocess.CompletedProcess[str]:
        return _completed({"mergeable": True, "mergeable_state": "clean"})

    monkeypatch.setattr(subject, "_poll_mergeability", lambda *a, **kw: {"mergeable": True, "mergeable_state": "clean"})

    rc = subject.main([])
    assert rc == 0
    assert output
    parsed = json.loads("".join(output))
    assert "hookSpecificOutput" in parsed
