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
