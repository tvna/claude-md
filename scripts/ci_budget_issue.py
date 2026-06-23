#!/usr/bin/env python3
"""Open or update a tracking issue when a CI wall-time budget is breached.

Soft-observability companion to ``scripts/analyze_ci_timings.py
--budget-seconds`` (#1156). The analyzer writes the breach set to a JSON file
via ``--budget-output``; this script reads that file and, when there is at
least one breach, opens; or idempotently updates; a single rolling
tracking issue. No breach is a no-op: the script never closes or reopens an
issue, because median wall time is non-deterministic across runners and this
is regression alerting, not a required status check.

The only GitHub access is through the approved REST wrapper
(``scripts/_github_api.apply_call``); no command-line ``gh`` is invoked. The
``--dry-run`` flag lets ``weekly-maintenance.yml`` plan on manual dispatch
without mutating state.

Usage::

    python3 scripts/ci_budget_issue.py run \\
        --repo owner/repo --breach-file budget.json \\
        --run-url URL [--dry-run true|false]

Environment:
    GH_TOKEN  GitHub token with issues:write scope.
    REPO      Fallback for --repo when the flag is omitted.

Contract:
- Inputs: the ``run`` subcommand; ``--breach-file`` (the JSON written by
  ``analyze_ci_timings.py --budget-output``); ``--repo`` (defaults to $REPO);
  ``--run-url``; ``--dry-run`` (true|false); env ``GH_TOKEN``.
- Outputs: with breaches and not dry-run, opens or comments on the rolling
  tracking issue via ``scripts/_github_api.apply_call`` (POST issue / POST
  comment) and prints a status line. Empty breach set or dry-run is a no-op
  that still exits 0.
- Failure policy: fails LOUD per CLAUDE.md section 4; a malformed breach
  file, a missing token, or a non-2xx API response exits 1 rather than
  silently treating it as "no breach".

Tested by ``tests/test_ci_budget_issue.py``. Refs #1156, #1150.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import quote

import issue_anchors
from _github_api import apply_call as github_apply_call

API_ROOT = "https://api.github.com"

# A hidden marker keeps the rolling issue idempotent: the search by title +
# label narrows the candidate set, then the marker disambiguates the one issue
# this script owns from any human-filed look-alike.
ISSUE_MARKER = "<!-- ci-budget-breach-issue -->"
ISSUE_TITLE = "ci(timings): verify-agents job over soft wall-time budget"
ISSUE_LABELS = ("type:tracking", "layer:p3-harness")
# Resolved from the declarative anchor table so a renumbering stays a
# one-file diff (#1640).
PARENT_ISSUE = issue_anchors.resolve("ci-budget-parent")

ApplyCall = Callable[..., tuple[int, str]]


def parse_dry_run(raw: str) -> bool:
    """Parse a workflow-supplied boolean string. Fail loud on anything else."""
    normalized = raw.strip().lower()
    if normalized in {"true", "1", "yes"}:
        return True
    if normalized in {"false", "0", "no", ""}:
        return False
    raise ValueError(f"--dry-run expects a boolean, got {raw!r}")


def load_breaches(path: Path) -> tuple[float, list[dict[str, Any]]]:
    """Read the ``--budget-output`` JSON and return ``(budget_seconds, breaches)``.

    Fails loud (CLAUDE.md s4) on a missing file or a payload that does not
    match the shape ``analyze_ci_timings.budget_breach_payload`` writes; a
    malformed breach set must not be silently treated as "no breach".
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"breach file {path} is not a JSON object")
    budget = data.get("budget_seconds")
    if not isinstance(budget, int | float):
        raise ValueError(f"breach file {path} has no numeric 'budget_seconds'")
    breaches = data.get("breaches")
    if not isinstance(breaches, list):
        raise ValueError(f"breach file {path} has no 'breaches' list")
    for entry in breaches:
        if not isinstance(entry, dict) or "job" not in entry or "p50" not in entry:
            raise ValueError(
                f"breach file {path} has a malformed breach entry: {entry!r}"
            )
    return float(budget), breaches


def render_breach_table(breaches: list[dict[str, Any]]) -> str:
    rows = ["| job | p50 (s) |", "| --- | ---: |"]
    for entry in breaches:
        rows.append(f"| {entry['job']} | {float(entry['p50']):.1f} |")
    return "\n".join(rows)


def render_issue_body(
    budget_seconds: float, breaches: list[dict[str, Any]], *, run_url: str
) -> str:
    return (
        f"{ISSUE_MARKER}\n"
        f"Refs #{PARENT_ISSUE}\n"
        "\n"
        "## Scope\n"
        "\n"
        "A weekly verify-agents timing scan found at least one job whose "
        "median (p50) wall time crossed the soft budget. This is "
        "observability, not a required status check: median wall time is "
        "non-deterministic across runners, so confirm the regression is real "
        "before optimizing.\n"
        "\n"
        "## Facts\n"
        "\n"
        f"- Soft budget: `{budget_seconds:.1f}` seconds per job (p50).\n"
        f"- Detector run: {run_url}\n"
        "\n"
        f"{render_breach_table(breaches)}\n"
        "\n"
        "## Acceptance criteria\n"
        "\n"
        "- [ ] Each listed job is either brought back under budget or the "
        "budget is revised with a rationale.\n"
        "- [ ] If the breach is runner variance rather than a real "
        "regression, that is recorded here before closing.\n"
    )


def render_update_comment(
    budget_seconds: float, breaches: list[dict[str, Any]], *, run_url: str
) -> str:
    return (
        "The soft wall-time budget is still breached on a later weekly scan.\n"
        "\n"
        f"- Soft budget: `{budget_seconds:.1f}` seconds per job (p50).\n"
        f"- Detector run: {run_url}\n"
        "\n"
        f"{render_breach_table(breaches)}\n"
    )


def find_existing_issue(repo: str, token: str, *, apply_call: ApplyCall) -> int | None:
    """Return the number of the open rolling issue, or ``None``.

    Narrows by title + ``type:tracking`` label via the Search API, then
    confirms the marker in the body so a human-filed look-alike with the same
    title is never mistaken for the one this script owns.
    """
    query = (
        f'repo:{repo} is:issue is:open label:type:tracking '
        f'in:title "{ISSUE_TITLE}"'
    )
    encoded = quote(query, safe="")
    code, body = apply_call(
        method="GET",
        url=f"{API_ROOT}/search/issues?q={encoded}&per_page=20",
        payload=None,
        token=token,
    )
    if not 200 <= code < 300:
        raise RuntimeError(f"search issues failed (HTTP {code}): {body[:200]}")
    items = json.loads(body).get("items") or []
    for item in items:
        if not isinstance(item, dict):
            continue
        if ISSUE_MARKER in (item.get("body") or "") and isinstance(
            item.get("number"), int
        ):
            return item["number"]
    return None


def open_or_update_issue(
    *,
    repo: str,
    token: str,
    budget_seconds: float,
    breaches: list[dict[str, Any]],
    run_url: str,
    apply_call: ApplyCall = github_apply_call,
) -> str:
    """Create the rolling issue, or comment on it if it already exists."""
    existing = find_existing_issue(repo, token, apply_call=apply_call)
    if existing is not None:
        code, body = apply_call(
            method="POST",
            url=f"{API_ROOT}/repos/{repo}/issues/{existing}/comments",
            payload={
                "body": render_update_comment(
                    budget_seconds, breaches, run_url=run_url
                )
            },
            token=token,
        )
        if not 200 <= code < 300:
            raise RuntimeError(f"comment failed (HTTP {code}): {body[:200]}")
        print(f"Updated existing CI budget tracking issue #{existing}.")
        return "commented"

    code, body = apply_call(
        method="POST",
        url=f"{API_ROOT}/repos/{repo}/issues",
        payload={
            "title": ISSUE_TITLE,
            "body": render_issue_body(budget_seconds, breaches, run_url=run_url),
            "labels": list(ISSUE_LABELS),
        },
        token=token,
    )
    if not 200 <= code < 300:
        raise RuntimeError(f"create issue failed (HTTP {code}): {body[:200]}")
    print("Created CI budget tracking issue.")
    return "created"


def _cmd_run(args: argparse.Namespace) -> int:
    dry_run = parse_dry_run(args.dry_run)
    budget_seconds, breaches = load_breaches(Path(args.breach_file))

    if not breaches:
        print("No CI budget breach; nothing to file.")
        return 0

    if dry_run:
        print(
            f"[dry-run] Would open/update the CI budget tracking issue for "
            f"{len(breaches)} job(s) over {budget_seconds:.1f}s."
        )
        return 0

    repo = args.repo or os.environ.get("REPO", "")
    if not repo:
        print("::error::--repo or REPO is required.", file=sys.stderr)
        return 1
    token = os.environ.get("GH_TOKEN", "")
    if not token:
        print("::error::GH_TOKEN is not set.", file=sys.stderr)
        return 1

    open_or_update_issue(
        repo=repo,
        token=token,
        budget_seconds=budget_seconds,
        breaches=breaches,
        run_url=args.run_url,
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Open/update the rolling budget issue")
    p_run.add_argument("--repo", default=None, help="owner/repo (defaults to $REPO)")
    p_run.add_argument(
        "--breach-file",
        required=True,
        dest="breach_file",
        help="Path to the --budget-output JSON written by analyze_ci_timings.py",
    )
    p_run.add_argument("--run-url", default="", dest="run_url", help="Detector run URL")
    p_run.add_argument("--dry-run", default="false", dest="dry_run", help="true|false")
    p_run.set_defaults(func=_cmd_run)

    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (RuntimeError, ValueError, OSError, json.JSONDecodeError) as error:
        print(f"::error::{error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
