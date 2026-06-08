#!/usr/bin/env python3
"""Comment on the quality tracking issue when the post-merge coverage gate fails."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

# Coverage failures are reported as comments on the continuous code-quality
# tracking issue (#197) rather than a dedicated, marker-searched issue. The
# previous open-marker search matched unrelated issues by tokenized title text,
# so the destination is now pinned explicitly.
TARGET_ISSUE = 197
COVERAGE_GATE = "pytest --cov (threshold: [tool.coverage.report].fail_under in pyproject.toml)"

Runner = Callable[..., subprocess.CompletedProcess[str]]


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


def _run_gh(cmd: list[str], *, runner: Runner, body: str | None = None) -> subprocess.CompletedProcess[str]:
    kwargs: dict[str, Any] = {
        "capture_output": True,
        "text": True,
        "timeout": 30,
        "check": True,
    }
    if body is not None:
        cmd = [*cmd, "--body", body]
    return runner(cmd, **kwargs)


def post_failure_comment(
    context: CoverageFailureContext,
    *,
    runner: Runner = subprocess.run,
) -> str:
    _run_gh(
        [
            "gh",
            "issue",
            "comment",
            str(TARGET_ISSUE),
            "--repo",
            context.repo,
        ],
        runner=runner,
        body=render_comment(context),
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
        except (RuntimeError, subprocess.CalledProcessError) as error:
            print(f"::error::{error}", file=sys.stderr)
            return 1
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
