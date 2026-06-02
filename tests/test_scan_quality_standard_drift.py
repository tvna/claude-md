"""Tests for ``scripts/scan_quality_standard_drift.py``.

The gate keeps ``docs/standards/workflow-script-quality.md`` and its
enforcement registry in sync: every must-have has a registry entry and
every ``enforced``/``partial`` row resolves its backing. Refs #1089.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import scan_quality_standard_drift as sqsd

pytestmark = pytest.mark.shard_default


# ---------------------------------------------------------------------------
# parse_must_haves
# ---------------------------------------------------------------------------


class TestParseMustHaves:
    def test_extracts_m_headings_only(self) -> None:
        text = textwrap.dedent(
            """\
            ## Must-have checks
            ### M1. Module shape
            ### M2. Unit tests
            ### M10. Deps
            ## Optional enhancements
            ### O1. Property tests
            ### G1. Footprint
            """
        )
        assert sqsd.parse_must_haves(text) == {"M1", "M2", "M10"}


# ---------------------------------------------------------------------------
# resolve_backing
# ---------------------------------------------------------------------------


class TestResolveBacking:
    def test_script_resolves_when_present(self, tmp_path: Path) -> None:
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "foo.py").write_text("x = 1\n", encoding="utf-8")
        assert sqsd.resolve_backing("script:foo", tmp_path, "") is None

    def test_script_missing_is_defect(self, tmp_path: Path) -> None:
        (tmp_path / "scripts").mkdir()
        assert "no scripts/foo.py" in (sqsd.resolve_backing("script:foo", tmp_path, "") or "")

    def test_test_resolves_when_present(self, tmp_path: Path) -> None:
        (tmp_path / "tests").mkdir()
        (tmp_path / "tests" / "test_foo.py").write_text("x = 1\n", encoding="utf-8")
        assert sqsd.resolve_backing("test:test_foo", tmp_path, "") is None

    def test_tool_resolves_when_in_pyproject(self, tmp_path: Path) -> None:
        assert sqsd.resolve_backing("tool:ruff", tmp_path, "[tool.ruff]\n") is None

    def test_tool_unknown_is_defect(self, tmp_path: Path) -> None:
        assert "unknown tool" in (sqsd.resolve_backing("tool:black", tmp_path, "black") or "")

    def test_tool_known_but_absent_from_pyproject_is_defect(self, tmp_path: Path) -> None:
        assert "not referenced in pyproject" in (sqsd.resolve_backing("tool:mypy", tmp_path, "") or "")

    def test_unknown_kind_is_defect(self, tmp_path: Path) -> None:
        assert "unknown kind" in (sqsd.resolve_backing("workflow:x", tmp_path, "") or "")

    def test_missing_target_is_defect(self, tmp_path: Path) -> None:
        assert "missing a ':<name>'" in (sqsd.resolve_backing("script:", tmp_path, "") or "")


# ---------------------------------------------------------------------------
# find_drift
# ---------------------------------------------------------------------------


def _registry(**entries: object) -> dict[str, object]:
    return dict(entries)


class TestFindDrift:
    def test_clean_registry_has_no_drift(self, tmp_path: Path) -> None:
        (tmp_path / "scripts").mkdir()
        (tmp_path / "scripts" / "g.py").write_text("x = 1\n", encoding="utf-8")
        registry = _registry(
            M1={"status": "doc-only", "backing": []},
            M2={"status": "enforced", "backing": ["script:g"]},
        )
        assert sqsd.find_drift({"M1", "M2"}, registry, tmp_path, "") == []

    def test_must_have_without_registry_entry(self, tmp_path: Path) -> None:
        defects = sqsd.find_drift({"M1"}, {}, tmp_path, "")
        assert any("has no registry entry" in d for d in defects)

    def test_registry_entry_without_must_have(self, tmp_path: Path) -> None:
        registry = _registry(M9={"status": "doc-only", "backing": []})
        defects = sqsd.find_drift(set(), registry, tmp_path, "")
        assert any("not a must-have heading" in d for d in defects)

    def test_doc_only_with_backing_is_defect(self, tmp_path: Path) -> None:
        registry = _registry(M1={"status": "doc-only", "backing": ["tool:ruff"]})
        defects = sqsd.find_drift({"M1"}, registry, tmp_path, "ruff")
        assert any("doc-only" in d and "must be empty" in d for d in defects)

    def test_enforced_without_backing_is_defect(self, tmp_path: Path) -> None:
        registry = _registry(M1={"status": "enforced", "backing": []})
        defects = sqsd.find_drift({"M1"}, registry, tmp_path, "")
        assert any("lists no backing" in d for d in defects)

    def test_enforced_with_unresolved_backing_is_defect(self, tmp_path: Path) -> None:
        (tmp_path / "scripts").mkdir()
        registry = _registry(M1={"status": "enforced", "backing": ["script:absent"]})
        defects = sqsd.find_drift({"M1"}, registry, tmp_path, "")
        assert any("no scripts/absent.py" in d for d in defects)

    def test_invalid_status_is_defect(self, tmp_path: Path) -> None:
        registry = _registry(M1={"status": "maybe", "backing": []})
        defects = sqsd.find_drift({"M1"}, registry, tmp_path, "")
        assert any("invalid status" in d for d in defects)

    def test_non_table_entry_is_defect(self, tmp_path: Path) -> None:
        registry = _registry(M1="enforced")
        defects = sqsd.find_drift({"M1"}, registry, tmp_path, "")
        assert any("not a table" in d for d in defects)


# ---------------------------------------------------------------------------
# Live tree: the shipped standard + registry must agree.
# ---------------------------------------------------------------------------


class TestLiveTree:
    def test_repository_standard_and_registry_agree(self) -> None:
        assert sqsd.main(["verify"]) == 0
