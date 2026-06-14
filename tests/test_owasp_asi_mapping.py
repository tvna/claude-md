"""Tests for ``scripts/owasp_asi_mapping.py``."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import owasp_asi_mapping as oam

pytestmark = pytest.mark.shard_ci_ops_2

REPO_ROOT = Path(__file__).resolve().parents[1]
REAL_INVENTORY = REPO_ROOT / "docs" / "prd" / "security-control-inventory.md"


def _table(rows: str) -> str:
    """Wrap table rows in a minimal OWASP section with surrounding sections."""
    return (
        "# Inventory\n\n"
        "## 1. Something\n\nprose\n\n"
        f"## OWASP Top 10 for Agentic Applications 2026 (ASI01-ASI10) coverage\n\n"
        "| ASI | Risk | Status | Rationale | Gap |\n"
        "|---|---|---|---|---|\n"
        f"{rows}"
        "\n## Gap summary\n\nmore prose\n"
    )


def _all_rows(status: str = "covered", rationale: str = "evidence here") -> str:
    return "".join(
        f"| `ASI{n:02d}` | Risk {n} | {status} | {rationale} | -- |\n"
        for n in range(1, 11)
    )


class TestExtractSection:
    def test_returns_none_when_absent(self) -> None:
        assert oam.extract_section("# Doc\n\n## Other\n\nprose\n") is None

    def test_stops_at_next_heading(self) -> None:
        section = oam.extract_section(_table(_all_rows()))
        assert section is not None
        assert "ASI01" in section
        assert "Gap summary" not in section


class TestEvaluate:
    def test_complete_mapping_is_clean(self) -> None:
        assert oam.evaluate(_table(_all_rows())) == []

    def test_missing_section_is_violation(self) -> None:
        errors = oam.evaluate("# Doc\n\n## Other\n\nprose\n")
        assert len(errors) == 1
        assert "OWASP section not found" in errors[0]

    def test_missing_item_is_violation(self) -> None:
        rows = "".join(
            f"| `ASI{n:02d}` | Risk | covered | evidence | -- |\n"
            for n in range(1, 10)  # ASI10 absent
        )
        errors = oam.evaluate(_table(rows))
        assert any("ASI10" in message and "no mapping row" in message for message in errors)

    def test_duplicate_item_is_violation(self) -> None:
        rows = _all_rows() + "| `ASI01` | Risk | covered | evidence | -- |\n"
        errors = oam.evaluate(_table(rows))
        assert any("ASI01" in message and "exactly once" in message for message in errors)

    def test_invalid_status_is_violation(self) -> None:
        rows = _all_rows().replace(
            "| `ASI03` | Risk 3 | covered |", "| `ASI03` | Risk 3 | mostly-ok |"
        )
        errors = oam.evaluate(_table(rows))
        assert any("ASI03" in message and "not one of" in message for message in errors)

    def test_empty_rationale_is_violation(self) -> None:
        rows = _all_rows().replace(
            "| `ASI05` | Risk 5 | covered | evidence here |",
            "| `ASI05` | Risk 5 | covered |  |",
        )
        errors = oam.evaluate(_table(rows))
        assert any("ASI05" in message and "rationale cell is empty" in message for message in errors)

    def test_accepts_all_valid_statuses(self) -> None:
        for status in ("covered", "partially covered", "not covered", "not applicable"):
            assert oam.evaluate(_table(_all_rows(status=status))) == []


class TestRealInventory:
    def test_shipped_inventory_passes(self) -> None:
        text = REAL_INVENTORY.read_text(encoding="utf-8")
        assert oam.evaluate(text) == []


class TestMain:
    def test_verify_clean_real_inventory(self) -> None:
        assert oam.main(["verify", "--inventory", str(REAL_INVENTORY)]) == 0

    def test_verify_missing_file_fails(self, tmp_path: Path) -> None:
        missing = tmp_path / "nope.md"
        assert oam.main(["verify", "--inventory", str(missing)]) == 1

    def test_verify_incomplete_fails(self, tmp_path: Path) -> None:
        doc = tmp_path / "inv.md"
        doc.write_text(_table(_all_rows().replace("| `ASI09` | Risk 9 | covered | evidence here | -- |\n", "")), encoding="utf-8")
        assert oam.main(["verify", "--inventory", str(doc)]) == 1
