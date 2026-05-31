#!/usr/bin/env python3
"""Scan .github/workflows/*.yml for unallowlisted direct ``gh`` CLI calls.

Policy (issue #911): workflow ``run:`` blocks must not invoke the ``gh``
CLI unless the (workflow, step) pair is documented in :data:`ALLOWLIST_ENTRIES`
with an explicit migration rationale.

ALLOWLIST_ENTRIES is expected to shrink as each migration PR lands.  When
the list is empty the gate is fully strict: any new ``gh`` call without a
matching allowlist entry fails CI.

CLI::

    python3 scripts/scan_workflow_gh_calls.py verify  # exit 1 on violations
    python3 scripts/scan_workflow_gh_calls.py list    # print all gh calls

Exit codes:
    0  verify passed (no violations) or list completed
    1  verify found unallowlisted gh calls
    2  usage error

Refs #911.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

import yaml

WORKFLOW_DIR = Path(".github/workflows")

# Same subcommand set as gate_gh_cli.py for consistency.
_GH_CLI_RE = re.compile(
    r"(?:^|(?<=[\s;|&(`]))gh\s+"
    r"(?:api|auth|browse|codespace|co|gist|gpg-key|issue|label|org|pr|"
    r"project|release|repo|ruleset|run|search|secret|ssh-key|status|variable|workflow)\b",
    re.MULTILINE,
)

_FRAGMENT_LEN = 80


class Violation(NamedTuple):
    workflow: str   # file basename
    job: str        # job key
    step: str       # step name, or "" if unnamed
    fragment: str   # first gh … fragment from the run block


# ---------------------------------------------------------------------------
# Allowlist
#
# Each entry documents one intentional exception pending migration.
# Required keys: ``workflow`` (basename), ``step`` (verbatim name:),
# ``rationale`` (one-line with tracking issue).
#
# Remove entries as each ``gh`` call is replaced by a tested Python script.
# When the list is empty the gate enforces zero direct gh usage.
# ---------------------------------------------------------------------------
ALLOWLIST_ENTRIES: list[dict[str, str]] = [
    {
        "workflow": "generate-agents.yml",
        "step": "Open pull request if generated instructions changed",
        "rationale": "gh pr view/edit/create for automated PR upsert; migration tracked in #911",
    },
    {
        "workflow": "post-merge.yml",
        "step": "Open pull request if any generated doc changed",
        "rationale": "gh pr view/edit/create for automated PR upsert; migration tracked in #911",
    },
    {
        "workflow": "issue-pr-triage.yml",
        "step": "Apply threat labels",
        "rationale": "gh issue edit --add-label for threat label application; migration tracked in #911",
    },
    {
        "workflow": "issue-pr-triage.yml",
        "step": "Remove stale threat labels",
        "rationale": "gh issue edit --remove-label for stale label cleanup; migration tracked in #911",
    },
    {
        "workflow": "dependabot-automerge.yml",
        "step": "Collect changed files",
        "rationale": "gh pr diff --name-only to collect PR file list; migration tracked in #911",
    },
    {
        "workflow": "dependabot-automerge.yml",
        "step": "Request GitHub auto-merge",
        "rationale": "gh pr merge --auto --squash to enable auto-merge; migration tracked in #911",
    },
    {
        "workflow": "backup-non-ascii-originals.yml",
        "step": "Capture issues, PRs, and comments",
        "rationale": "gh api --paginate for issues/PRs/comments bulk fetch; migration tracked in #911",
    },
    {
        "workflow": "backup-non-ascii-originals.yml",
        "step": "Post SHA-256 to issue",
        "rationale": "gh issue comment to post backup summary; migration tracked in #911",
    },
    {
        "workflow": "publish-devcontainer-images.yml",
        "step": "Open pin update PR",
        "rationale": "gh pr view/list/create/merge for pin-update PR management; migration tracked in #911",
    },
    {
        "workflow": "weekly-maintenance.yml",
        "step": "Resolve default branch",
        "rationale": "gh api to resolve default_branch name; migration tracked in #911",
    },
    {
        "workflow": "weekly-maintenance.yml",
        "step": "Fetch verify-agents.yml runs",
        "rationale": "gh api for CI timing data collection; migration tracked in #911",
    },
    {
        "workflow": "weekly-maintenance.yml",
        "step": "Fetch per-run jobs",
        "rationale": "gh api for per-run job timing data; migration tracked in #911",
    },
    {
        "workflow": "weekly-maintenance.yml",
        "step": "Post report as comment on dispatch issue",
        "rationale": "gh issue comment to post timing report; migration tracked in #911",
    },
]

_ALLOWLIST_KEYS: frozenset[tuple[str, str]] = frozenset(
    (e["workflow"], e["step"]) for e in ALLOWLIST_ENTRIES
)


def _load_yaml(wf_path: Path) -> dict | None:
    """Return parsed YAML dict, or None if the file is missing or not a dict."""
    try:
        data = yaml.safe_load(wf_path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _iter_run_steps(
    workflow_dir: Path,
) -> Iterator[tuple[str, str, str, str]]:
    """Yield (workflow_basename, job_id, step_name, run_text) for steps with a run block.

    Skips workflow files that cannot be parsed as YAML dicts.
    Skips steps that lack a ``run:`` string value.
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


def find_violations(
    workflow_dir: Path = WORKFLOW_DIR,
) -> list[Violation]:
    """Return a Violation for every unallowlisted ``gh`` CLI call in workflow run: blocks."""
    violations: list[Violation] = []
    for wf_name, job_id, step_name, run_text in _iter_run_steps(workflow_dir):
        match = _GH_CLI_RE.search(run_text)
        if match is None:
            continue
        if (wf_name, step_name) in _ALLOWLIST_KEYS:
            continue
        fragment = run_text[match.start() : match.start() + _FRAGMENT_LEN].strip()
        violations.append(Violation(workflow=wf_name, job=job_id, step=step_name, fragment=fragment))
    return violations


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Scan workflow YAML files for unallowlisted gh CLI calls.",
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("verify", help="Exit 1 if any unallowlisted gh call is found")
    sub.add_parser("list", help="Print all gh calls found (both allowed and violations)")
    args = parser.parse_args(argv)

    wf_dir = WORKFLOW_DIR

    if args.cmd == "list":
        for wf_name, job_id, step_name, run_text in _iter_run_steps(wf_dir):
            match = _GH_CLI_RE.search(run_text)
            if match is None:
                continue
            status = "ALLOWED" if (wf_name, step_name) in _ALLOWLIST_KEYS else "VIOLATION"
            fragment = run_text[match.start() : match.start() + _FRAGMENT_LEN].strip()
            print(f"[{status}] {wf_name} / {job_id} / {step_name!r}: {fragment!r}")
        return 0

    violations = find_violations(wf_dir)
    if not violations:
        return 0

    for v in violations:
        print(
            f"::error file=.github/workflows/{v.workflow}::"
            f"Unallowlisted gh CLI call in step {v.step!r} (job: {v.job}): "
            f"{v.fragment!r}. "
            f"Migrate to a tested Python script or add an allowlist entry with "
            f"rationale in scripts/scan_workflow_gh_calls.py ALLOWLIST_ENTRIES.",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
