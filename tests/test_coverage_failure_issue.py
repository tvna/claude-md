from __future__ import annotations

import subprocess

import coverage_failure_issue
import pytest

pytestmark = pytest.mark.shard_ci_ops


class FakeRunner:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

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
        return subprocess.CompletedProcess(cmd, 0, "", "")


def test_render_comment_links_run_and_names_threshold() -> None:
    context = coverage_failure_issue.CoverageFailureContext(
        repo="owner/repo",
        run_url="https://github.com/owner/repo/actions/runs/123/attempts/2",
        workflow="Post-merge automation",
        coverage_result="failure",
        run_id="123",
        run_attempt="2",
    )

    comment = coverage_failure_issue.render_comment(context)

    assert "https://github.com/owner/repo/actions/runs/123/attempts/2" in comment
    assert "[tool.coverage.report].fail_under in pyproject.toml" in comment
    assert "Post-merge coverage gate failed." in comment


def test_post_failure_comment_targets_quality_tracking_issue() -> None:
    runner = FakeRunner()
    context = coverage_failure_issue.CoverageFailureContext(
        repo="owner/repo",
        run_url="https://github.com/owner/repo/actions/runs/124",
        workflow="Post-merge automation",
        coverage_result="failure",
        run_id="124",
        run_attempt="1",
    )

    result = coverage_failure_issue.post_failure_comment(context, runner=runner)

    assert result == "commented"
    assert len(runner.calls) == 1
    assert runner.calls[0][:3] == ["gh", "issue", "comment"]
    assert str(coverage_failure_issue.TARGET_ISSUE) in runner.calls[0]
    assert coverage_failure_issue.TARGET_ISSUE == 197
    assert any("https://github.com/owner/repo/actions/runs/124" in arg for arg in runner.calls[0])


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

    def fake_post_failure_comment(
        context: coverage_failure_issue.CoverageFailureContext,
        *,
        runner=coverage_failure_issue.subprocess.run,
    ) -> str:
        calls.append(context)
        return "commented"

    monkeypatch.setattr(coverage_failure_issue, "post_failure_comment", fake_post_failure_comment)

    assert coverage_failure_issue.main(["run"]) == 0
    assert calls[0].run_url == "https://github.com/owner/repo/actions/runs/123/attempts/2"
