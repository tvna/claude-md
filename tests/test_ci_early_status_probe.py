from __future__ import annotations

import json
import subprocess
from typing import Any

import ci_early_status_probe as probe
import pytest

pytestmark = pytest.mark.shard_preflight


def _event(response: Any) -> dict[str, Any]:
    return {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"repo": "o/r"},
        "tool_response": response,
    }


def _completed(rows: list[dict[str, Any]], returncode: int = 0) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess(
        ["gh"],
        returncode,
        stdout=json.dumps(rows),
        stderr="",
    )


def test_extracts_pr_number_from_response_url() -> None:
    repo, pr = probe.extract_pr_target(
        _event({"url": "https://github.com/o/r/pull/42"})
    )

    assert repo == "o/r"
    assert pr == "42"


def test_failed_check_adds_context_after_delay() -> None:
    sleeps: list[float] = []
    calls: list[list[str]] = []

    def runner(cmd, **_kwargs):
        calls.append(cmd)
        return _completed(
            [
                {
                    "workflow": "Verify agents",
                    "name": "lint",
                    "state": "COMPLETED",
                    "conclusion": "failure",
                },
                {
                    "workflow": "Verify agents",
                    "name": "types",
                    "state": "PENDING",
                    "conclusion": "",
                },
            ],
            returncode=1,
        )

    out = probe.decide(
        _event({"html_url": "https://github.com/o/r/pull/42"}),
        sleeper=sleeps.append,
        runner=runner,
        environ={"CODEX_CI_EARLY_PROBE_DELAY_SECONDS": "0"},
    )

    assert sleeps == [0.0]
    assert calls == [
        [
            "gh",
            "pr",
            "checks",
            "42",
            "--json",
            "name,state,conclusion,workflow",
            "--repo",
            "o/r",
        ]
    ]
    assert out is not None
    context = out["hookSpecificOutput"]["additionalContext"]
    assert "already has failing checks" in context
    assert "Verify agents / lint: failure" in context


def test_pending_without_failure_allows_normal_monitoring() -> None:
    out = probe.decide(
        _event({"url": "https://github.com/o/r/pull/42"}),
        sleeper=lambda _delay: None,
        runner=lambda *_args, **_kwargs: _completed(
            [{"name": "lint", "state": "PENDING", "conclusion": ""}]
        ),
        environ={"CODEX_CI_EARLY_PROBE_DELAY_SECONDS": "0"},
    )

    assert out is None


def test_success_without_failure_allows_normal_monitoring() -> None:
    out = probe.decide(
        _event({"url": "https://github.com/o/r/pull/42"}),
        sleeper=lambda _delay: None,
        runner=lambda *_args, **_kwargs: _completed(
            [{"name": "lint", "state": "COMPLETED", "conclusion": "success"}]
        ),
        environ={"CODEX_CI_EARLY_PROBE_DELAY_SECONDS": "0"},
    )

    assert out is None


def test_missing_pr_target_skips_without_sleeping_or_running() -> None:
    slept = False
    ran = False

    def sleeper(_delay: float) -> None:
        nonlocal slept
        slept = True

    def runner(*_args, **_kwargs):
        nonlocal ran
        ran = True
        return _completed([])

    out = probe.decide(
        {"tool_name": "mcp__github__create_pull_request", "tool_response": {}},
        sleeper=sleeper,
        runner=runner,
    )

    assert out is None
    assert slept is False
    assert ran is False


def test_subprocess_failure_fails_open(capsys: pytest.CaptureFixture[str]) -> None:
    def runner(*_args, **_kwargs):
        raise OSError("missing gh")

    out = probe.decide(
        _event({"url": "https://github.com/o/r/pull/42"}),
        sleeper=lambda _delay: None,
        runner=runner,
        environ={"CODEX_CI_EARLY_PROBE_DELAY_SECONDS": "0"},
    )

    assert out is None
    assert "gh pr checks failed" in capsys.readouterr().err


# --- _walk_strings coverage ---


def test_walk_strings_list_branch() -> None:
    # covers lines 41-46 (list branch)
    assert probe._walk_strings(["hello", "world"]) == ["hello", "world"]
    assert probe._walk_strings([["a"], "b"]) == ["a", "b"]
    assert probe._walk_strings(42) == []  # non-str/dict/list returns []


# --- extract_pr_target: int and str-digit pr number from tool_input ---


def test_extract_pr_target_int_number_in_tool_input() -> None:
    # covers line 64
    event = {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"repo": "o/r", "number": 99},
        "tool_response": {},
    }
    repo, pr = probe.extract_pr_target(event)
    assert repo == "o/r"
    assert pr == "99"


def test_extract_pr_target_str_digit_in_tool_input() -> None:
    # covers line 66
    event = {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"repo": "o/r", "pull_number": "55"},
        "tool_response": {},
    }
    repo, pr = probe.extract_pr_target(event)
    assert pr == "55"


# --- parse_delay: default and ValueError paths ---


def test_parse_delay_default_when_env_not_set() -> None:
    # covers line 82
    delay = probe.parse_delay(environ={})
    assert delay == probe._DEFAULT_DELAY_SECONDS


def test_parse_delay_invalid_value_returns_default() -> None:
    # covers lines 85-86
    delay = probe.parse_delay(environ={"CODEX_CI_EARLY_PROBE_DELAY_SECONDS": "not-a-float"})
    assert delay == probe._DEFAULT_DELAY_SECONDS


# --- _load_check_rows: json error and non-list ---


def test_load_check_rows_invalid_json_returns_empty() -> None:
    # covers lines 111-112
    result = probe._load_check_rows("not json{{{")
    assert result == []


def test_load_check_rows_non_list_returns_empty() -> None:
    # covers line 114
    import json as _json
    result = probe._load_check_rows(_json.dumps({"key": "value"}))
    assert result == []


# --- _check_name: name-only, workflow-only, unnamed branches ---


def test_check_name_name_only() -> None:
    # covers line 133-134
    assert probe._check_name({"name": "lint"}) == "lint"


def test_check_name_workflow_only() -> None:
    # covers lines 135-136
    assert probe._check_name({"workflow": "CI"}) == "CI"


def test_check_name_unnamed() -> None:
    # covers line 137
    assert probe._check_name({}) == "(unnamed check)"


# --- build_additional_context: more than 10 failures ---


def test_build_additional_context_more_than_10_failures() -> None:
    # covers line 157
    rows = [{"name": f"check-{i}", "conclusion": "failure"} for i in range(12)]
    ctx = probe.build_additional_context(None, "1", rows, 0)
    text = ctx["hookSpecificOutput"]["additionalContext"]
    assert "2 more" in text


# --- decide: wrong tool name ---


def test_decide_returns_none_for_wrong_tool() -> None:
    # covers line 174
    out = probe.decide({"tool_name": "some_other_tool"})
    assert out is None


# --- main() ---


def test_main_outputs_decision_on_failure(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    # covers lines 197-209
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
    monkeypatch.setattr("sys.stdin", type("Input", (), {"read": lambda self: "   "})())
    rc = probe.main([])
    assert rc == 0


def test_main_non_dict_event_returns_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    import json as _json
    monkeypatch.setattr("sys.stdin", type("Input", (), {"read": lambda self: _json.dumps([1, 2, 3])})())
    rc = probe.main([])
    assert rc == 0


# --- __main__ block (line 213) ---


def test_main_block_raises_system_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy
    from pathlib import Path

    monkeypatch.setattr("sys.stdin", type("Input", (), {"read": lambda self: "   "})())
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_path(
            str(Path(__file__).parent.parent / "scripts" / "ci_early_status_probe.py"),
            run_name="__main__",
        )
    assert exc_info.value.code == 0
