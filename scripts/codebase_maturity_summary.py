#!/usr/bin/env python3
"""Render a deterministic codebase scale + maturity summary as Markdown.

Issue #1955 asks for a post-merge view of how the codebase is growing and
maturing. This script measures a small, deterministic set of scale and
maturity signals and renders them as a Markdown report on stdout. The
``maturity-summary`` job in ``.github/workflows/post-merge.yml`` appends that
report to ``$GITHUB_STEP_SUMMARY`` on every merge to ``main``, so the numbers
are visible per merge without writing anything to the repository.

Scale signals (raw counts; bigger is just bigger, not better):
- ``scripts/*.py`` module count and their total physical line count.
- ``tests/test_*.py`` module count.
- ``.github/workflows/*.yml`` workflow count.
- ``docs/**/*.md`` document count.

Maturity signals (proxies for review/test/automation discipline):
- test-to-script ratio (test modules / script modules).
- generated AST-doc coverage (``docs/generated/scripts/ast/*.md`` over the
  public ``scripts/*.py`` modules the post-merge automation documents).
- deterministic-gate script count (``gate_`` / ``preflight_`` / ``scan_`` /
  ``verify_`` prefixed modules).
- maintainability budget health: active-over-budget (non-deferred
  violations), deferred-over-budget (acknowledged debt), and warn-band module
  counts, reused from ``scan_maintainability_metrics.find_module_sizes`` so
  this report and the size gate cannot drift apart. The two over-budget rows
  are reported separately so an "over budget (active) = 0" line is not read as
  "no module exceeds the budget" when deferred debt exists.

The report is a pure function of repository content: no timestamps, hostnames,
or environment values, so the same tree always renders the same Markdown.

Contract:
- Inputs: the ``summary`` subcommand; optional ``--repo-root`` (default ``.``)
  for test injection.
- Outputs: a Markdown report on stdout; exit 0 on success.
- Failure policy: fails loud (exit 1) per CLAUDE.md section 4 when the repo
  root does not exist.

Tested by ``tests/test_codebase_maturity_summary.py``. Refs #1955.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from scan_maintainability_metrics import find_module_sizes

# Module-name prefixes that mark a deterministic harness gate. Kept in sync
# with the naming convention used across scripts/ (gate_/preflight_/scan_/
# verify_); a maturity signal, not an enforced allowlist.
GATE_PREFIXES = ("gate_", "preflight_", "scan_", "verify_")


@dataclass(frozen=True)
class MaturityReport:
    """Deterministic scale + maturity measurements for one repository tree."""

    script_modules: int
    script_total_lines: int
    test_modules: int
    workflow_count: int
    doc_count: int
    ast_doc_count: int
    gate_script_modules: int
    active_over_budget_modules: int
    warn_band_modules: int
    deferred_over_budget_modules: int

    @property
    def test_to_script_ratio(self) -> float:
        if self.script_modules == 0:
            return 0.0
        return self.test_modules / self.script_modules

    @property
    def ast_doc_coverage(self) -> float:
        """Fraction of ``scripts/*.py`` modules with a generated AST doc.

        Denominator is every script module because
        ``script_ast_graph.iter_script_paths`` documents all ``scripts/*.py``
        files (private ``_`` helpers included). A freshly added script has no
        AST doc until the post-merge ``decision-tree`` job regenerates them,
        so the ratio briefly dips below 1.0 between merge and that follow-up.
        """
        if self.script_modules == 0:
            return 0.0
        return self.ast_doc_count / self.script_modules


def _count_lines(path: Path) -> int:
    return len(path.read_text(encoding="utf-8", errors="ignore").splitlines())


def _iter_script_modules(repo_root: Path) -> list[Path]:
    scripts_dir = repo_root / "scripts"
    if not scripts_dir.exists():
        return []
    return [p for p in sorted(scripts_dir.rglob("*.py")) if p.is_file()]


def _glob_files(base: Path, pattern: str) -> list[Path]:
    if not base.exists():
        return []
    return [p for p in sorted(base.glob(pattern)) if p.is_file()]


def measure(repo_root: Path) -> MaturityReport:
    """Measure every scale and maturity signal for *repo_root*."""
    script_modules = _iter_script_modules(repo_root)
    public_scripts = [
        p
        for p in _glob_files(repo_root / "scripts", "*.py")
        if not p.name.startswith("_")
    ]
    gate_scripts = [
        p for p in public_scripts if p.name.startswith(GATE_PREFIXES)
    ]

    docs_dir = repo_root / "docs"
    doc_count = (
        len([p for p in sorted(docs_dir.rglob("*.md")) if p.is_file()])
        if docs_dir.exists()
        else 0
    )

    # Partition the modules above the line budget into active violations
    # (not deferred) and deferred debt so the two over-budget rows sum to the
    # total over-budget count; the warn band is a disjoint within-budget set.
    sizes = find_module_sizes(repo_root)
    active_over_budget = sum(1 for m in sizes if m.is_violation)
    warn_band = sum(1 for m in sizes if m.is_in_warn_band)
    deferred_over_budget = sum(
        1 for m in sizes if m.is_over_budget and m.deferred_reason is not None
    )

    return MaturityReport(
        script_modules=len(script_modules),
        script_total_lines=sum(_count_lines(p) for p in script_modules),
        test_modules=len(_glob_files(repo_root / "tests", "test_*.py")),
        workflow_count=len(
            _glob_files(repo_root / ".github" / "workflows", "*.yml")
        ),
        doc_count=doc_count,
        ast_doc_count=len(
            _glob_files(
                repo_root / "docs" / "generated" / "scripts" / "ast", "*.md"
            )
        ),
        gate_script_modules=len(gate_scripts),
        active_over_budget_modules=active_over_budget,
        warn_band_modules=warn_band,
        deferred_over_budget_modules=deferred_over_budget,
    )


def render_markdown(report: MaturityReport) -> str:
    """Render *report* as a deterministic Markdown document."""
    scale_rows = [
        ("Script modules (`scripts/*.py`)", f"{report.script_modules}"),
        ("Total script lines", f"{report.script_total_lines}"),
        ("Test modules (`tests/test_*.py`)", f"{report.test_modules}"),
        ("Workflows (`.github/workflows/*.yml`)", f"{report.workflow_count}"),
        ("Documents (`docs/**/*.md`)", f"{report.doc_count}"),
    ]
    maturity_rows = [
        ("Test-to-script ratio", f"{report.test_to_script_ratio:.2f}"),
        (
            "Generated AST-doc coverage",
            f"{report.ast_doc_coverage:.2f} "
            f"({report.ast_doc_count}/{report.script_modules})",
        ),
        ("Deterministic-gate scripts", f"{report.gate_script_modules}"),
        (
            "Maintainability over budget (active)",
            f"{report.active_over_budget_modules}",
        ),
        (
            "Maintainability over budget (deferred)",
            f"{report.deferred_over_budget_modules}",
        ),
        ("Maintainability warn band", f"{report.warn_band_modules}"),
    ]

    lines = ["# Codebase maturity and scale", ""]
    lines.append("## Scale")
    lines.append("")
    lines.extend(_render_table(scale_rows))
    lines.append("")
    lines.append("## Maturity")
    lines.append("")
    lines.extend(_render_table(maturity_rows))
    lines.append("")
    return "\n".join(lines)


def _render_table(rows: list[tuple[str, str]]) -> list[str]:
    out = ["| Metric | Value |", "| --- | --- |"]
    out.extend(f"| {name} | {value} |" for name, value in rows)
    return out


def _cmd_summary(args: argparse.Namespace) -> int:
    repo_root = Path(args.repo_root).resolve()
    if not repo_root.exists():
        print(
            f"::error::repo root {repo_root} does not exist", file=sys.stderr
        )
        return 1
    report = measure(repo_root)
    print(render_markdown(report))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_summary = sub.add_parser(
        "summary",
        help="Render the codebase scale + maturity report as Markdown.",
    )
    p_summary.add_argument("--repo-root", default=".")
    p_summary.set_defaults(func=_cmd_summary)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
