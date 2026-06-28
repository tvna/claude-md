"""Tests for the static family catalog in ``scripts/_security_drift_families.py``."""

from __future__ import annotations

import _security_drift_families as fam
import pytest

pytestmark = pytest.mark.shard_ci_ops


def test_issue_labels_are_the_meta_fix_lane() -> None:
    assert fam.ISSUE_LABELS == ("layer:meta", "type:fix")


def test_target_families_are_unique_and_include_workflow_permissions() -> None:
    assert len(fam.TARGET_FAMILIES) == len(set(fam.TARGET_FAMILIES))
    assert "workflow-permissions" in fam.TARGET_FAMILIES
    # `rulesets` files its own issues; it must not double-file via this catalog.
    assert "rulesets" not in fam.TARGET_FAMILIES


def test_every_target_family_has_a_complete_ascii_spec() -> None:
    required = {"scope", "detector", "evidence", "remediation"}
    for family in fam.TARGET_FAMILIES:
        spec = fam.FAMILY_ISSUE_SPEC[family]
        assert required <= set(spec)
        for value in spec.values():
            value.encode("ascii")  # raises if any non-ASCII leaked in
