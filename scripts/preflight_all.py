#!/usr/bin/env python3
"""Single entrypoint that runs CI's PR-gating verification set locally.

Closes the verification-drift gap identified by issue #493: 18 of 23 open
retrospective issues record at least one verification-drift repair, i.e. a
push landed locally but failed in CI because the developer ran a subset of
the gates. ``preflight_all.py`` runs the exact same scripts CI runs on
``pull_request:`` triggers, in the same order, with the same environment
contract, and reports per-step pass / fail / skip.

The set of steps lives in :data:`STEPS`. Each step declares:

* ``name`` -- a short identifier used in annotations and the
  ``--list`` machine-readable manifest consumed by
  :mod:`scan_preflight_drift`.
* ``argv`` -- the exact command line CI runs.
* ``required_env`` -- environment variables that must be set for the
  step to be meaningful (e.g. ``RULESETS_PAT`` for the live ruleset
  diff).
* ``soft`` -- when true and ``required_env`` is missing, the step is
  reported as a warning skip rather than a failure. Hard-required gates
  are kept ``soft=False`` so contributors cannot accidentally silence
  them.

Steps whose CI input is the PR / issue body (``title_policy``,
``body_policy``, ``issue_link``) are intentionally absent here -- their
client-side equivalents are the MCP PreToolUse hooks
``scripts/preflight_title_policy.py`` /
``scripts/preflight_pr_body_required_sections.py`` /
``scripts/pr_body_close_keyword_gate.py``, which gate the data at the
write-tool boundary instead of the working tree. The drift gate
(``scripts/scan_preflight_drift.py``) tracks this allowlist explicitly so
silent CI-vs-local drift is still detected.

Exit codes:
* ``0`` -- every step passed (or was correctly soft-skipped).
* ``1`` -- at least one step failed, or a hard-required step's
  ``required_env`` was missing.

Tested by ``tests/test_preflight_all.py``. Refs #493.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Step:
    """One verification gate runnable from preflight and CI alike."""

    name: str
    argv: tuple[str, ...]
    required_env: tuple[str, ...] = ()
    # When True, missing ``required_env`` or a missing executable on PATH
    # downgrades the step from failure to warning. Reserve for gates whose
    # local prerequisites legitimately differ from CI (network tokens,
    # uv-managed toolchain on a contributor laptop).
    soft: bool = False
    # External executables that must resolve on PATH for the step to run.
    # Treated the same as ``required_env`` for skip semantics.
    required_bin: tuple[str, ...] = field(default_factory=tuple)


# Order matches the order CI gates fire on a typical PR run: static
# repository-shape checks first (cheap, no toolchain), then static
# workflow / ruleset shape, then the uv-managed lint / type / test
# triple, then prek. ``verify_ruleset_sync`` requires the privileged
# RULESETS_PAT secret and is soft-skipped without it.
STEPS: tuple[Step, ...] = (
    Step(
        name="scan_apm_portability",
        argv=(
            "python3",
            "scripts/scan_apm_portability.py",
            "verify",
            "--path",
            ".apm/instructions/master.instructions.md",
            "--path",
            "CLAUDE.md",
            "--path",
            "AGENTS.md",
        ),
    ),
    Step(
        name="verify_apm_checksums",
        argv=("python3", "scripts/verify_apm_checksums.py", "verify"),
    ),
    Step(
        name="uv_pin_drift",
        argv=("python3", "scripts/uv_pin.py", "drift"),
    ),
    Step(
        name="nixpkgs_cooldown",
        argv=("python3", "scripts/nixpkgs_cooldown.py", "verify"),
    ),
    Step(
        name="scan_workflow_pip",
        argv=("python3", "scripts/scan_workflow_pip.py", "verify"),
    ),
    Step(
        name="scan_workflow_action_pins",
        argv=("python3", "scripts/scan_workflow_action_pins.py", "verify"),
    ),
    Step(
        name="scan_maintainability_metrics",
        argv=("python3", "scripts/scan_maintainability_metrics.py", "verify"),
    ),
    Step(
        name="scan_design_philosophy_drift",
        argv=(
            "python3",
            "scripts/scan_design_philosophy_drift.py",
            "verify",
            "--master",
            ".apm/instructions/master.instructions.md",
            "--doc",
            "docs/prd/agent-rules-design-philosophy.md",
        ),
    ),
    Step(
        name="dependabot_labels",
        argv=(
            "python3",
            "scripts/dependabot_labels.py",
            "verify",
            "--dependabot",
            ".github/dependabot.yml",
            "--labels",
            ".github/labels.json",
        ),
    ),
    Step(
        name="verify_required_check_contexts",
        argv=(
            "python3",
            "scripts/verify_required_check_contexts.py",
            "verify",
            "--sot-path",
            ".github/rulesets/main.json",
            "--workflows-dir",
            ".github/workflows",
        ),
    ),
    Step(
        name="auto_retro_decision_tree_doc",
        argv=("python3", "scripts/auto_retro.py", "decision-tree-doc"),
    ),
    Step(
        name="scan_preflight_drift",
        argv=("python3", "scripts/scan_preflight_drift.py", "verify"),
    ),
    Step(
        # Refs #545. Static check that every tests/test_*.py declares
        # exactly one module-scope shard marker so the lint-scripts-pytest
        # matrix neither skips a file nor double-counts one. Runs before
        # the pytest matrix in CI; mirrored here so contributors see the
        # failure pre-push.
        name="verify_test_shard_markers",
        argv=("python3", "scripts/verify_test_shard_markers.py"),
    ),
    Step(
        # Refs #492. Also wired via .pre-commit-config.yaml pre-push stage;
        # mirroring here keeps the single ``preflight_all.py`` entrypoint
        # truthful for contributors who use only the .githooks/pre-push hook.
        name="preflight_pr_single_commit",
        argv=("python3", "scripts/preflight_pr_single_commit.py"),
    ),
    Step(
        # Refs #476. PR body is optional locally (PR_BODY env unset means
        # the opt-out marker is absent, which is the stricter default --
        # contributors who run preflight see drift before push). The
        # base-ref shape mirrors CI's portable-pr-policy.yml step.
        name="verify_readme_translation",
        argv=(
            "python3",
            "scripts/verify_readme_translation.py",
            "verify",
            "--base-ref",
            "origin/main",
        ),
    ),
    Step(
        name="verify_ruleset_sync",
        argv=(
            "python3",
            "scripts/verify_ruleset_sync.py",
            "verify",
            "--repo",
            "tvna/claude-md",
            "--base-ref",
            "main",
            "--sot-path",
            ".github/rulesets/main.json",
            "--ruleset-name",
            "main-protection",
        ),
        required_env=("GH_TOKEN_API",),
        soft=True,
    ),
    Step(
        name="ruff",
        argv=("uv", "run", "ruff", "check", "scripts", "tests"),
        required_bin=("uv",),
        soft=True,
    ),
    Step(
        name="mypy",
        argv=("uv", "run", "mypy", "scripts", "tests"),
        required_bin=("uv",),
        soft=True,
    ),
    Step(
        name="pytest",
        argv=("uv", "run", "python", "-m", "pytest", "-q"),
        required_bin=("uv",),
        soft=True,
    ),
    Step(
        name="prek",
        argv=("uv", "tool", "run", "prek", "run", "--all-files", "--show-diff-on-failure"),
        required_bin=("uv",),
        soft=True,
    ),
)


@dataclass(frozen=True)
class StepResult:
    """Outcome of one :class:`Step` invocation."""

    name: str
    status: str  # "pass" | "fail" | "skip"
    detail: str = ""


def missing_prereqs(step: Step, environ: dict[str, str]) -> list[str]:
    """Return human-readable prereqs that are not satisfied for *step*.

    A prereq is either a missing environment variable from
    ``step.required_env`` or a missing executable from
    ``step.required_bin``. Order is stable and matches the declaration
    order so the surfaced message is deterministic.
    """
    missing: list[str] = []
    for key in step.required_env:
        if not environ.get(key):
            missing.append(f"env:{key}")
    for binary in step.required_bin:
        if shutil.which(binary) is None:
            missing.append(f"bin:{binary}")
    return missing


def run_step(step: Step, cwd: Path, environ: dict[str, str]) -> StepResult:
    """Execute *step* under *cwd* and return its :class:`StepResult`.

    Prerequisite handling: when any prereq is missing and ``step.soft``
    is true, the step is reported as ``skip`` with a human-readable
    detail. When ``step.soft`` is false, it is reported as ``fail`` --
    so a contributor who removed a hard prereq sees the failure rather
    than a silent green.
    """
    missing = missing_prereqs(step, environ)
    if missing:
        detail = "missing prereqs: " + ", ".join(missing)
        return StepResult(
            name=step.name,
            status="skip" if step.soft else "fail",
            detail=detail,
        )

    completed = subprocess.run(  # noqa: S603 -- argv is hard-coded in STEPS
        list(step.argv),
        cwd=cwd,
        check=False,
    )
    if completed.returncode == 0:
        return StepResult(name=step.name, status="pass")
    return StepResult(
        name=step.name,
        status="fail",
        detail=f"exit={completed.returncode}",
    )


def emit_summary(results: list[StepResult], stream) -> None:
    """Print a human-readable summary of *results* to *stream*.

    The format is intentionally line-oriented so it survives in GitHub
    Actions logs and `pre-push` terminal output. Each line is
    ``<status>  <name>  <detail>``.
    """
    width = max((len(r.name) for r in results), default=0)
    for result in results:
        line = f"{result.status:<5}  {result.name:<{width}}"
        if result.detail:
            line = f"{line}  {result.detail}"
        print(line, file=stream)


def emit_annotations(results: list[StepResult], stream) -> None:
    """Emit ``::error::`` / ``::warning::`` annotations for failed / skipped steps.

    These render as Annotations on the GitHub Actions run page when the
    same script runs inside CI, and remain readable plain text in the
    contributor's terminal.
    """
    for result in results:
        if result.status == "fail":
            print(f"::error::step '{result.name}' failed ({result.detail})", file=stream)
        elif result.status == "skip":
            print(f"::warning::step '{result.name}' skipped ({result.detail})", file=stream)


def list_manifest() -> list[dict[str, object]]:
    """Return :data:`STEPS` as a JSON-serializable manifest.

    Consumed by :mod:`scan_preflight_drift` to diff the local set
    against the script names invoked by ``.github/workflows/*.yml``.
    """
    return [
        {
            "name": step.name,
            "argv": list(step.argv),
            "required_env": list(step.required_env),
            "required_bin": list(step.required_bin),
            "soft": step.soft,
        }
        for step in STEPS
    ]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the same verification gates CI runs on pull_request:.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Print the step manifest as JSON and exit (no commands run).",
    )
    args = parser.parse_args(argv)

    if args.list:
        json.dump(list_manifest(), sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    environ = dict(os.environ)
    results = [run_step(step, REPO_ROOT, environ) for step in STEPS]
    emit_summary(results, sys.stdout)
    emit_annotations(results, sys.stderr)
    fails = sum(1 for r in results if r.status == "fail")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
