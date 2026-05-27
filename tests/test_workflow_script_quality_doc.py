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

pytestmark = pytest.mark.shard_ci_ops
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


class TestCoverageGraduationPolicy:
    """Pin the Coverage graduation policy added by #198.

    The policy is the contract that lets non-`scripts/` Python packages
    enter the repository coverage gate without weakening the
    script-specific floor from #188. Regressing the doc text silently
    would void that contract; this test detects such drift.
    """

    def test_section_heading_present(self, standard_text: str) -> None:
        assert "## Coverage graduation policy" in standard_text, (
            "Coverage graduation policy section is missing; #198 carries "
            "the rule that lets non-scripts/ packages join the gate."
        )

    def test_g1_through_g4_subsections_present(
        self, standard_text: str
    ) -> None:
        for label in ("### G1.", "### G2.", "### G3.", "### G4."):
            assert label in standard_text, (
                f"Graduation subsection {label} is missing; the policy "
                "lists current footprint, procedure, exclusions, and the "
                "non-weakening invariant."
            )

    def test_script_floor_invariant_documented(
        self, standard_text: str
    ) -> None:
        # G4 must spell out that the script floor cannot drop. Searching
        # for a verbatim phrase keeps reviewers from silently softening
        # the invariant to "should not" or similar.
        assert "cannot weaken" in standard_text, (
            "G4 must state the script gate cannot weaken; #198 invariant "
            "depends on the explicit wording."
        )

    def test_pyproject_anchor_referenced(self, standard_text: str) -> None:
        # The policy points readers at the configuration of record so
        # the doc stays connected to the executable gate.
        assert "[tool.coverage.report].fail_under" in standard_text, (
            "Graduation policy must name the authoritative threshold "
            "key so the doc and config stay coupled."
        )

    def test_issue_198_referenced(self, standard_text: str) -> None:
        assert "#198" in standard_text, (
            "Graduation policy must cite #198 so its provenance is "
            "discoverable from the standard alone."
        )

    def test_rationale_table_lists_graduation_row(
        self, standard_text: str
    ) -> None:
        assert "| G1-G4 coverage graduation |" in standard_text, (
            "Rationale (CLAUDE.md mapping) table must include the "
            "graduation row so the policy maps back to CLAUDE.md."
        )
