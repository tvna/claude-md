#!/usr/bin/env python3
"""Pilot maintainability metrics for workflow script modules.

Issue #200 asks for a lightweight maintainability metric set and at
least one deterministic pilot. This script implements the first gate:
module size. Large workflow scripts are harder to review, test, and
split at IO boundaries, so new or modified modules must stay under the
documented line budget unless they are listed as explicit legacy debt.

Invoked from ``.github/workflows/verify-agents.yml`` as
``python scripts/scan_maintainability_metrics.py verify``.

Exit 0 when every non-deferred script is within budget; exit 1 on any
violation. Violations emit ``::error`` annotations so GitHub Actions
surfaces the exact file. Passing modules that sit in the warning band
(at or above ``WARN_MODULE_LINES`` but within budget) emit ``::warning``
so a module approaching the limit is visible before it crosses.

Tested by ``tests/test_scan_maintainability_metrics.py``. Refs #200, #1700.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

SCRIPT_SUBDIR = "scripts"
MAX_MODULE_LINES = 800

# Warning band: modules at or above this many lines (but still within the
# hard budget) pass the gate but emit a ``::warning`` so a module that is
# approaching the limit is visible before it crosses or is trimmed to fit.
# Refs #1700: early detection of ceiling clustering (Goodhart's-law signal).
WARN_RATIO = 0.8
WARN_MODULE_LINES = int(MAX_MODULE_LINES * WARN_RATIO)

# Baseline debt may pass, but the gate prevents this pattern from
# spreading while the oversized module is split in a later scoped PR.
DEFERRED_OVERSIZE_MODULES: dict[Path, str] = {
    Path("scripts/auto_retro.py"): (
        "pure parser/triage/renderer layers extracted into _auto_retro_parse.py, "
        "_auto_retro_triage.py, and _auto_retro_render.py (refs #1725); the "
        "GitHub IO fetchers and the run/sentinel/post-merge-rescan orchestration "
        "remain here, so the module stays over budget and deferred"
    ),
    Path("scripts/threat_intel_triage.py"): (
        "legacy multi-source intelligence gate; split OSV, KEV, NVD, EPSS, "
        "and malicious-package adapters before tightening the budget"
    ),
    Path("scripts/body_policy.py"): (
        "placeholder-token and substantive-content gates added in refs #1826 "
        "pushed the module to 849 lines; split verification helpers into a "
        "dedicated _body_policy_shape.py module to restore budget"
    ),
}


@dataclass(frozen=True)
class ModuleSize:
    path: Path
    line_count: int
    max_lines: int
    warn_lines: int = WARN_MODULE_LINES
    deferred_reason: str | None = None

    @property
    def is_over_budget(self) -> bool:
        return self.line_count > self.max_lines

    @property
    def is_violation(self) -> bool:
        return self.is_over_budget and self.deferred_reason is None

    @property
    def is_in_warn_band(self) -> bool:
        """True when a passing module is approaching the hard budget.

        Excludes deferred debt and hard violations, so the warning band
        only flags modules that pass today but sit in
        ``[warn_lines, max_lines]``.
        """
        return (
            self.deferred_reason is None
            and not self.is_over_budget
            and self.line_count >= self.warn_lines
        )


def count_lines(path: Path) -> int:
    """Return the number of physical lines in *path*."""
    return len(path.read_text(encoding="utf-8", errors="ignore").splitlines())


def measure_module(path: Path, repo_root: Path) -> ModuleSize:
    """Return the module-size measurement for *path*."""
    rel = path.relative_to(repo_root)
    return ModuleSize(
        path=rel,
        line_count=count_lines(path),
        max_lines=MAX_MODULE_LINES,
        warn_lines=WARN_MODULE_LINES,
        deferred_reason=DEFERRED_OVERSIZE_MODULES.get(rel),
    )


def find_module_sizes(repo_root: Path) -> list[ModuleSize]:
    """Measure every Python module under ``scripts/``."""
    scripts_dir = repo_root / SCRIPT_SUBDIR
    if not scripts_dir.exists():
        return []
    return [
        measure_module(path, repo_root)
        for path in _iter_python_files(scripts_dir)
    ]


def find_violations(repo_root: Path) -> list[ModuleSize]:
    """Return non-deferred modules that exceed the size budget."""
    return [
        metric
        for metric in find_module_sizes(repo_root)
        if metric.is_violation
    ]


def _iter_python_files(scripts_dir: Path) -> Iterator[Path]:
    for path in sorted(scripts_dir.rglob("*.py")):
        if path.is_file():
            yield path


def _cmd_verify(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    metrics = find_module_sizes(repo_root)
    violations = [metric for metric in metrics if metric.is_violation]
    warned = [metric for metric in metrics if metric.is_in_warn_band]
    deferred = [
        metric
        for metric in metrics
        if metric.is_over_budget and metric.deferred_reason is not None
    ]

    for metric in violations:
        print(
            f"::error file={metric.path}::"
            f"{metric.path} has {metric.line_count} lines; "
            f"limit is {metric.max_lines}. Split the module or document "
            "an explicit deferred-debt exception.",
            file=sys.stderr,
        )
    for metric in warned:
        print(
            f"::warning file={metric.path}::"
            f"{metric.path} has {metric.line_count} lines, in the warning "
            f"band [{metric.warn_lines}, {metric.max_lines}] "
            f"(>= {int(WARN_RATIO * 100)}% of the budget). Consider "
            "splitting it before it reaches the hard limit.",
        )
    for metric in deferred:
        print(
            f"::notice file={metric.path}::"
            f"{metric.path} has {metric.line_count} lines above the "
            f"{metric.max_lines}-line budget; deferred: "
            f"{metric.deferred_reason}.",
        )

    if violations:
        print(
            f"FAIL: {len(violations)} script module size violation(s).",
            file=sys.stderr,
        )
        return 1

    print(
        "OK: script module size budget passed "
        f"({len(warned)} module(s) in the warning band, "
        f"{len(deferred)} deferred oversized module(s))."
    )
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_verify = sub.add_parser(
        "verify",
        help="Require scripts/*.py modules to stay within the size budget.",
    )
    p_verify.add_argument("--repo-root", default=".")
    p_verify.set_defaults(func=_cmd_verify)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
