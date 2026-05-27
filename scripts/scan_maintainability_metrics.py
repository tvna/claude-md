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
surfaces the exact file.

Tested by ``tests/test_scan_maintainability_metrics.py``. Refs #200.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

SCRIPT_SUBDIR = "scripts"
MAX_MODULE_LINES = 800

# Baseline debt may pass, but the gate prevents this pattern from
# spreading while the oversized module is split in a later scoped PR.
DEFERRED_OVERSIZE_MODULES: dict[Path, str] = {
    Path("scripts/auto_retro.py"): (
        "legacy retrospective aggregator; split into parser, GitHub IO, "
        "and renderer modules in a follow-up PR before tightening the budget"
    ),
}


@dataclass(frozen=True)
class ModuleSize:
    path: Path
    line_count: int
    max_lines: int
    deferred_reason: str | None = None

    @property
    def is_over_budget(self) -> bool:
        return self.line_count > self.max_lines

    @property
    def is_violation(self) -> bool:
        return self.is_over_budget and self.deferred_reason is None


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
        f"({len(deferred)} deferred oversized module(s))."
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
