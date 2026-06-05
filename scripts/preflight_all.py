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
import time
from collections.abc import Sequence
from dataclasses import dataclass, field
from pathlib import Path

import preflight_cache

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
    # When True, the step is expensive (the full pytest suite). Heavy steps run
    # only after every cheap step has passed (fail-fast: a sub-second gate
    # failure short-circuits the ~5-min suite, refs #985) and are gated by the
    # content-addressed skip cache in ``scripts/preflight_cache.py`` so an
    # unchanged working tree skips the re-run while keeping CI coverage parity.
    heavy: bool = False


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
        # Refs #1207. Runtime gate: fails when ``uv --version`` does not match
        # ``[tool.uv].required-version``. Complements the static drift gate
        # above -- that one catches literal-value drift across the source
        # tree; this one catches the host-uv vs pin gap PR #1206 left open
        # for Claude Code's process PATH. ``soft=True`` so a contributor
        # laptop without uv warn-skips (the same posture as ruff/mypy below);
        # CI provisions uv via setup-uv before this step runs, so the gate is
        # hard there.
        name="preflight_uv_version",
        argv=("python3", "scripts/preflight_uv_version.py", "verify"),
        required_bin=("uv",),
        soft=True,
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
        name="scan_workflow_gh_calls",
        argv=("python3", "scripts/scan_workflow_gh_calls.py", "verify"),
    ),
    Step(
        name="scan_workflow_injection",
        argv=("python3", "scripts/scan_workflow_injection.py", "verify"),
    ),
    Step(
        name="scan_secret_runbooks",
        argv=("python3", "scripts/scan_secret_runbooks.py", "verify"),
    ),
    Step(
        name="scan_secrets",
        argv=("python3", "scripts/scan_secrets.py", "verify"),
    ),
    Step(
        name="scan_markdown_links",
        argv=("python3", "scripts/scan_markdown_links.py", "verify"),
    ),
    Step(
        name="scan_docs_inventory",
        argv=("python3", "scripts/scan_docs_inventory.py", "verify"),
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
        name="workflow_diagram_doc",
        argv=("python3", "scripts/workflow_diagram.py", "diagram-doc"),
    ),
    Step(
        name="scan_preflight_drift",
        argv=("python3", "scripts/scan_preflight_drift.py", "verify"),
    ),
    Step(
        # Refs #1087. Static gate enforcing M4 (boundary validation) and M9
        # (fail-loud/open) by requiring every workflow-called script to declare
        # a Contract: docstring block. Baseline debt lives in the script's
        # BASELINE_MISSING_CONTRACT and may only shrink.
        name="scan_input_contract_drift",
        argv=("python3", "scripts/scan_input_contract_drift.py", "verify"),
    ),
    Step(
        # Refs #1089. Fails when the workflow-script-quality standard and its
        # enforcement registry drift, or an `enforced`/`partial` must-have
        # names a backing gate that does not resolve.
        name="scan_quality_standard_drift",
        argv=("python3", "scripts/scan_quality_standard_drift.py", "verify"),
    ),
    Step(
        # Refs #1088. Fails when a scripts/*.py lacks its matching test module
        # (M2), a new GitHub-API script is absent from the boundary registry
        # (O6), or a workflow-invoked script has no CLI contract test (M3).
        name="scan_test_presence_drift",
        argv=("python3", "scripts/scan_test_presence_drift.py", "verify"),
    ),
    Step(
        # Refs #615. Fails when a Claude hook script is absent from Codex
        # coverage and is not in the explicit allowlist in the script.
        name="scan_hook_coverage_drift",
        argv=("python3", "scripts/scan_hook_coverage_drift.py", "verify"),
    ),
    Step(
        # Refs #1103. Fails when a tool a gate needs at runtime (a Step
        # required_bin) is not provisioned in flake.nix, so the devcontainer
        # cannot silently lack a tool the gates depend on.
        name="scan_devcontainer_tool_drift",
        argv=("python3", "scripts/scan_devcontainer_tool_drift.py", "verify"),
    ),
    Step(
        # Refs #1170. Fails when a .devcontainer/network/*.allowlist host has
        # no inline triage rationale, so a new egress destination cannot be
        # admitted without the observe/evaluate/decide record in
        # docs/runbooks/devcontainer-tool-network-triage.md.
        name="scan_allowlist_rationale",
        argv=("python3", "scripts/scan_allowlist_rationale.py", "verify"),
    ),
    Step(
        # Refs #1153. Fails when a pinned binary's flake.nix SHA256 is
        # hardcoded under scripts/ or .github/workflows/, so flake.nix stays
        # the single source of truth and a bump cannot leave a stale copy.
        name="scan_flake_pin_drift",
        argv=("python3", "scripts/scan_flake_pin_drift.py", "verify"),
    ),
    Step(
        # Refs #1154. Fails when a tool is compiled from source (go/cargo
        # install) on the CI surface instead of fetching a pinned prebuilt --
        # the ~138s regression class from #1150. Ack a justified backstop.
        name="scan_compile_from_source",
        argv=("python3", "scripts/scan_compile_from_source.py", "verify"),
    ),
    Step(
        # Refs #1155. Fails when a pre-commit hook that provisions a shared
        # binary (entry runs install_*.sh) is not require_serial, so prek
        # cannot race parallel copies on the shared path (the #1150
        # PermissionError class).
        name="scan_provisioning_hook_serial",
        argv=("python3", "scripts/scan_provisioning_hook_serial.py", "verify"),
    ),
    Step(
        # Refs #1230. Fails when a scripts/*.sh writes $CLAUDE_ENV_FILE
        # directly instead of persisting PATH via persist_session_path from
        # scripts/_session_path.sh -- the duplication that refactor removed.
        name="scan_session_path_drift",
        argv=("python3", "scripts/scan_session_path_drift.py", "verify"),
    ),
    Step(
        # Refs #1099. Runs waza spec-compliance over every skill under
        # .agents/skills. spec failure = fail, token budget = warning only.
        # Needs the pinned waza binary (scripts/install_waza.sh); soft so a
        # contributor laptop without waza/Go warns-and-skips while CI, which
        # installs waza first, enforces it.
        name="skill_quality_gate",
        argv=("python3", "scripts/skill_quality_gate.py", "verify"),
        required_bin=("waza",),
        soft=True,
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
        # Refs #178. Fails when a scheduled control family in
        # .github/security-control-floor.toml sits below the detect-and-file
        # floor without an exempt_reason, mirroring the verify-agents.yml
        # lint-scripts-static gate so the floor is checked pre-push too.
        name="verify_security_control_floor",
        argv=("python3", "scripts/verify_security_control_floor.py"),
    ),
    Step(
        # Refs #745. Fetches the live base branch and fails before push when
        # HEAD does not contain it, matching GitHub's out-of-date branch gate.
        name="preflight_branch_base",
        argv=("python3", "scripts/preflight_branch_base.py", "verify"),
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
        # Refs #1178. PR body is optional locally (PR_BODY unset means no
        # Text delta section, the stricter default so an instruction-text
        # change without the section surfaces before push). The base-ref
        # shape mirrors CI's portable-pr-policy.yml step; cutoff/created-at
        # are omitted so the local run always enforces.
        name="verify_text_delta_section",
        argv=(
            "python3",
            "scripts/verify_text_delta_section.py",
            "verify",
            "--base-ref",
            "origin/main",
        ),
    ),
    Step(
        # Refs #1190. Diff-coupling gate: a change to the principle source
        # must touch the design-philosophy matrix (or carry a
        # philosophy-matrix-ack line in the PR body). PR_BODY is unset
        # locally, the stricter default, so a master edit without the
        # matrix surfaces before push. Base-ref shape mirrors CI's
        # portable-pr-policy.yml step.
        name="scan_design_philosophy_drift_coupling",
        argv=(
            "python3",
            "scripts/scan_design_philosophy_drift.py",
            "verify-coupling",
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
        # Refs #985. Parallelised across cores with pytest-xdist (``-n auto``)
        # to cut the ~290s serial wall-clock without dropping a single test --
        # the same full universe CI runs (sharded across matrix legs) runs here
        # (sharded across local workers). xdist lives in the ``local`` uv group,
        # so the run activates it explicitly. ``heavy=True`` routes this step
        # through the fail-fast + skip-cache path in ``main``.
        name="pytest",
        argv=("uv", "run", "--group", "local", "python", "-m", "pytest", "-q", "-n", "auto"),
        required_bin=("uv",),
        soft=True,
        heavy=True,
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
    # Wall-clock seconds the step took. 0.0 for steps that never executed
    # (prereq skip, cache hit, upstream-failure skip). Surfaced per-step so the
    # slow gate is identifiable from the summary alone (refs #985).
    duration_s: float = 0.0


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

    start = time.monotonic()
    completed = subprocess.run(  # noqa: S603 -- argv is hard-coded in STEPS
        list(step.argv),
        cwd=cwd,
        check=False,
    )
    elapsed = time.monotonic() - start
    if completed.returncode == 0:
        return StepResult(name=step.name, status="pass", duration_s=elapsed)
    return StepResult(
        name=step.name,
        status="fail",
        detail=f"exit={completed.returncode}",
        duration_s=elapsed,
    )


def _heavy_fingerprint(heavy: Sequence[Step], cwd: Path) -> str | None:
    """Best-effort content fingerprint for the heavy tier, or ``None`` on error.

    The fingerprint folds in every heavy step's argv so a command change (e.g.
    adding ``-n auto``) busts a cache recorded under the old command. Any git or
    filesystem error degrades to ``None`` -- the caller then runs the full suite
    rather than trusting a fingerprint it could not compute (fail-open to the
    *slower, safer* path, never to a skip).
    """
    extra = tuple(token for step in heavy for token in step.argv)
    try:
        return preflight_cache.compute_fingerprint(cwd, extra=extra)
    except (OSError, subprocess.SubprocessError):
        return None


def run_all(
    steps: Sequence[Step],
    cwd: Path,
    environ: dict[str, str],
) -> list[StepResult]:
    """Run *steps* with fail-fast cheap-tier gating and a heavy-tier skip cache.

    Cheap steps run first, in declaration order, and all of them run so a single
    invocation reports every cheap failure at once. Heavy steps (the ~5-min
    pytest suite) then run only when **every** cheap step passed -- a sub-second
    gate failure (branch-base, ruff, mypy) short-circuits the
    suite instead of wasting it (refs #985, the PR #983 "5 minutes then rejected
    for an unrelated reason" failure mode).

    When the cheap tier is green, each heavy step is gated by the
    content-addressed cache: if the test-relevant working tree is byte-identical
    to the last recorded green run, the step is reported ``pass (cached)`` and
    not re-executed. This preserves CI coverage parity (the same full suite is
    what produced the cached pass) while killing the multi-push re-run multiplier
    on an unchanged tree. After a heavy tier that actually executed and passed,
    the fingerprint is recorded for the next push.
    """
    cheap = [s for s in steps if not s.heavy]
    heavy = [s for s in steps if s.heavy]

    cheap_results = [run_step(step, cwd, environ) for step in cheap]
    cheap_failed = [r.name for r in cheap_results if r.status == "fail"]

    if not heavy:
        return cheap_results

    if cheap_failed:
        blocked = "upstream gate failed: " + ", ".join(cheap_failed)
        heavy_results = [
            StepResult(name=step.name, status="skip", detail=blocked) for step in heavy
        ]
        return cheap_results + heavy_results

    fingerprint = _heavy_fingerprint(heavy, cwd)
    cache_file = preflight_cache.cache_path(cwd)
    cache = preflight_cache.load(cache_file)
    disabled = preflight_cache.cache_disabled(environ)
    fresh = (
        not disabled
        and fingerprint is not None
        and preflight_cache.is_fresh(cache, fingerprint)
    )

    heavy_results = []
    ran_any = False
    for step in heavy:
        if fresh:
            ts = cache.get("recorded_at", "?") if cache else "?"
            heavy_results.append(
                StepResult(
                    name=step.name,
                    status="pass",
                    detail=f"cached: tree unchanged since last green run at {ts}",
                )
            )
        else:
            heavy_results.append(run_step(step, cwd, environ))
            ran_any = True

    if ran_any and fingerprint is not None and all(r.status == "pass" for r in heavy_results):
        preflight_cache.record(cache_file, fingerprint)

    return cheap_results + heavy_results


def emit_summary(results: list[StepResult], stream) -> None:
    """Print a human-readable summary of *results* to *stream*.

    The format is intentionally line-oriented so it survives in GitHub
    Actions logs and `pre-push` terminal output. Each line is
    ``<status>  <name>  <detail>``.
    """
    width = max((len(r.name) for r in results), default=0)
    for result in results:
        line = f"{result.status:<5}  {result.name:<{width}}  {result.duration_s:7.2f}s"
        if result.detail:
            line = f"{line}  {result.detail}"
        print(line, file=stream)
    total = sum(r.duration_s for r in results)
    print(f"{'total':<5}  {'':<{width}}  {total:7.2f}s", file=stream)


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
            "heavy": step.heavy,
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
    results = run_all(STEPS, REPO_ROOT, environ)
    emit_summary(results, sys.stdout)
    emit_annotations(results, sys.stderr)
    fails = sum(1 for r in results if r.status == "fail")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
