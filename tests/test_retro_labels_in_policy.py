"""Drift gate: the label-policy ``retro`` family matches the retro:* name SoT.

Couples the two homes of the retro:* labels so they cannot drift apart:

* ``scripts/_retro_labels.py``; the ``retro:*`` label NAMES
  (``ALL_RETRO_LABELS``), a side-effect-free Python constant imported widely at
  runtime.
* ``.github/label-policy.toml`` ``[[labels]]`` under ``family == "retro"``; the
  labels' IDENTITY (name/description/color) in the single label SoT, from which
  ``apply-labels.yml`` derives the live catalog it reconciles to GitHub.

Before #2442 batch 1 the retro:* identity lived only in ``labels.json`` and was
exempt from the old parity gate. Folding it into ``label-policy.toml`` closed
that gap, and #2499 retired ``labels.json`` entirely so the policy is now the
one authored home; this test is the enforceable coupling that keeps the policy
``retro`` family and the ``ALL_RETRO_LABELS`` constant identical. Because the
retro:* entries are ``status = "keep"`` in the policy, they are in the derived
live catalog, so an ``apply-labels.yml`` ``prune=true`` run cannot delete them
(the prune-safety invariant #1119 first exposed).

Refs #2442 (this coupling), #558 (the retro:* constants), #1119 (prune safety),
#2499 (labels.json retirement).
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import _retro_labels
import labels_apply

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


def test_retro_labels_are_in_derived_live_catalog() -> None:
    """Prune-safety (#1119): every retro:* constant must appear in the live
    catalog derived from the policy by ``labels_apply.load_sot_from_policy``,
    which keeps only ``status in {keep, rename}`` entries.

    ``test_policy_retro_family_matches_name_sot`` above only couples the retro
    NAMES; it stays green if a future edit keeps ``family = "retro"`` and the
    name but flips a retro entry to ``status = "add"``. That regression would
    silently drop the label from the derived catalog, letting an
    ``apply-labels.yml`` ``prune=true`` run delete the live retro label again
    (the #1119 accident). This test asserts the live-status condition directly,
    so such drift fails here first. Refs #2499, #1119.
    """
    catalog_names = {
        str(entry["name"]) for entry in labels_apply.load_sot_from_policy(LABEL_POLICY)
    }
    missing = sorted(set(_retro_labels.ALL_RETRO_LABELS) - catalog_names)
    assert not missing, (
        f"retro labels {missing} are not in the policy-derived live catalog; they "
        "must be status keep/rename so an apply-labels.yml prune run cannot delete "
        "them (#1119)."
    )
