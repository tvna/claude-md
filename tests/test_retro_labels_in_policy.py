"""Drift gate: the label-policy ``retro`` family matches the retro:* name SoT.

Couples the two homes of the retro:* labels so they cannot drift apart:

* ``scripts/_retro_labels.py``; the ``retro:*`` label NAMES
  (``ALL_RETRO_LABELS``), a side-effect-free Python constant imported widely at
  runtime.
* ``.github/label-policy.toml`` ``[[labels]]`` under ``family == "retro"``; the
  labels' IDENTITY (name/description/color), the single authored source that
  ``.github/labels.json`` reconciles to and ``scripts/scan_label_sot_drift.py``
  validates.

Before #2442 batch 1 the retro:* identity lived only in ``labels.json`` and was
exempt from the parity gate. Folding it into ``label-policy.toml`` closed that
gap, but the name set now exists in two files; this test is the enforceable
coupling that keeps them identical. Its sibling
``tests/test_retro_labels_in_sot.py`` guards the separate prune-safety invariant
(the names must also stay in ``labels.json`` so an ``apply-labels.yml``
``prune=true`` run cannot delete them).

Refs #2442 (this coupling), #558 (the retro:* constants).
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import _retro_labels

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parents[1]
LABEL_POLICY = REPO_ROOT / ".github" / "label-policy.toml"
RETRO_FAMILY = "retro"


def _policy_labels() -> list[dict[str, object]]:
    raw = tomllib.loads(LABEL_POLICY.read_text(encoding="utf-8"))
    labels = raw.get("labels")
    if not isinstance(labels, list):
        raise AssertionError(f"{LABEL_POLICY} has missing or non-list [[labels]]")
    return [entry for entry in labels if isinstance(entry, dict)]


def _retro_family_entries() -> list[dict[str, object]]:
    return [entry for entry in _policy_labels() if entry.get("family") == RETRO_FAMILY]


def test_retro_family_declared_in_policy() -> None:
    """label-policy.toml must declare the ``retro`` family (Design A)."""
    raw = tomllib.loads(LABEL_POLICY.read_text(encoding="utf-8"))
    families = {fam.get("name") for fam in raw.get("families", []) if isinstance(fam, dict)}
    assert RETRO_FAMILY in families, (
        f"label-policy.toml declares no '{RETRO_FAMILY}' [[families]] entry; the "
        f"retro:* labels below it would sit under an undeclared family."
    )


def test_policy_retro_family_matches_name_sot() -> None:
    """The policy ``retro`` family's names must equal ``ALL_RETRO_LABELS`` exactly."""
    policy_names = {entry.get("name") for entry in _retro_family_entries()}
    assert policy_names == set(_retro_labels.ALL_RETRO_LABELS), (
        "label-policy.toml [[labels]] family=retro drifted from "
        "scripts/_retro_labels.py ALL_RETRO_LABELS: "
        f"policy={sorted(str(n) for n in policy_names)} "
        f"constants={sorted(_retro_labels.ALL_RETRO_LABELS)}. Keep the two in sync."
    )


def test_type_retrospective_stays_retired_from_policy() -> None:
    """type:retrospective was retired outright by #972, never folded into policy."""
    policy_names = {entry.get("name") for entry in _policy_labels()}
    assert "type:retrospective" not in policy_names, (
        "'type:retrospective' was added to label-policy.toml, but #972 retired it "
        "outright (backfilled to type:docs, pruned from the live catalog); it must "
        "not be re-added."
    )


@pytest.mark.parametrize("field", ["description", "color"])
def test_retro_family_entries_carry_identity(field: str) -> None:
    """Every policy retro entry must carry a non-empty description and color."""
    for entry in _retro_family_entries():
        value = entry.get(field)
        assert isinstance(value, str) and value.strip(), (
            f"retro label {entry.get('name')!r} is missing a non-empty {field!r} "
            "in label-policy.toml"
        )
