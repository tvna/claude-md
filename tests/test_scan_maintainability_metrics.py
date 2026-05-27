"""Tests for ``scripts/scan_maintainability_metrics.py``.

The gate is the module-size pilot for issue #200. It fails new
oversized modules while allowing documented baseline debt to report as
deferred.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_maintainability_metrics

REPO_ROOT = Path(__file__).resolve().parents[1]
STANDARD_PATH = REPO_ROOT / "docs" / "standards" / "maintainability-metrics.md"


def _make_script(repo: Path, rel: str, line_count: int) -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join("print('x')" for _ in range(line_count)), encoding="utf-8")
    return path


class TestModuleSizePilot:
    def test_measure_module_uses_repo_relative_path(self, tmp_path: Path) -> None:
        path = _make_script(tmp_path, "scripts/small.py", 3)

        metric = scan_maintainability_metrics.measure_module(path, tmp_path)

        assert metric.path == Path("scripts/small.py")
        assert metric.line_count == 3
        assert metric.max_lines == scan_maintainability_metrics.MAX_MODULE_LINES
        assert not metric.is_violation

    def test_find_violations_flags_non_deferred_oversized_module(
        self, tmp_path: Path
    ) -> None:
        _make_script(
            tmp_path,
            "scripts/large.py",
            scan_maintainability_metrics.MAX_MODULE_LINES + 1,
        )

        violations = scan_maintainability_metrics.find_violations(tmp_path)

        assert [violation.path for violation in violations] == [
            Path("scripts/large.py")
        ]

    def test_deferred_baseline_debt_does_not_fail_gate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        rel = Path("scripts/legacy.py")
        _make_script(
            tmp_path,
            rel.as_posix(),
            scan_maintainability_metrics.MAX_MODULE_LINES + 1,
        )
        monkeypatch.setattr(
            scan_maintainability_metrics,
            "DEFERRED_OVERSIZE_MODULES",
            {rel: "baseline debt"},
        )

        metrics = scan_maintainability_metrics.find_module_sizes(tmp_path)
        violations = scan_maintainability_metrics.find_violations(tmp_path)

        assert metrics[0].deferred_reason == "baseline debt"
        assert violations == []


class TestMain:
    def test_clean_tree_exits_zero(self, tmp_path: Path) -> None:
        _make_script(tmp_path, "scripts/small.py", 2)

        assert (
            scan_maintainability_metrics.main(
                ["verify", "--repo-root", str(tmp_path)]
            )
            == 0
        )

    def test_violation_exits_one(self, tmp_path: Path) -> None:
        _make_script(
            tmp_path,
            "scripts/large.py",
            scan_maintainability_metrics.MAX_MODULE_LINES + 1,
        )

        assert (
            scan_maintainability_metrics.main(
                ["verify", "--repo-root", str(tmp_path)]
            )
            == 1
        )


@pytest.fixture(scope="module")
def standard_text() -> str:
    return STANDARD_PATH.read_text(encoding="utf-8")


class TestMaintainabilityMetricStandard:
    def test_metric_inventory_is_documented(self, standard_text: str) -> None:
        for phrase in (
            "module size",
            "cyclomatic complexity",
            "duplication",
            "import graph shape",
            "side-effect isolation",
        ):
            assert phrase in standard_text

    def test_pilot_and_threshold_are_documented(self, standard_text: str) -> None:
        assert "800 physical lines" in standard_text
        assert "scripts/scan_maintainability_metrics.py" in standard_text
        assert "scripts/auto_retro.py" in standard_text

    def test_ci_fail_or_report_policy_is_documented(self, standard_text: str) -> None:
        assert "Fails CI" in standard_text
        assert "Reports only" in standard_text
