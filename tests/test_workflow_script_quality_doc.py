"""Pin the M10 install-standard wording in the workflow script quality doc.

Issue #195 promoted the dependency installation rule from the optional
O7 placeholder to must-have M10. This test detects regressions that
silently revert the doc to the placeholder form, drop the canonical
``uv sync --locked`` phrase, or stop referencing the deterministic gate
script. Failures here mean the standard's contract has drifted; fix the
doc rather than relaxing the assertions.

Tested doc: ``docs/standards/workflow-script-quality.md``. Refs #195.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
STANDARD_PATH = REPO_ROOT / "docs" / "standards" / "workflow-script-quality.md"


@pytest.fixture(scope="module")
def standard_text() -> str:
    return STANDARD_PATH.read_text(encoding="utf-8")


class TestM10InstallStandard:
    def test_m10_heading_present(self, standard_text: str) -> None:
        assert "### M10." in standard_text, (
            "M10 must-have heading is missing; #195 promoted the rule "
            "from O7 to must-have."
        )

    def test_canonical_install_primitive_documented(
        self, standard_text: str
    ) -> None:
        assert "uv sync --locked" in standard_text, (
            "canonical install primitive 'uv sync --locked' must appear "
            "in the standard."
        )

    def test_deterministic_gate_referenced(self, standard_text: str) -> None:
        assert "scripts/scan_workflow_pip.py" in standard_text, (
            "M10 must reference the deterministic gate script."
        )

    def test_rationale_table_lists_m10(self, standard_text: str) -> None:
        assert "| M10 install path |" in standard_text, (
            "Rationale (CLAUDE.md mapping) table must include the M10 row."
        )

    def test_o7_placeholder_not_reinstated(self, standard_text: str) -> None:
        # O7 was retired; a future edit must not silently bring it back
        # as an optional enhancement and drop the must-have contract.
        assert "### O7." not in standard_text, (
            "O7 placeholder must not be reinstated; the rule lives at M10."
        )
