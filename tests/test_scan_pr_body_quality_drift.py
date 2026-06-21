"""Tests for ``scripts/scan_pr_body_quality_drift.py``.

The gate keeps ``docs/standards/pr-body-quality.enforcement.toml`` internally
consistent: every ``enforced``/``partial`` row resolves its backing, and every
``doc-only`` row has an empty backing list. Refs #1828.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_pr_body_quality_drift as spbqd

pytestmark = pytest.mark.shard_default


# ---------------------------------------------------------------------------
# resolve_backing
# ---------------------------------------------------------------------------


class TestResolveBacking:
    def test_script_resolves_when_present(self, tmp_path: Path) -> None:
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "foo.py").write_text("x = 1\n", encoding="utf-8")
        assert spbqd.resolve_backing("script:foo", tmp_path) is None

    def test_script_missing_is_defect(self, tmp_path: Path) -> None:
        (tmp_path / "scripts").mkdir()
        result = spbqd.resolve_backing("script:absent", tmp_path)
        assert result is not None and "no scripts/absent.py" in result

    def test_test_resolves_when_present(self, tmp_path: Path) -> None:
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_foo.py").write_text("x = 1\n", encoding="utf-8")
        assert spbqd.resolve_backing("test:test_foo", tmp_path) is None

    def test_test_missing_is_defect(self, tmp_path: Path) -> None:
        (tmp_path / "tests").mkdir()
        result = spbqd.resolve_backing("test:test_absent", tmp_path)
        assert result is not None and "no tests/test_absent.py" in result

    def test_unknown_kind_is_defect(self, tmp_path: Path) -> None:
        result = spbqd.resolve_backing("workflow:x", tmp_path)
        assert result is not None and "unknown kind" in result

    def test_missing_target_is_defect(self, tmp_path: Path) -> None:
        result = spbqd.resolve_backing("script:", tmp_path)
        assert result is not None and "missing a ':<name>'" in result


# ---------------------------------------------------------------------------
# find_drift
# ---------------------------------------------------------------------------


def _registry(**entries: object) -> dict[str, object]:
    return dict(entries)


class TestFindDrift:
    def test_clean_doc_only_registry_has_no_drift(self, tmp_path: Path) -> None:
        registry = _registry(
            **{k: {"status": "doc-only", "backing": []} for k in spbqd.KNOWN_DEFECTS}
        )
        assert spbqd.find_drift(registry, tmp_path) == []

    def test_enforced_row_with_existing_script_has_no_drift(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "gate.py").write_text("x = 1\n", encoding="utf-8")
        registry = _registry(
            **{
                k: {"status": "doc-only", "backing": []}
                for k in spbqd.KNOWN_DEFECTS - {"placeholder-residue"}
            },
            **{"placeholder-residue": {"status": "enforced", "backing": ["script:gate"]}},
        )
        assert spbqd.find_drift(registry, tmp_path) == []

    def test_orphan_key_is_defect(self, tmp_path: Path) -> None:
        registry = _registry(**{"unknown-defect": {"status": "doc-only", "backing": []}})
        defects = spbqd.find_drift(registry, tmp_path)
        assert any("not a known defect class" in d for d in defects)

    def test_doc_only_with_backing_is_defect(self, tmp_path: Path) -> None:
        registry = _registry(
            **{"placeholder-residue": {"status": "doc-only", "backing": ["script:x"]}}
        )
        defects = spbqd.find_drift(registry, tmp_path)
        assert any("doc-only" in d and "must have an empty backing list" in d for d in defects)

    def test_enforced_without_backing_is_defect(self, tmp_path: Path) -> None:
        registry = _registry(
            **{"placeholder-residue": {"status": "enforced", "backing": []}}
        )
        defects = spbqd.find_drift(registry, tmp_path)
        assert any("lists no backing" in d for d in defects)

    def test_enforced_with_unresolved_backing_is_defect(self, tmp_path: Path) -> None:
        (tmp_path / "scripts").mkdir()
        registry = _registry(
            **{"placeholder-residue": {"status": "enforced", "backing": ["script:absent"]}}
        )
        defects = spbqd.find_drift(registry, tmp_path)
        assert any("no scripts/absent.py" in d for d in defects)

    def test_invalid_status_is_defect(self, tmp_path: Path) -> None:
        registry = _registry(
            **{"placeholder-residue": {"status": "maybe", "backing": []}}
        )
        defects = spbqd.find_drift(registry, tmp_path)
        assert any("invalid status" in d for d in defects)

    def test_non_table_entry_is_defect(self, tmp_path: Path) -> None:
        registry = _registry(**{"placeholder-residue": "enforced"})
        defects = spbqd.find_drift(registry, tmp_path)
        assert any("not a table" in d for d in defects)


# ---------------------------------------------------------------------------
# Live tree: the shipped registry must be internally consistent.
# ---------------------------------------------------------------------------


class TestLiveTree:
    def test_repository_registry_is_consistent(self) -> None:
        assert spbqd.main(["verify"]) == 0
