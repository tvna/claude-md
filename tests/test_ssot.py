"""Tests for ``scripts/_ssot.py``.

Exercises the reader against the real ``.gitapex/ssot.json`` (validated
separately by ``tests/test_scan_ssot_schema.py``), so these tests catch a
reader/registry contract break without duplicating shape validation.

Refs #2266, #2246, #1041.
"""

from __future__ import annotations

import _ssot
import pytest

pytestmark = pytest.mark.shard_preflight


class TestConsumerLabels:
    def test_returns_registered_labels_for_branch_cleanup(self) -> None:
        assert _ssot.consumer_labels("scripts/branch_cleanup.py") == (
            "layer:meta",
            "type:docs",
        )

    def test_raises_key_error_for_unknown_path(self) -> None:
        with pytest.raises(KeyError, match="no label_consumers entry"):
            _ssot.consumer_labels("scripts/does_not_exist.py")


class TestRoutingRules:
    def test_returns_ordered_rules_ending_in_default(self) -> None:
        rules = _ssot.routing_rules()
        assert len(rules) > 0
        assert rules[-1].get("default") is True
        assert all(rule.get("default") is not True for rule in rules[:-1])
