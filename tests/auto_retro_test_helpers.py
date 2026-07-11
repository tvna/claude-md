"""Shared fixtures for auto-retro orchestrator tests."""

from __future__ import annotations

import json
from typing import Any

import auto_retro as ar
import pytest
from _github_api import GitHubApiError

# The label set the .gitapex/ssot.json registry entry for scripts/auto_retro.py
# carries, mirrored here so orchestrator tests inject a known set via
# _ssot.consumer_labels instead of depending on (or asserting against) the
# live registry file. REGISTRY_LABELS is the full entry (registry order):
# the create-time identity labels, the retired layer:meta kept only for
# discovery (#1041, #2313), then the terminal open-state labels.
# TERMINAL_PRIMARY / TERMINAL_LEGACY are the terminal open-state labels the code
# derives from it. Derivation-specific tests override the mock with synthetic
# labels to prove the code reads the registry rather than a hardcoded literal.
REGISTRY_LABELS = (
    "type:docs",
    "layer:p3-harness",
    "area:ci-ops",
    "layer:meta",
    "ops:retro-opened",
    "harness:retro-opened",
)
TERMINAL_PRIMARY = "ops:retro-opened"
TERMINAL_LEGACY = "harness:retro-opened"


def stub_registry_labels(
    monkeypatch: pytest.MonkeyPatch, labels: tuple[str, ...] = REGISTRY_LABELS
) -> None:
    """Point ar._ssot.consumer_labels at a fixed label set for the test."""
    monkeypatch.setattr(ar._ssot, "consumer_labels", lambda path: labels)


def merged_event(**overrides: Any) -> dict[str, Any]:
    pr: dict[str, Any] = {
        "number": 42,
        "title": "feat(harness): do a thing",
        "merged": True,
        "merged_at": "2026-05-23T10:00:00Z",
        "merged_by": {"login": "tvna"},
        "user": {"login": "tvna"},
        "labels": [
            {"name": "type:feat"},
            {"name": "layer:p3-harness"},
            {"name": "layer:meta"},
        ],
        "html_url": "https://github.com/o/r/pull/42",
    }
    pr.update(overrides)
    return {"pull_request": pr}


def orchestrator_recorder(
    monkeypatch: pytest.MonkeyPatch,
    *,
    existing: list[dict[str, Any]] | None = None,
    commits: list[dict[str, Any]] | None = None,
    review_comments: list[dict[str, Any]] | None = None,
    created_response: dict[str, Any] | None = None,
    comments_error: bool = False,
    pr_detail: dict[str, Any] | None = None,
    pr_detail_sequence: list[dict[str, Any]] | None = None,
    check_runs: list[dict[str, Any]] | None = None,
    check_runs_error: bool = False,
    back_link_comments: list[dict[str, Any]] | None = None,
    back_link_post_error: bool = False,
    terminal_label_post_error: bool = False,
) -> list[tuple[str, str, Any]]:
    """Replace ar.gh_api with a recorder that returns canned data per path."""
    seen: list[tuple[str, str, Any]] = []
    existing = existing or []
    commits = commits or []
    if review_comments is None:
        review_comments = [{"id": 1, "body": "default repair signal"}]
    created_response = created_response or {
        "number": 999,
        "html_url": "https://x/i/999",
    }
    if pr_detail is None:
        pr_detail = {"merge_commit_sha": None}
    check_runs = check_runs or []
    back_link_comments = back_link_comments or []
    pr_detail_idx = [0]

    def fake_api(method, path, body=None, **_kw):
        seen.append((method, path, body))
        if method == "GET" and "/contents/" in path:
            # Simulates the repair-free-merge-ledger file not existing yet
            # (the common case in tests that don't care about the ledger
            # feature): a 404, not an empty body, so
            # auto_retro.fetch_repo_file's real 404-vs-unexpected-encoding
            # distinction is exercised the same way live GitHub behaves.
            raise GitHubApiError(404, "GET", path, "Not Found")
        if method == "GET" and path.startswith("/search/issues"):
            return json.dumps({"items": existing})
        if method == "GET" and "/pulls/" in path and "/comments" in path:
            if comments_error:
                raise GitHubApiError(500, "GET", path, "comments endpoint boom")
            return json.dumps(review_comments)
        if method == "GET" and "/pulls/" in path and "/commits" in path:
            return json.dumps(commits)
        if method == "GET" and "/check-runs" in path:
            return json.dumps({"check_runs": check_runs})
        if method == "GET" and "/pulls/" in path:
            if check_runs_error:
                raise GitHubApiError(500, "GET", path, "pulls endpoint boom")
            if pr_detail_sequence is not None:
                i = pr_detail_idx[0]
                pr_detail_idx[0] = i + 1
                if i < len(pr_detail_sequence):
                    return json.dumps(pr_detail_sequence[i])
                return json.dumps(pr_detail_sequence[-1])
            return json.dumps(pr_detail)
        if (
            method == "GET"
            and "/issues/" in path
            and path.split("?", 1)[0].endswith("/comments")
        ):
            return json.dumps(back_link_comments)
        if (
            method == "POST"
            and "/issues/" in path
            and path.endswith("/comments")
        ):
            if back_link_post_error:
                raise GitHubApiError(500, "POST", path, "back-link post boom")
            return ""
        if (
            method == "POST"
            and "/issues/" in path
            and path.endswith("/labels")
        ):
            if terminal_label_post_error:
                raise GitHubApiError(500, "POST", path, "terminal-label post boom")
            return ""
        if method == "PATCH" and "/issues/comments/" in path:
            return ""
        if method == "POST" and path.endswith("/issues"):
            return json.dumps(created_response)
        return ""

    stub_registry_labels(monkeypatch)
    monkeypatch.setattr(ar, "gh_api", fake_api)
    return seen
