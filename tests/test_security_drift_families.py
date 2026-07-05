"""Tests for the static family catalog in ``scripts/_security_drift_families.py``."""

from __future__ import annotations

import _security_drift_families as fam
import pytest

pytestmark = pytest.mark.shard_ci_ops


def test_issue_labels_resolve_from_the_ssot_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        fam._ssot,
        "consumer_labels",
        lambda path: ("layer:p3-harness", "area:security-intel", "type:fix"),
    )
    assert fam.issue_labels() == ("layer:p3-harness", "area:security-intel", "type:fix")


def test_issue_labels_wraps_drifted_registry_as_runtime_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise_key_error(path: str) -> tuple[str, ...]:
        raise KeyError(f"no label_consumers entry for path {path!r}")

    monkeypatch.setattr(fam._ssot, "consumer_labels", _raise_key_error)
    with pytest.raises(RuntimeError, match="security-drift-families registry labels"):
        fam.issue_labels()


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
