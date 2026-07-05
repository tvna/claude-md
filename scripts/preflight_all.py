#!/usr/bin/env python3
"""Single entrypoint that runs CI's PR-gating verification set locally.

Closes the verification-drift gap identified by issue #493: 18 of 23 open
retrospective issues record at least one verification-drift repair, i.e. a
push landed locally but failed in CI because the developer ran a subset of
the gates. ``preflight_all.py`` runs the exact same scripts CI runs on
``pull_request:`` triggers, in the same order, with the same environment
contract, and reports per-step pass / fail / skip.

The set of steps lives in :data:`STEPS`. Each step declares:

* ``name``; a short identifier used in annotations and the
  ``--list`` machine-readable manifest consumed by tests and tooling
  that verify the declared step set (e.g. ``tests/test_scan_session_path_drift.py``).
* ``argv``; the exact command line CI runs.
* ``required_env``; environment variables that must be set for the
  step to be meaningful (e.g. ``RULESETS_PAT`` for the live ruleset
  diff).
* ``soft``; when true and ``required_env`` is missing, the step is
  reported as a warning skip rather than a failure. Hard-required gates
  are kept ``soft=False`` so contributors cannot accidentally silence
  them.

Steps whose CI input is the PR / issue body (``title_policy``,
``body_policy``, ``issue_link``) are intentionally absent here; their
client-side equivalents are the MCP PreToolUse hooks
``scripts/preflight_title_policy.py`` /
``scripts/preflight_pr_body_required_sections.py`` /
``scripts/pr_body_close_keyword_gate.py``, which gate the data at the
write-tool boundary instead of the working tree. The drift gate
(``scripts/scan_ssot_drift.py``) tracks this allowlist explicitly so
silent CI-vs-local drift is still detected.

Exit codes:
* ``0``; every step passed (or was correctly soft-skipped).
* ``1``; at least one step failed, or a hard-required step's
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
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from pathlib import Path

import preflight_cache
from preflight_steps import STEPS, Step

REPO_ROOT = Path(__file__).resolve().parent.parent


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
    filesystem error degrades to ``None``; the caller then runs the full suite
    rather than trusting a fingerprint it could not compute (fail-open to the
    *slower, safer* path, never to a skip).
    """
    extra = tuple(token for step in heavy for token in step.argv)
    try:
        return preflight_cache.compute_fingerprint(cwd, extra=extra)
    except (OSError, subprocess.SubprocessError):
        return None


# Cheap steps that mutate the working tree or take a git lock; they must not
# run concurrently with the working-tree-reading static gates, so the parallel
# tier runs them first, sequentially (refs #1245):
#   * preflight_branch_base; ``git fetch`` writes .git refs and takes a lock.
# No generated docs are regenerated here: docs/generated/scripts/ (#1540) and
# docs/generated/workflows/ (#1771) are both owned by the post-merge automation,
# so the pre-push lane writes nothing under docs/generated/.
_SERIAL_CHEAP: frozenset[str] = frozenset({
    "preflight_branch_base",
})


def _cheap_workers(n: int, environ: dict[str, str]) -> int:
    """Return the worker count for the parallel cheap tier.

    Honours ``PREFLIGHT_CHEAP_WORKERS`` (a positive int) as an override and
    escape hatch; ``=1`` restores the fully serial behaviour for bisecting a
    suspected ordering bug. Otherwise scales to ``2x`` cores (the steps are
    subprocess / I-O bound), capped at 16 to avoid a fork storm, and never
    exceeds *n*.
    """
    override = environ.get("PREFLIGHT_CHEAP_WORKERS", "").strip()
    if override:
        try:
            value = int(override)
        except ValueError:
            value = 0
        if value >= 1:
            return max(1, min(value, n))
    return max(1, min(n, (os.cpu_count() or 4) * 2, 16))


def _run_cheap(
    cheap: Sequence[Step], cwd: Path, environ: dict[str, str]
) -> list[StepResult]:
    """Run the cheap tier, returning results in *cheap* declaration order.

    Steps named in :data:`_SERIAL_CHEAP` mutate the working tree or take a git
    lock, so they run first and sequentially, before any working-tree-reading
    gate runs in parallel. The remaining steps; pure static file reads and
    read-only git; run on a thread pool, where each step is a subprocess that
    releases the GIL while it waits. The returned list is rebuilt in *cheap*
    declaration order so ``emit_summary``, the manifest, and the drift gate are
    byte-for-byte unaffected by the concurrency.
    """
    serial = [s for s in cheap if s.name in _SERIAL_CHEAP]
    parallel = [s for s in cheap if s.name not in _SERIAL_CHEAP]

    results: dict[str, StepResult] = {}
    for step in serial:
        results[step.name] = run_step(step, cwd, environ)

    if parallel:
        workers = _cheap_workers(len(parallel), environ)
        if workers == 1:
            for step in parallel:
                results[step.name] = run_step(step, cwd, environ)
        else:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = {
                    pool.submit(run_step, step, cwd, environ): step.name
                    for step in parallel
                }
                for future in as_completed(futures):
                    results[futures[future]] = future.result()

    return [results[step.name] for step in cheap]


def run_all(
    steps: Sequence[Step],
    cwd: Path,
    environ: dict[str, str],
) -> list[StepResult]:
    """Run *steps* with fail-fast cheap-tier gating and a heavy-tier skip cache.

    Cheap steps run first, in declaration order, and all of them run so a single
    invocation reports every cheap failure at once. Heavy steps (the ~5-min
    pytest suite) then run only when **every** cheap step passed; a sub-second
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

    cheap_results = _run_cheap(cheap, cwd, environ)
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


def resolve_skips(cli_skip: Sequence[str] | None, environ: dict[str, str]) -> set[str]:
    """Return the set of step names to skip, from ``--skip`` and the env.

    Combines repeated ``--skip NAME`` CLI values with the comma-separated
    ``PREFLIGHT_SKIP_STEPS`` environment variable. This is the narrowed
    replacement for the all-or-nothing ``PREFLIGHT_SKIP`` bypass (issue #2133,
    PR #2120 retro #2121): ``.githooks/pre-push`` translates a routine
    ``PREFLIGHT_SKIP=1`` into ``PREFLIGHT_SKIP_STEPS=prek`` so the prek step (the
    one binary that is genuinely unprovisionable in some remote sessions) can be
    dropped while every cheap deterministic gate and ``preflight_coverage`` still
    run.
    """
    names: set[str] = set(cli_skip or ())
    env = environ.get("PREFLIGHT_SKIP_STEPS", "")
    names |= {part.strip() for part in env.split(",") if part.strip()}
    return names


def partition_skips(
    steps: Sequence[Step], skip: set[str]
) -> tuple[list[Step], list[StepResult], list[str]]:
    """Split *steps* into (to-run, skip-results, unknown-skip-names).

    A skip name that matches no step is returned as *unknown* (it skips nothing,
    the safe direction: the gate still runs) so a typo cannot silently drop a
    different gate. Matched steps become ``skip`` results so the summary still
    lists them, making the bypass observable rather than invisible.
    """
    known = {step.name for step in steps}
    unknown = sorted(skip - known)
    to_run = [step for step in steps if step.name not in skip]
    skipped = [
        StepResult(name=step.name, status="skip", detail="skipped via PREFLIGHT_SKIP_STEPS")
        for step in steps
        if step.name in skip
    ]
    return to_run, skipped, unknown


def list_manifest() -> list[dict[str, object]]:
    """Return :data:`STEPS` as a JSON-serializable manifest.

    Consumed by tests and tooling that verify the declared step set
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
    parser.add_argument(
        "--skip",
        action="append",
        metavar="NAME",
        help="Skip a named step (repeatable). Also reads PREFLIGHT_SKIP_STEPS "
        "(comma-separated). The narrowed replacement for the all-or-nothing "
        "PREFLIGHT_SKIP bypass; cheap gates and coverage still run.",
    )
    args = parser.parse_args(argv)

    if args.list:
        json.dump(list_manifest(), sys.stdout, indent=2, sort_keys=True)
        sys.stdout.write("\n")
        return 0

    environ = dict(os.environ)
    skip = resolve_skips(args.skip, environ)
    to_run, skipped, unknown = partition_skips(STEPS, skip)
    for name in unknown:
        print(
            f"::warning::--skip/PREFLIGHT_SKIP_STEPS names unknown step '{name}'; "
            "nothing skipped for it (the gate still runs).",
            file=sys.stderr,
        )
    results = run_all(to_run, REPO_ROOT, environ) + skipped
    emit_summary(results, sys.stdout)
    emit_annotations(results, sys.stderr)
    fails = sum(1 for r in results if r.status == "fail")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
