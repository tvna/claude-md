#!/usr/bin/env python3
"""Comment on the quality tracking issue when the post-merge coverage gate fails."""

from __future__ import annotations

import argparse
import os
import sys
import urllib.error
from collections.abc import Mapping
from dataclasses import dataclass

import issue_anchors
from _github_api import GitHubApiError, rest_json

# Coverage failures are reported as comments on the continuous code-quality
# tracking issue rather than a dedicated, marker-searched issue. The
# previous open-marker search matched unrelated issues by tokenized title text,
# so the destination is pinned explicitly; resolved from the declarative
# anchor table so a renumbering stays a one-file diff (#1640).
TARGET_ISSUE = issue_anchors.resolve("coverage-failure")
COVERAGE_GATE = "pytest --cov (threshold: [tool.coverage.report].fail_under in pyproject.toml)"


@dataclass(frozen=True)
class CoverageFailureContext:
    repo: str
    run_url: str
    workflow: str
    coverage_result: str
    run_id: str
    run_attempt: str


def _require_env(env: Mapping[str, str], names: tuple[str, ...]) -> None:
    missing = [name for name in names if not env.get(name)]
    if missing:
        raise RuntimeError(f"Missing required environment: {', '.join(missing)}")


def context_from_env(env: Mapping[str, str] = os.environ) -> CoverageFailureContext:
    _require_env(env, ("GH_TOKEN", "REPO", "RUN_ID"))
    repo = env["REPO"]
    run_id = env["RUN_ID"]
    run_attempt = env.get("RUN_ATTEMPT", "1")
    server_url = env.get("SERVER_URL", "https://github.com").rstrip("/")
    workflow = env.get("WORKFLOW", "Post-merge automation")
    coverage_result = env.get("COVERAGE_RESULT", "failure")
    run_url = f"{server_url}/{repo}/actions/runs/{run_id}/attempts/{run_attempt}"
    return CoverageFailureContext(
        repo=repo,
        run_url=run_url,
        workflow=workflow,
        coverage_result=coverage_result,
        run_id=run_id,
        run_attempt=run_attempt,
    )


def render_comment(context: CoverageFailureContext) -> str:
    return (
        "Post-merge coverage gate failed.\n"
        "\n"
        f"- Workflow: `{context.workflow}`\n"
        f"- Coverage job result: `{context.coverage_result}`\n"
        f"- Failed run: {context.run_url}\n"
        f"- Local coverage gate: `{COVERAGE_GATE}`\n"
        f"- Run id: `{context.run_id}`\n"
        f"- Run attempt: `{context.run_attempt}`\n"
    )


def post_failure_comment(
    context: CoverageFailureContext,
    *,
    token: str | None = None,
) -> str:
    """Post the coverage-failure comment on the tracking issue via REST.

    Raises :class:`_github_api.GitHubApiError` on a non-2xx response so the
    caller fails loud (CLAUDE.md section 4).
    """
    if token is None:
        token = os.environ.get("GH_TOKEN", "")
    rest_json(
        "POST",
        f"/repos/{context.repo}/issues/{TARGET_ISSUE}/comments",
        {"body": render_comment(context)},
        token=token,
    )
    print(f"Commented coverage failure on #{TARGET_ISSUE}.")
    return "commented"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run")
    args = parser.parse_args(argv)

    if args.command == "run":
        try:
            context = context_from_env()
            post_failure_comment(context)
        except (RuntimeError, GitHubApiError, urllib.error.URLError, OSError) as error:
            print(f"::error::{error}", file=sys.stderr)
            return 1
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
