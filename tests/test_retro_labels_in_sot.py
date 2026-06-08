"""Drift gate: every retro label SoT constant must be declared in labels.json.

Couples the two label sources of truth so they cannot drift apart:

* ``scripts/_retro_labels.py`` -- the ``retro:*`` feedback-loop constants
  (``ALL_RETRO_LABELS``) consumed by the scanner and the prior calculator.
* ``.github/labels.json`` -- the SoT that ``apply-labels.yml`` reconciles
  against (and prunes against).

A ``prune=true`` reconciliation (run 26839401015) deleted ``retro:fp``,
``type:retrospective`` and a stray ``retrospective`` label because they were
absent from ``.github/labels.json``, wiping ``retro:fp`` triage state from 23
auto-retro issues (root cause #1119; one-time restore PR #1120). Declaring the
family stopped the bleeding, but only this test makes the coupling enforceable:
if any retro label constant is ever missing from the JSON SoT, a future prune
could delete it again -- and this gate fails first.

Refs #1121 (this gate), #1119 (root cause), #1120 (restore).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import _retro_labels

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parents[1]
LABELS_JSON = REPO_ROOT / ".github" / "labels.json"

# ``type:retrospective`` is not a ``retro:*`` feedback-loop label so it does not
# live in ``ALL_RETRO_LABELS``, but it was deleted by the same prune and must
# stay declared in the JSON SoT for the same reason. Guard it explicitly.
TYPE_RETROSPECTIVE = "type:retrospective"

REQUIRED_IN_SOT = sorted(_retro_labels.ALL_RETRO_LABELS | {TYPE_RETROSPECTIVE})


def _sot_label_names() -> set[str]:
    raw = json.loads(LABELS_JSON.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise AssertionError(f"{LABELS_JSON} must be a JSON array of label objects")
    return {entry["name"] for entry in raw}


def test_labels_json_parses_as_list_of_named_entries() -> None:
    names = _sot_label_names()
    assert names, f"{LABELS_JSON} declared no labels"


@pytest.mark.parametrize("label", REQUIRED_IN_SOT)
def test_retro_label_declared_in_labels_json(label: str) -> None:
    names = _sot_label_names()
    assert label in names, (
        f"retro label '{label}' is missing from .github/labels.json; a prune run "
        f"of apply-labels.yml would delete it (see #1119). Add it to the SoT."
    )
