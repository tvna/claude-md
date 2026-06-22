"""Tests for the repair-category registry in ``scripts/_auto_retro_triage.py``.

Verifies that ``KNOWN_REPAIR_CATEGORIES`` exposes the expected taxonomy
labels used by the auto-retro operator-fill workflow, including the
``pr-body-content-quality`` category added in #1828.
"""

from __future__ import annotations

import auto_retro as ar
import pytest

pytestmark = pytest.mark.shard_ci_ops


class TestKnownRepairCategories:
    def test_pr_body_content_quality_is_recognized(self) -> None:
        assert "pr-body-content-quality" in ar.KNOWN_REPAIR_CATEGORIES

    def test_section_3_taxonomy_labels_present(self) -> None:
        assert "missing-deterministic-gate" in ar.KNOWN_REPAIR_CATEGORIES
        assert "unclear-agent-instruction" in ar.KNOWN_REPAIR_CATEGORIES
        assert "external-human-decision" in ar.KNOWN_REPAIR_CATEGORIES

    def test_is_frozenset(self) -> None:
        assert isinstance(ar.KNOWN_REPAIR_CATEGORIES, frozenset)

    def test_has_four_categories(self) -> None:
        assert len(ar.KNOWN_REPAIR_CATEGORIES) == 4
