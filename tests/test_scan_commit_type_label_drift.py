"""Tests for ``scripts/scan_commit_type_label_drift.py``."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import scan_commit_type_label_drift as gate

pytestmark = pytest.mark.shard_policy


def _label_policy(labels: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a minimal label-policy dict from raw label entries."""
    return {"labels": labels}


def _title_policy(types: list[str]) -> dict[str, Any]:
    """Build a minimal title-policy dict with the given commit types."""
    return {"title_policy": {"types": types}}


def test_commit_types_extracts_string_set() -> None:
    title = _title_policy(["feat", "fix"])
    assert gate.commit_types(title) == {"feat", "fix"}
