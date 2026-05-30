from __future__ import annotations

import json
import urllib.request
from typing import Any

import ci_early_status_probe as probe
import pytest

pytestmark = pytest.mark.shard_preflight

_TOKEN = "test-token"


# ---------------------------------------------------------------------------
# Fake opener helpers
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, data: Any, status: int = 200) -> None:
        self.status = status
        self._body = json.dumps(data).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        pass


def _url_opener(url_map: dict[str, Any]) -> Any:
    """Fake opener dispatching by URL substring."""

    def fake(req: urllib.request.Request) -> _FakeResponse:
        for pattern, data in url_map.items():
            if pattern in req.full_url:
                return _FakeResponse(data)
        raise ValueError(f"unexpected URL: {req.full_url}")

    return fake


def _event(response: Any) -> dict[str, Any]:
    return {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"repo": "o/r"},
        "tool_response": response,
    }


def _pr_data(sha: str = "abc123def456") -> dict[str, Any]:
    return {"number": 42, "head": {"sha": sha}}


def _check_runs(*rows: dict[str, Any]) -> dict[str, Any]:
    return {"check_runs": list(rows)}


def _wf_runs(*runs: dict[str, Any]) -> dict[str, Any]:
    return {"workflow_runs": list(runs)}


# ---------------------------------------------------------------------------
# extract_pr_target
# ---------------------------------------------------------------------------


def test_extracts_pr_number_from_response_url() -> None:
    repo, pr = probe.extract_pr_target(
        _event({"url": "https://github.com/o/r/pull/42"})
    )

    assert repo == "o/r"
    assert pr == "42"


# ---------------------------------------------------------------------------
# failed_check_adds_context_after_delay
# ---------------------------------------------------------------------------


def test_failed_check_adds_context_after_delay() -> None:
    sleeps: list[float] = []
    sha = "deadbeef1234"

    url_map = {
        "/pulls/42": _pr_data(sha),
        "/check-runs": _check_runs(
            {"name": "lint", "status": "completed", "conclusion": "failure",
             "check_suite": {"id": 99}},
            {"name": "types", "status": "in_progress", "conclusion": None,
             "check_suite": {"id": 99}},
        ),
        "/actions/runs": _wf_runs(
            {"name": "Verify agents", "check_suite_id": 99},
        ),
    }

    out = probe.decide(
        _event({"html_url": "https://github.com/o/r/pull/42"}),
        sleeper=sleeps.append,
        opener=_url_opener(url_map),
        token=_TOKEN,
        environ={"CODEX_CI_EARLY_PROBE_DELAY_SECONDS": "0"},
    )

    assert sleeps == [0.0]
    assert out is not None
    context = out["hookSpecificOutput"]["additionalContext"]
    assert "already has failing checks" in context
    assert "Verify agents / lint: failure" in context


def test_pending_without_failure_allows_normal_monitoring() -> None:
    sha = "aaabbbccc"
    url_map = {
        "/pulls/42": _pr_data(sha),
        "/check-runs": _check_runs(
            {"name": "lint", "status": "in_progress", "conclusion": None, "check_suite": {"id": 1}},
        ),
        "/actions/runs": _wf_runs(),
    }

    out = probe.decide(
        _event({"url": "https://github.com/o/r/pull/42"}),
        sleeper=lambda _delay: None,
        opener=_url_opener(url_map),
        token=_TOKEN,
        environ={"CODEX_CI_EARLY_PROBE_DELAY_SECONDS": "0"},
    )

    assert out is None


def test_success_without_failure_allows_normal_monitoring() -> None:
    sha = "successsha"
    url_map = {
        "/pulls/42": _pr_data(sha),
        "/check-runs": _check_runs(
            {"name": "lint", "status": "completed", "conclusion": "success", "check_suite": {"id": 1}},
        ),
        "/actions/runs": _wf_runs(),
    }

    out = probe.decide(
        _event({"url": "https://github.com/o/r/pull/42"}),
        sleeper=lambda _delay: None,
        opener=_url_opener(url_map),
        token=_TOKEN,
        environ={"CODEX_CI_EARLY_PROBE_DELAY_SECONDS": "0"},
    )

    assert out is None


def test_missing_pr_target_skips_without_sleeping_or_running() -> None:
    slept = False
    checked = False

    def sleeper(_delay: float) -> None:
        nonlocal slept
        slept = True

    def checking_opener(req: urllib.request.Request) -> _FakeResponse:
        nonlocal checked
        checked = True
        return _FakeResponse({})

    out = probe.decide(
        {"tool_name": "mcp__github__create_pull_request", "tool_response": {}},
        sleeper=sleeper,
        opener=checking_opener,
        token=_TOKEN,
    )

    assert out is None
    assert slept is False
    assert checked is False


def test_no_token_fails_open(capsys: pytest.CaptureFixture[str]) -> None:
    sha = "sha123"
    url_map = {
        "/pulls/42": _pr_data(sha),
        "/check-runs": _check_runs(),
        "/actions/runs": _wf_runs(),
    }

    out = probe.decide(
        _event({"url": "https://github.com/o/r/pull/42"}),
        sleeper=lambda _delay: None,
        opener=_url_opener(url_map),
        token="",
        environ={"CODEX_CI_EARLY_PROBE_DELAY_SECONDS": "0"},
    )

    assert out is None
    err = capsys.readouterr().err
    assert "GH_TOKEN not set" in err


def test_api_error_fetching_pr_fails_open(capsys: pytest.CaptureFixture[str]) -> None:
    url_map: dict[str, Any] = {
        "/pulls/42": ({}, 500),
        "/check-runs": _check_runs(),
        "/actions/runs": _wf_runs(),
    }

    def smart_opener(req: urllib.request.Request) -> _FakeResponse:
        for pattern, val in url_map.items():
            if pattern in req.full_url:
                if isinstance(val, tuple):
                    return _FakeResponse(val[0], val[1])
                return _FakeResponse(val)
        raise ValueError(f"unexpected URL: {req.full_url}")

    out = probe.decide(
        _event({"url": "https://github.com/o/r/pull/42"}),
        sleeper=lambda _delay: None,
        opener=smart_opener,
        token=_TOKEN,
        environ={"CODEX_CI_EARLY_PROBE_DELAY_SECONDS": "0"},
    )

    assert out is None


# --- _walk_strings coverage ---


def test_walk_strings_list_branch() -> None:
    assert probe._walk_strings(["hello", "world"]) == ["hello", "world"]
    assert probe._walk_strings([["a"], "b"]) == ["a", "b"]
    assert probe._walk_strings(42) == []


def test_extract_pr_target_int_number_in_tool_input() -> None:
    event = {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"repo": "o/r", "number": 99},
        "tool_response": {},
    }
    repo, pr = probe.extract_pr_target(event)
    assert repo == "o/r"
    assert pr == "99"


def test_extract_pr_target_str_digit_in_tool_input() -> None:
    event = {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"repo": "o/r", "pull_number": "55"},
        "tool_response": {},
    }
    repo, pr = probe.extract_pr_target(event)
    assert pr == "55"


def test_parse_delay_default_when_env_not_set() -> None:
    delay = probe.parse_delay(environ={})
    assert delay == probe._DEFAULT_DELAY_SECONDS


def test_parse_delay_invalid_value_returns_default() -> None:
    delay = probe.parse_delay(environ={"CODEX_CI_EARLY_PROBE_DELAY_SECONDS": "not-a-float"})
    assert delay == probe._DEFAULT_DELAY_SECONDS


def test_check_name_name_only() -> None:
    assert probe._check_name({"name": "lint"}) == "lint"


def test_check_name_workflow_only() -> None:
    assert probe._check_name({"workflow": "CI"}) == "CI"


def test_check_name_unnamed() -> None:
    assert probe._check_name({}) == "(unnamed check)"


def test_build_additional_context_more_than_10_failures() -> None:
    rows = [{"name": f"check-{i}", "conclusion": "failure"} for i in range(12)]
    ctx = probe.build_additional_context(None, "1", rows, 0)
    text = ctx["hookSpecificOutput"]["additionalContext"]
    assert "2 more" in text


def test_decide_returns_none_for_wrong_tool() -> None:
    out = probe.decide({"tool_name": "some_other_tool"})
    assert out is None


def test_main_outputs_decision_on_failure(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    import json as _json
    event_data = {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"repo": "o/r"},
        "tool_response": {"url": "https://github.com/o/r/pull/5"},
    }
    monkeypatch.setattr(
        "sys.stdin",
        type("Input", (), {"read": lambda self: _json.dumps(event_data)})(),
    )
    monkeypatch.setattr(probe, "decide", lambda *_a, **_kw: {"hookSpecificOutput": {"additionalContext": "x"}})

    rc = probe.main([])
    assert rc == 0
    assert capsys.readouterr().out != ""


def test_main_malformed_json_returns_zero(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.stdin", type("Input", (), {"read": lambda self: "{{bad"})())
    rc = probe.main([])
    assert rc == 0
    assert "malformed" in capsys.readouterr().err


def test_main_empty_stdin_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("sys.stdin", type("Input", (), {"read": lambda self: "   "})()
    )
    rc = probe.main([])
    assert rc == 0


def test_main_non_dict_event_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    import json as _json
    monkeypatch.setattr("sys.stdin", type("Input", (), {"read": lambda self: _json.dumps([1, 2, 3])})())
    rc = probe.main([])
    assert rc == 0


def test_main_block_raises_system_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy
    from pathlib import Path

    monkeypatch.setattr("sys.stdin", type("Input", (), {"read": lambda self: "   "})()
    )
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(
            str(Path(__file__).parent.parent / "scripts" / "ci_early_status_probe.py"),
            run_name="__main__",
        )
    assert exc_info.value.code == 0
