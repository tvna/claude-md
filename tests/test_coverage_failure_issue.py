from __future__ import annotations

from typing import Any

import coverage_failure_issue
import pytest

pytestmark = pytest.mark.shard_ci_ops


class FakeRest:
    """Capture rest_json calls in place of a real GitHub REST POST."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def __call__(self, method: str, path: str, payload=None, *, token: str) -> Any:
        self.calls.append(
            {"method": method, "path": path, "payload": payload, "token": token}
        )
        return {"id": 1}


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


def test_post_failure_comment_targets_quality_tracking_issue(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rest = FakeRest()
    monkeypatch.setattr(coverage_failure_issue, "rest_json", rest)
    context = coverage_failure_issue.CoverageFailureContext(
        repo="owner/repo",
        run_url="https://github.com/owner/repo/actions/runs/124",
        workflow="Post-merge automation",
        coverage_result="failure",
        run_id="124",
        run_attempt="1",
    )

    result = coverage_failure_issue.post_failure_comment(context, token="tok")

    assert result == "commented"
    assert len(rest.calls) == 1
    call = rest.calls[0]
    assert call["method"] == "POST"
    assert coverage_failure_issue.TARGET_ISSUE == 197
    assert call["path"] == f"/repos/owner/repo/issues/{coverage_failure_issue.TARGET_ISSUE}/comments"
    assert call["token"] == "tok"
    assert "https://github.com/owner/repo/actions/runs/124" in call["payload"]["body"]


def test_post_failure_comment_reads_token_from_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    rest = FakeRest()
    monkeypatch.setattr(coverage_failure_issue, "rest_json", rest)
    monkeypatch.setenv("GH_TOKEN", "env-token")
    context = coverage_failure_issue.CoverageFailureContext(
        repo="owner/repo",
        run_url="https://github.com/owner/repo/actions/runs/125",
        workflow="Post-merge automation",
        coverage_result="failure",
        run_id="125",
        run_attempt="1",
    )

    coverage_failure_issue.post_failure_comment(context)

    assert rest.calls[0]["token"] == "env-token"


def test_context_from_env_requires_token_repo_and_run_id() -> None:
    with pytest.raises(RuntimeError, match="Missing required environment"):
        coverage_failure_issue.context_from_env({})


def test_main_run_returns_1_when_post_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from _github_api import GitHubApiError

    monkeypatch.setenv("GH_TOKEN", "token")
    monkeypatch.setenv("REPO", "owner/repo")
    monkeypatch.setenv("RUN_ID", "123")

    def _raise(*_a, **_k):
        raise GitHubApiError(500, "POST", "/repos/owner/repo/issues/197/comments", "boom")

    monkeypatch.setattr(coverage_failure_issue, "post_failure_comment", _raise)

    assert coverage_failure_issue.main(["run"]) == 1


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
        token: str | None = None,
    ) -> str:
        calls.append(context)
        return "commented"

    monkeypatch.setattr(coverage_failure_issue, "post_failure_comment", fake_post_failure_comment)

    assert coverage_failure_issue.main(["run"]) == 0
    assert calls[0].run_url == "https://github.com/owner/repo/actions/runs/123/attempts/2"
