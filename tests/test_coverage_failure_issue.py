from __future__ import annotations

import json
import subprocess

import coverage_failure_issue
import pytest

pytestmark = pytest.mark.shard_ci_ops


class FakeRunner:
    def __init__(self, *, list_stdout: str = "[]") -> None:
        self.calls: list[list[str]] = []
        self.list_stdout = list_stdout

    def __call__(
        self,
        cmd: list[str],
        *,
        capture_output: bool,
        text: bool,
        timeout: int,
        check: bool,
    ) -> subprocess.CompletedProcess[str]:
        self.calls.append(cmd)
        assert capture_output is True
        assert text is True
        assert timeout == 30
        assert check is True
        if cmd[:3] == ["gh", "issue", "list"]:
            return subprocess.CompletedProcess(cmd, 0, self.list_stdout, "")
        return subprocess.CompletedProcess(cmd, 0, "", "")


def test_render_issue_body_links_run_and_names_threshold() -> None:
    context = coverage_failure_issue.CoverageFailureContext(
        repo="owner/repo",
        run_url="https://github.com/owner/repo/actions/runs/123/attempts/2",
        workflow="Post-merge automation",
        coverage_result="failure",
        run_id="123",
        run_attempt="2",
    )

    body = coverage_failure_issue.render_issue_body(context)

    assert "<!-- coverage-failure-issue -->" in body
    assert "Refs #749" in body
    assert "https://github.com/owner/repo/actions/runs/123/attempts/2" in body
    assert "pytest --cov-fail-under=92.71" in body
    assert "Speculation:" in body


def test_open_or_update_creates_issue_when_no_marker_issue_exists() -> None:
    runner = FakeRunner(list_stdout="[]")
    context = coverage_failure_issue.CoverageFailureContext(
        repo="owner/repo",
        run_url="https://github.com/owner/repo/actions/runs/123",
        workflow="Post-merge automation",
        coverage_result="failure",
        run_id="123",
        run_attempt="1",
    )

    result = coverage_failure_issue.open_or_update_issue(context, runner=runner)

    assert result == "created"
    assert runner.calls[0][:3] == ["gh", "issue", "list"]
    assert runner.calls[1][:3] == ["gh", "issue", "create"]
    assert "--title" in runner.calls[1]
    assert "ci(coverage): post-merge coverage threshold failed" in runner.calls[1]
    assert runner.calls[1].count("--label") == 2
    assert "type:fix" in runner.calls[1]
    assert "layer:p3-harness" in runner.calls[1]


def test_open_or_update_comments_when_marker_issue_exists() -> None:
    runner = FakeRunner(list_stdout=json.dumps([{"number": 321}]))
    context = coverage_failure_issue.CoverageFailureContext(
        repo="owner/repo",
        run_url="https://github.com/owner/repo/actions/runs/124",
        workflow="Post-merge automation",
        coverage_result="failure",
        run_id="124",
        run_attempt="1",
    )

    result = coverage_failure_issue.open_or_update_issue(context, runner=runner)

    assert result == "commented"
    assert runner.calls[0][:3] == ["gh", "issue", "list"]
    assert runner.calls[1][:3] == ["gh", "issue", "comment"]
    assert "321" in runner.calls[1]
    assert any("https://github.com/owner/repo/actions/runs/124" in arg for arg in runner.calls[1])


def test_context_from_env_requires_token_repo_and_run_id() -> None:
    with pytest.raises(RuntimeError, match="Missing required environment"):
        coverage_failure_issue.context_from_env({})


def test_main_run_matches_workflow_env(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[coverage_failure_issue.CoverageFailureContext] = []
    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setenv("REPO", "owner/repo")
    monkeypatch.setenv("RUN_ID", "123")
    monkeypatch.setenv("RUN_ATTEMPT", "2")
    monkeypatch.setenv("SERVER_URL", "https://github.com")
    monkeypatch.setenv("WORKFLOW", "Post-merge automation")
    monkeypatch.setenv("COVERAGE_RESULT", "failure")

    def fake_open_or_update(
        context: coverage_failure_issue.CoverageFailureContext,
        *,
        runner=coverage_failure_issue.subprocess.run,
    ) -> str:
        calls.append(context)
        return "created"

    monkeypatch.setattr(coverage_failure_issue, "open_or_update_issue", fake_open_or_update)

    assert coverage_failure_issue.main(["run"]) == 0
    assert calls[0].run_url == "https://github.com/owner/repo/actions/runs/123/attempts/2"
