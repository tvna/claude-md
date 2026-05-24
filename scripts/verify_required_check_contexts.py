"""Static gate: every SoT required_status_check context must be produced by a workflow job.

GitHub Rulesets matches `required_status_checks[].context` against the
`check_run.name` reported by GitHub Actions. For GitHub Actions check_runs
this defaults to the job id unless `jobs.<job_id>.name` is set explicitly,
so a workflow with `name: Verify ruleset sync` and `jobs.gate.<no name>:`
reports a check_run named `gate` -- which does NOT match a SoT context
of `"Verify ruleset sync / gate"`. Issue #287 captures the silent break
this caused (PR #271, PR #274 both merged via admin bypass because the
required gates never resolved).

This script is the missing deterministic gate. For every context declared
in `.github/rulesets/main.json` `required_status_checks`, it requires that
some `.github/workflows/*.yml` declare a `jobs.<job_id>.name` value
matching the context literally. Drift in either direction (SoT renamed,
workflow renamed, or workflow's explicit `name:` removed) fails the gate
with an actionable error message.

The check is purely static: no GitHub API calls, no PR head SHA needed.
It runs on every PR via `verify-ruleset-sync.yml` and can also be invoked
locally:

    python3 scripts/verify_required_check_contexts.py verify \
        --sot-path .github/rulesets/main.json \
        --workflows-dir .github/workflows

Refs #287.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def load_sot_contexts(sot_path: Path) -> list[str]:
    """Return the list of required_status_check context strings declared in *sot_path*.

    Returns an empty list when the ruleset does not contain a
    `required_status_checks` rule (still a valid SoT shape).
    """
    data = json.loads(sot_path.read_text(encoding="utf-8"))
    rules = data.get("rules") or []
    for rule in rules:
        if rule.get("type") != "required_status_checks":
            continue
        params = rule.get("parameters") or {}
        checks = params.get("required_status_checks") or []
        return [str(item.get("context") or "") for item in checks if item.get("context")]
    return []


def parse_workflow(yaml_text: str) -> dict[str, Any]:
    """Extract the two fields this verifier needs (workflow `name:` and each
    `jobs.<job_id>.name:`) without relying on a full YAML parser.

    GitHub Actions workflows frequently include shell heredocs with
    column-1 content inside `run: |` blocks (e.g. `.github/workflows/
    threat-intel-triage.yml`). PyYAML rejects those as invalid block
    scalars, even though `actions/runner` accepts them. To avoid a
    parser dependency that would make this gate strictly less robust
    than the runtime, the verifier walks the file line by line and
    matches only the two indentation patterns it cares about:

    - top-level `name:` (column 0)
    - `jobs.<job_id>:` (exact 2-space indent, no further colon on the line)
    - that job's `name:` (exact 4-space indent inside the job mapping)

    Step names (column 6+ with `- name:` prefix) and nested mappings
    are intentionally ignored. Quoted and unquoted scalars are both
    supported. Multi-line scalars are NOT supported for these two
    fields; no current workflow uses them.
    """
    workflow_name = ""
    jobs: dict[str, dict[str, Any]] = {}
    current_job: str | None = None
    in_jobs = False
    for line in yaml_text.splitlines():
        if line.startswith("name:"):
            workflow_name = _strip_scalar(line[len("name:"):])
            continue
        if line.startswith("jobs:"):
            in_jobs = True
            continue
        if not in_jobs:
            continue
        if line.startswith("  ") and not line.startswith("    "):
            stripped = line[2:]
            if stripped.endswith(":") and ":" not in stripped[:-1]:
                current_job = stripped[:-1].strip()
                jobs[current_job] = {}
                continue
        if current_job and line.startswith("    name:"):
            jobs[current_job]["name"] = _strip_scalar(line[len("    name:"):])
    return {"name": workflow_name, "jobs": jobs}


def _strip_scalar(raw: str) -> str:
    """Strip whitespace and surrounding quotes from a YAML scalar value."""
    value = raw.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        value = value[1:-1]
    return value


def produced_check_names(workflows_dir: Path) -> dict[str, tuple[str, str]]:
    """Walk `*.yml` workflows under *workflows_dir* and map each effective
    `check_run.name` to its `(workflow_file, job_id)` origin.

    Effective name is `jobs.<job_id>.name` when set, else the job id
    itself. The map's key is what GitHub Rulesets matches against
    `required_status_checks[].context`.
    """
    produced: dict[str, tuple[str, str]] = {}
    for yaml_file in sorted(workflows_dir.glob("*.yml")):
        try:
            text = yaml_file.read_text(encoding="utf-8")
        except OSError:
            continue
        parsed = parse_workflow(text)
        jobs = parsed.get("jobs") or {}
        if not isinstance(jobs, dict):
            continue
        for job_id, job_def in jobs.items():
            if not isinstance(job_def, dict):
                continue
            explicit_name = job_def.get("name")
            check_name = str(explicit_name) if explicit_name else str(job_id)
            produced.setdefault(check_name, (yaml_file.name, str(job_id)))
    return produced


def find_missing(
    sot_contexts: list[str], produced: dict[str, tuple[str, str]]
) -> list[str]:
    """Return SoT contexts that have no matching produced check name."""
    return [ctx for ctx in sot_contexts if ctx not in produced]


def _cmd_verify(args: argparse.Namespace) -> int:
    sot_path = Path(args.sot_path)
    workflows_dir = Path(args.workflows_dir)
    sot_contexts = load_sot_contexts(sot_path)
    if not sot_contexts:
        print(f"OK: {sot_path} declares no required_status_checks contexts.")
        return 0
    produced = produced_check_names(workflows_dir)
    missing = find_missing(sot_contexts, produced)
    if missing:
        print(
            "::error::Required-status-check contexts declared in "
            f"{sot_path} do not match any workflow job's effective "
            "check_run.name. Each context must equal either an explicit "
            "`jobs.<job_id>.name:` value or, when absent, the job id "
            "itself. See issue #287 for the silent-break reproducer.",
            file=sys.stderr,
        )
        for ctx in missing:
            print(f"::error::missing: {ctx!r}", file=sys.stderr)
        return 1
    print(
        f"OK: every required_status_check context in {sot_path} matches "
        f"a workflow job in {workflows_dir} (checked {len(sot_contexts)} contexts)."
    )
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    verify = sub.add_parser(
        "verify",
        help="Assert that every SoT required_status_check context is produced "
        "by some workflow job's effective check_run.name.",
    )
    verify.add_argument("--sot-path", required=True)
    verify.add_argument("--workflows-dir", required=True)
    verify.set_defaults(func=_cmd_verify)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
