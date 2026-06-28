#!/usr/bin/env python3
"""Flag ``git push`` in workflow ``run:`` blocks; the unsigned-commit authoring path.

A commit pushed via ``git push`` from a runner is authored by whatever token
``actions/checkout`` persisted (the default ``github-actions[bot]``) and is
**not** signed by GitHub: ``git`` cannot mint GitHub's web-flow signature, and a
GitHub App account cannot hold its own signing key. So every PR-branch commit
produced this way shows as Unverified and is authored by github-actions[bot]
rather than the App bot.

The repository's adopted path for bot-generated PR commits is the signed GraphQL
``createCommitOnBranch`` mutation (``scripts/pr_upsert.py`` -> ``upsert_files_pr``
/ ``upsert_single_file_pr``), run under a GitHub App installation token minted by
``actions/create-github-app-token``. That path produces Verified commits authored
by the App bot and, by construction, appends onto the branch (no force-push, so
the all-branches ``non_fast_forward`` ruleset is satisfied). Refs #1437, #1466.

This gate is the deterministic sibling of ``scan_workflow_injection.py`` and
``scan_workflow_pip.py``: it is a regression guard that keeps a workflow from
reintroducing the unsigned ``git push`` authoring path once every workflow has
migrated. It scans only ``run:`` values; ``git push`` mentioned in a comment
elsewhere is not matched.

Escape hatch: append ``# unsigned-ack`` to the offending line when a ``git push``
is genuinely required and has been reviewed (for example, a push that does not
author repository content, or a flow with no signing/authorship requirement).

CLI::

    python3 scripts/scan_workflow_unsigned_commit.py verify  # exit 1 on violations
    python3 scripts/scan_workflow_unsigned_commit.py list     # print all matches

Exit codes:
    0  verify passed (no violations) or list completed
    1  verify found a git push in a run block
    2  usage error

Tested by ``tests/test_scan_workflow_unsigned_commit.py``.

Contract:
    Inputs: the ``.github/workflows/*.yml`` tree (no stdin, no env input).
    Outputs: ``::error file=...::`` annotations on stderr and a one-line summary;
        exit code as documented above.
    Failure policy: loud; a workflow that cannot be parsed as YAML is skipped,
        but any detected ``git push`` fails the gate with a non-zero exit rather
        than passing silently.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import Any, NamedTuple

import yaml

WORKFLOW_DIR = Path(".github/workflows")

# Lines carrying this marker bypass the scan. Mirrors the ACK escape-hatch
# precedent of ``scripts/scan_workflow_injection.py``.
ACK_MARKER = "# unsigned-ack"

# ``git push`` in any form (``git push``, ``git   push``, ``git push --force...``).
_GIT_PUSH = re.compile(r"\bgit\s+push\b")

_FRAGMENT_LEN = 80


class Violation(NamedTuple):
    workflow: str  # file basename
    job: str       # job key
    step: str      # step name, or "" if unnamed
    line: int      # 1-based line number within the run block
    fragment: str  # trimmed fragment starting at the match


def _load_yaml(wf_path: Path) -> dict[str, Any] | None:
    """Return parsed YAML dict, or None if the file is missing or not a dict."""
    try:
        data = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _iter_run_steps(workflow_dir: Path) -> Iterator[tuple[str, str, str, str]]:
    """Yield ``(workflow_basename, job_id, step_name, run_text)`` for run steps.

    Skips workflow files that cannot be parsed as YAML dicts and steps that lack a
    string ``run:`` value.
    """
    for wf_path in sorted(workflow_dir.glob("*.yml")):
        data = _load_yaml(wf_path)
        if data is None:
            continue
        jobs = data.get("jobs") or {}
        if not isinstance(jobs, dict):
            continue
        for job_id, job in jobs.items():
            if not isinstance(job, dict):
                continue
            steps = job.get("steps") or []
            if not isinstance(steps, list):
                continue
            for step in steps:
                if not isinstance(step, dict):
                    continue
                run_text = step.get("run")
                if not isinstance(run_text, str):
                    continue
                step_name = str(step.get("name") or "")
                yield wf_path.name, str(job_id), step_name, run_text


def scan_run_text(run_text: str) -> list[tuple[int, str]]:
    """Return ``(line_number, fragment)`` for each ``git push`` in *run_text*.

    Line numbers are 1-based within *run_text*. Lines carrying :data:`ACK_MARKER`
    are treated as reviewed exceptions and skipped.
    """
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(run_text.splitlines(), start=1):
        if ACK_MARKER in line:
            continue
        match = _GIT_PUSH.search(line)
        if match is not None:
            fragment = line[match.start() : match.start() + _FRAGMENT_LEN].strip()
            hits.append((lineno, fragment))
    return hits


def _iter_matches(workflow_dir: Path) -> Iterator[Violation]:
    for wf_name, job_id, step_name, run_text in _iter_run_steps(workflow_dir):
        for lineno, fragment in scan_run_text(run_text):
            yield Violation(workflow=wf_name, job=job_id, step=step_name, line=lineno, fragment=fragment)


def find_violations(workflow_dir: Path = WORKFLOW_DIR) -> list[Violation]:
    """Return a Violation for every ``git push`` in a run block."""
    return list(_iter_matches(workflow_dir))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan workflow run: blocks for the unsigned git push authoring path.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify", help="Exit 1 if any git push is found in a run block")
    sub.add_parser("list", help="Print every git push found in a run block")
    args = parser.parse_args(argv)

    wf_dir = WORKFLOW_DIR

    if args.cmd == "list":
        for v in _iter_matches(wf_dir):
            print(f"{v.workflow} / {v.job} / {v.step!r} line {v.line}: {v.fragment!r}")
        return 0

    violations = find_violations(wf_dir)
    if not violations:
        print("OK: no git push (unsigned authoring path) in workflow run blocks.")
        return 0

    for v in violations:
        print(
            f"::error file=.github/workflows/{v.workflow}::"
            f"git push in step {v.step!r} (job: {v.job}) authors an unsigned commit as "
            f"github-actions[bot]: {v.fragment!r}. Use the signed createCommitOnBranch path "
            f"(scripts/pr_upsert.py upsert-files) under a create-github-app-token token, or "
            f"append '{ACK_MARKER}' to the line if reviewed safe.",
            file=sys.stderr,
        )
    print(
        f"FAIL: {len(violations)} git push (unsigned authoring path) in workflow run blocks.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
