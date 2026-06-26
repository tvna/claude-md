"""Tests for ``scripts/scan_module_size_distribution.py``.

The generator persists the ``scripts/*.py`` size distribution as a committed
snapshot (issue #1701). Refs #2013: the snapshot is produced post-merge under
the single-producer model (#1540/#1543/#1546); feature branches no longer
regenerate it, so these tests exercise the ``write``/``verify`` round-trip and
the pure rendering functions on temp dirs rather than the checked-in file.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest
import scan_maintainability_metrics
import scan_module_size_distribution

pytestmark = pytest.mark.shard_ci_ops


def _make_script(repo: Path, rel: str, line_count: int) -> Path:
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join("print('x')" for _ in range(line_count)), encoding="utf-8")
    return path


class TestHistogram:
    def test_bucket_label_covers_edges_and_overflow(self) -> None:
        labels = [
            scan_module_size_distribution.bucket_label(i)
            for i in range(len(scan_module_size_distribution.BUCKET_EDGES) + 1)
        ]
        assert labels == ["1-160", "161-320", "321-480", "481-640", "641-800", "801+"]

    def test_bucket_counts_place_modules_in_first_matching_bucket(
        self, tmp_path: Path
    ) -> None:
        for name, lines in (("a", 1), ("b", 160), ("c", 161), ("d", 800), ("e", 801)):
            _make_script(tmp_path, f"scripts/{name}.py", lines)

        modules = scan_maintainability_metrics.find_module_sizes(tmp_path)
        counts = scan_module_size_distribution.bucket_counts(modules)

        # buckets: [1-160]=a,b  [161-320]=c  [481-640]=0  [641-800]=d  [801+]=e
        assert counts == [2, 1, 0, 0, 1, 1]


class TestSnapshotRender:
    def test_snapshot_is_deterministic_and_valid_toml(self, tmp_path: Path) -> None:
        _make_script(tmp_path, "scripts/small.py", 10)
        _make_script(tmp_path, "scripts/warn.py", scan_maintainability_metrics.WARN_MODULE_LINES)

        modules = scan_maintainability_metrics.find_module_sizes(tmp_path)
        first = scan_module_size_distribution.render_snapshot(modules)
        second = scan_module_size_distribution.render_snapshot(modules)

        assert first == second
        parsed = tomllib.loads(first)
        assert parsed["summary"]["in_warn_band"] == 1
        assert parsed["modules"]["warn_band"] == ["scripts/warn.py"]

    def test_over_budget_modules_are_listed(self, tmp_path: Path) -> None:
        _make_script(
            tmp_path, "scripts/big.py", scan_maintainability_metrics.MAX_MODULE_LINES + 5
        )

        modules = scan_maintainability_metrics.find_module_sizes(tmp_path)
        parsed = tomllib.loads(scan_module_size_distribution.render_snapshot(modules))

        assert parsed["summary"]["over_budget"] == 1
        assert parsed["modules"]["over_budget"] == ["scripts/big.py"]


class TestWriteVerify:
    def test_write_then_verify_passes(self, tmp_path: Path) -> None:
        _make_script(tmp_path, "scripts/small.py", 10)

        assert (
            scan_module_size_distribution.main(["write", "--repo-root", str(tmp_path)])
            == 0
        )
        assert (
            scan_module_size_distribution.main(["verify", "--repo-root", str(tmp_path)])
            == 0
        )

    def test_verify_fails_when_snapshot_missing(self, tmp_path: Path) -> None:
        _make_script(tmp_path, "scripts/small.py", 10)

        assert (
            scan_module_size_distribution.main(["verify", "--repo-root", str(tmp_path)])
            == 1
        )

    def test_verify_fails_when_distribution_drifts(self, tmp_path: Path) -> None:
        _make_script(tmp_path, "scripts/small.py", 10)
        scan_module_size_distribution.main(["write", "--repo-root", str(tmp_path)])

        # A new module shifts the distribution; the committed snapshot is now stale.
        _make_script(tmp_path, "scripts/added.py", 200)

        assert (
            scan_module_size_distribution.main(["verify", "--repo-root", str(tmp_path)])
            == 1
        )
