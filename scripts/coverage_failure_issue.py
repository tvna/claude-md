#!/usr/bin/env python3
"""Open or update a tracking issue when the post-merge coverage gate fails."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

PARENT_ISSUE = 749
ISSUE_MARKER = "<!-- coverage-failure-issue -->"
ISSUE_TITLE = "ci(coverage): post-merge coverage threshold failed"
ISSUE_LABELS = ("type:fix", "layer:p3-harness")
COVERAGE_GATE = "pytest --cov-fail-under=92.71"

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


def render_issue_body(context: CoverageFailureContext) -> str:
    return (
        f"{ISSUE_MARKER}\n"
        f"Refs #{PARENT_ISSUE}\n"
        "\n"
        "## Scope\n"
        "\n"
        "Repair the post-merge coverage threshold failure and identify the deterministic gate that should prevent recurrence.\n"
        "\n"
        "## Facts\n"
        "\n"
        f"- Workflow: `{context.workflow}`\n"
        f"- Coverage job result: `{context.coverage_result}`\n"
        f"- Failed run: {context.run_url}\n"
        f"- Local coverage gate: `{COVERAGE_GATE}`\n"
        f"- Run id: `{context.run_id}`\n"
        f"- Run attempt: `{context.run_attempt}`\n"
        "\n"
        "## Assumptions\n"
        "\n"
        "- Speculation: the coverage percentage dropped below the repository floor after a merge to `main`.\n"
        "\n"
        "## Acceptance criteria\n"
        "\n"
        "- [ ] The coverage gate passes on `main` without lowering the configured threshold.\n"
        "- [ ] The missing test coverage or incorrect threshold movement is explained in this issue.\n"
        "- [ ] Any follow-up deterministic gate is linked here before closing.\n"
    )


def render_existing_issue_comment(context: CoverageFailureContext) -> str:
    return (
        "Another post-merge coverage failure hit the same tracking condition.\n"
        "\n"
        f"- Failed run: {context.run_url}\n"
        f"- Coverage job result: `{context.coverage_result}`\n"
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


def find_existing_issue(repo: str, *, runner: Runner = subprocess.run) -> int | None:
    result = _run_gh(
        [
            "gh",
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--search",
            ISSUE_MARKER,
            "--json",
            "number",
            "--limit",
            "1",
        ],
        runner=runner,
    )
    items = json.loads(result.stdout or "[]")
    if not items:
        return None
    first = items[0]
    if not isinstance(first, dict) or not isinstance(first.get("number"), int):
        raise RuntimeError("gh issue list returned an unexpected JSON shape")
    return first["number"]


def open_or_update_issue(
    context: CoverageFailureContext,
    *,
    runner: Runner = subprocess.run,
) -> str:
    existing = find_existing_issue(context.repo, runner=runner)
    if existing is not None:
        _run_gh(
            [
                "gh",
                "issue",
                "comment",
                str(existing),
                "--repo",
                context.repo,
            ],
            runner=runner,
            body=render_existing_issue_comment(context),
        )
        print(f"Updated existing coverage failure issue #{existing}.")
        return "commented"

    cmd = [
        "gh",
        "issue",
        "create",
        "--repo",
        context.repo,
        "--title",
        ISSUE_TITLE,
    ]
    for label in ISSUE_LABELS:
        cmd.extend(["--label", label])
    _run_gh(cmd, runner=runner, body=render_issue_body(context))
    print("Created coverage failure issue.")
    return "created"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("run")
    args = parser.parse_args(argv)

    if args.command == "run":
        try:
            context = context_from_env()
            open_or_update_issue(context)
        except (RuntimeError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
            print(f"::error::{error}", file=sys.stderr)
            return 1
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
