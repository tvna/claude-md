#!/usr/bin/env python3
"""Scan .github/workflows/*.yml for unallowlisted direct GitHub API calls.

Policy (issue #911): workflow ``run:`` blocks must not invoke the ``gh``
CLI, nor ``curl`` the GitHub REST API (``api.github.com`` /
``uploads.github.com``) directly, unless the (workflow, step) pair is
documented in :data:`ALLOWLIST_ENTRIES` with an explicit migration rationale.
Both shapes embed GitHub behaviour in YAML where it cannot be unit tested;
the fix is the same; move it behind a tested ``scripts/*.py`` helper.

ALLOWLIST_ENTRIES is expected to shrink as each migration PR lands.  When
the list is empty the gate is fully strict: any new ``gh`` call or direct
``curl`` to the GitHub API without a matching allowlist entry fails CI.

CLI::

    python3 scripts/scan_workflow_gh_calls.py verify  # exit 1 on violations
    python3 scripts/scan_workflow_gh_calls.py list    # print all matches

Exit codes:
    0  verify passed (no violations) or list completed
    1  verify found unallowlisted gh / curl calls
    2  usage error

Refs #911.
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

# Same subcommand set as gate_gh_cli.py for consistency.
_GH_CLI_RE = re.compile(
    r"(?:^|(?<=[\s;|&(`]))gh\s+"
    r"(?:api|auth|browse|codespace|co|gist|gpg-key|issue|label|org|pr|"
    r"project|release|repo|ruleset|run|search|secret|ssh-key|status|variable|workflow)\b",
    re.MULTILINE,
)

# A ``curl`` invocation anywhere in the run block …
_CURL_RE = re.compile(r"(?:^|(?<=[\s;|&(`]))curl\b", re.MULTILINE)
# … combined with a GitHub REST API host is a direct-API violation.  The uv
# release download (``github.com/astral-sh/...``) is intentionally NOT matched.
_GITHUB_API_HOST_RE = re.compile(r"\b(?:api|uploads)\.github\.com\b")

_FRAGMENT_LEN = 80


class Violation(NamedTuple):
    workflow: str        # file basename
    job: str             # job key
    step: str            # step name, or "" if unnamed
    fragment: str        # first matching fragment from the run block
    kind: str = "gh"     # "gh" (gh CLI) or "curl" (direct GitHub API curl)


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
ALLOWLIST_ENTRIES: list[dict[str, str]] = []

_ALLOWLIST_KEYS: frozenset[tuple[str, str]] = frozenset(
    (e["workflow"], e["step"]) for e in ALLOWLIST_ENTRIES
)


def _load_yaml(wf_path: Path) -> dict[str, Any] | None:
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


def _fragment_at(run_text: str, start: int) -> str:
    """Return a trimmed fragment of the run block starting at ``start``."""
    return run_text[start : start + _FRAGMENT_LEN].strip()


def _iter_matches(workflow_dir: Path) -> Iterator[Violation]:
    """Yield a Violation for every ``gh`` CLI call and direct GitHub-API ``curl``.

    Allowlist filtering is the caller's responsibility; this yields all matches.
    """
    for wf_name, job_id, step_name, run_text in _iter_run_steps(workflow_dir):
        gh_match = _GH_CLI_RE.search(run_text)
        if gh_match is not None:
            yield Violation(
                workflow=wf_name,
                job=job_id,
                step=step_name,
                fragment=_fragment_at(run_text, gh_match.start()),
                kind="gh",
            )
        if _CURL_RE.search(run_text) is not None:
            api_match = _GITHUB_API_HOST_RE.search(run_text)
            if api_match is not None:
                yield Violation(
                    workflow=wf_name,
                    job=job_id,
                    step=step_name,
                    fragment=_fragment_at(run_text, api_match.start()),
                    kind="curl",
                )


def find_violations(
    workflow_dir: Path = WORKFLOW_DIR,
) -> list[Violation]:
    """Return a Violation for every unallowlisted gh CLI call or direct GitHub-API curl."""
    return [v for v in _iter_matches(workflow_dir) if (v.workflow, v.step) not in _ALLOWLIST_KEYS]


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
        for v in _iter_matches(wf_dir):
            status = "ALLOWED" if (v.workflow, v.step) in _ALLOWLIST_KEYS else "VIOLATION"
            print(f"[{status}] ({v.kind}) {v.workflow} / {v.job} / {v.step!r}: {v.fragment!r}")
        return 0

    violations = find_violations(wf_dir)
    if not violations:
        return 0

    for v in violations:
        what = "gh CLI call" if v.kind == "gh" else "direct GitHub API curl"
        print(
            f"::error file=.github/workflows/{v.workflow}::"
            f"Unallowlisted {what} in step {v.step!r} (job: {v.job}): "
            f"{v.fragment!r}. "
            f"Migrate to a tested Python script or add an allowlist entry with "
            f"rationale in scripts/scan_workflow_gh_calls.py ALLOWLIST_ENTRIES.",
            file=sys.stderr,
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
