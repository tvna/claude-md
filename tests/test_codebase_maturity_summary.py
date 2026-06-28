"""Tests for ``scripts/codebase_maturity_summary.py``.

The script renders a deterministic scale + maturity Markdown report for the
post-merge job summary (#1955). These tests build synthetic repository trees
so the counts are known exactly, and exercise the ``summary`` CLI contract.
"""

from __future__ import annotations

from pathlib import Path

import codebase_maturity_summary
import pytest
import scan_maintainability_metrics

pytestmark = pytest.mark.shard_ci_ops


def _write(repo: Path, rel: str, *, lines: int = 1) -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join("x" for _ in range(lines)), encoding="utf-8")
    return path


def _seed_minimal_repo(repo: Path) -> None:
    """Two public scripts, one private helper, plus tests/workflows/docs."""
    _write(repo, "scripts/alpha.py", lines=10)
    _write(repo, "scripts/scan_beta.py", lines=20)
    _write(repo, "scripts/_helper.py", lines=5)
    _write(repo, "tests/test_alpha.py", lines=3)
    _write(repo, "tests/test_scan_beta.py", lines=3)
    _write(repo, ".github/workflows/ci.yml", lines=4)
    _write(repo, "docs/one.md", lines=2)
    _write(repo, "docs/nested/two.md", lines=2)


class TestMeasure:
    def test_counts_scale_signals(self, tmp_path: Path) -> None:
        _seed_minimal_repo(tmp_path)

        report = codebase_maturity_summary.measure(tmp_path)

        assert report.script_modules == 3
        assert report.script_total_lines == 10 + 20 + 5
        assert report.test_modules == 2
        assert report.workflow_count == 1
        assert report.doc_count == 2

    def test_test_to_script_ratio(self, tmp_path: Path) -> None:
        _seed_minimal_repo(tmp_path)

        report = codebase_maturity_summary.measure(tmp_path)

        assert report.test_to_script_ratio == pytest.approx(2 / 3)

    def test_ast_doc_coverage_uses_all_script_modules(
        self, tmp_path: Path
    ) -> None:
        _seed_minimal_repo(tmp_path)
        # One AST doc for two of the three script modules.
        _write(repo=tmp_path, rel="docs/generated/scripts/ast/alpha.md")
        _write(repo=tmp_path, rel="docs/generated/scripts/ast/scan_beta.md")

        report = codebase_maturity_summary.measure(tmp_path)

        assert report.ast_doc_count == 2
        assert report.ast_doc_coverage == pytest.approx(2 / 3)

    def test_gate_scripts_count_prefix_matches_only(
        self, tmp_path: Path
    ) -> None:
        _seed_minimal_repo(tmp_path)

        report = codebase_maturity_summary.measure(tmp_path)

        # Only scan_beta.py carries a gate prefix; _helper.py is private and
        # alpha.py has no gate prefix.
        assert report.gate_script_modules == 1

    def test_maintainability_signals_reuse_size_gate(
        self, tmp_path: Path
    ) -> None:
        _seed_minimal_repo(tmp_path)
        over = scan_maintainability_metrics.MAX_MODULE_LINES + 1
        warn = scan_maintainability_metrics.WARN_MODULE_LINES
        _write(repo=tmp_path, rel="scripts/huge.py", lines=over)
        _write(repo=tmp_path, rel="scripts/warned.py", lines=warn)

        report = codebase_maturity_summary.measure(tmp_path)

        assert report.active_over_budget_modules == 1
        assert report.warn_band_modules == 1
        assert report.deferred_over_budget_modules == 0

    def test_deferred_oversized_module_counts_as_deferred_not_active(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _seed_minimal_repo(tmp_path)
        over = scan_maintainability_metrics.MAX_MODULE_LINES + 1
        _write(repo=tmp_path, rel="scripts/legacy.py", lines=over)
        monkeypatch.setattr(
            scan_maintainability_metrics,
            "DEFERRED_OVERSIZE_MODULES",
            {Path("scripts/legacy.py"): "documented legacy debt"},
        )

        report = codebase_maturity_summary.measure(tmp_path)

        # The deferred over-budget module must not vanish: it belongs to the
        # deferred row, never the active-violations row (#1961 review).
        assert report.active_over_budget_modules == 0
        assert report.deferred_over_budget_modules == 1

    def test_proportionality_ratios(self, tmp_path: Path) -> None:
        _seed_minimal_repo(tmp_path)

        report = codebase_maturity_summary.measure(tmp_path)

        # 3 script modules totalling 35 lines (10 + 20 + 5).
        assert report.average_module_lines == pytest.approx(35 / 3)
        # Only scan_beta.py carries a gate prefix -> 1 of 3 modules.
        assert report.gate_script_ratio == pytest.approx(1 / 3)
        # No module exceeds the budget in the minimal repo.
        assert report.active_over_budget_ratio == 0.0

    def test_active_over_budget_ratio_counts_violations(
        self, tmp_path: Path
    ) -> None:
        _seed_minimal_repo(tmp_path)
        over = scan_maintainability_metrics.MAX_MODULE_LINES + 1
        _write(repo=tmp_path, rel="scripts/huge.py", lines=over)

        report = codebase_maturity_summary.measure(tmp_path)

        # 1 active violation out of 4 script modules.
        assert report.active_over_budget_modules == 1
        assert report.active_over_budget_ratio == pytest.approx(1 / 4)

    def test_empty_repo_ratios_do_not_divide_by_zero(
        self, tmp_path: Path
    ) -> None:
        report = codebase_maturity_summary.measure(tmp_path)

        assert report.test_to_script_ratio == 0.0
        assert report.ast_doc_coverage == 0.0
        assert report.average_module_lines == 0.0
        assert report.gate_script_ratio == 0.0
        assert report.active_over_budget_ratio == 0.0


class TestRender:
    def test_render_is_deterministic(self, tmp_path: Path) -> None:
        _seed_minimal_repo(tmp_path)
        report = codebase_maturity_summary.measure(tmp_path)

        first = codebase_maturity_summary.render_markdown(report)
        second = codebase_maturity_summary.render_markdown(report)

        assert first == second
        assert first.startswith("# Codebase maturity and scale")
        assert "## Scale" in first
        assert "## Maturity" in first
        assert "| Metric | Value |" in first

    def test_render_includes_proportionality_rows(
        self, tmp_path: Path
    ) -> None:
        _seed_minimal_repo(tmp_path)
        report = codebase_maturity_summary.measure(tmp_path)

        out = codebase_maturity_summary.render_markdown(report)

        assert "Average module lines" in out
        assert "Deterministic-gate coverage" in out
        assert "Maintainability over-budget proportion" in out


class TestCli:
    def test_summary_prints_markdown(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _seed_minimal_repo(tmp_path)

        rc = codebase_maturity_summary.main(
            ["summary", "--repo-root", str(tmp_path)]
        )

        assert rc == 0
        out = capsys.readouterr().out
        assert "# Codebase maturity and scale" in out
        assert "Script modules" in out

    def test_missing_repo_root_fails_loud(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        missing = tmp_path / "does-not-exist"

        rc = codebase_maturity_summary.main(
            ["summary", "--repo-root", str(missing)]
        )

        assert rc == 1
        assert "does not exist" in capsys.readouterr().err
