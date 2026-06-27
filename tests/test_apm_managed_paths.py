"""Drift gate for the single APM-managed-prefix source of truth.

``scripts/_apm_managed_paths.py`` owns ``MANAGED_PREFIXES`` so the gate and the
scanners cannot carry diverging literal copies (CLAUDE.md section 3: ship the
drift gate in the same change that establishes the invariant). This test fails
if any consumer stops referencing the shared constant. Refs #2066, #1892,
#1891.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import _apm_managed_paths as amp
import gate_agents_skills_edit as gase
import scan_repo_double_hyphen as srdh
import scan_repo_em_dash as sred

pytestmark = pytest.mark.shard_default


def test_canonical_value() -> None:
    # Trailing slashes are load-bearing: a sibling like .agents/skillset/ must
    # not be caught by a startswith against these prefixes; the literal pins them.
    assert amp.MANAGED_PREFIXES == (".agents/skills/", ".claude/skills/")


def test_gate_references_shared_constant() -> None:
    assert gase.MANAGED_PREFIXES is amp.MANAGED_PREFIXES


def test_em_dash_scanner_references_shared_constant() -> None:
    assert sred._SKIP_PREFIXES is amp.MANAGED_PREFIXES


def test_double_hyphen_scanner_includes_shared_constant() -> None:
    # This scanner skips a superset (it adds docs/archive/, docs/generated/), so
    # assert order-independent membership rather than position: every managed
    # prefix must be present wherever it sits in the composed tuple.
    for prefix in amp.MANAGED_PREFIXES:
        assert prefix in srdh._SKIP_PREFIXES
