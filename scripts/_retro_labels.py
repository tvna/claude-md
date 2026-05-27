"""Single source of truth for retrospective issue labels.

Mirrors the pattern in ``scripts/_trusted_bots.py`` and
``scripts/_ref_classifier.py``: constants only, no side effects,
importable from both ``scripts/`` and ``tests/``.

The labels here govern the TP/FP feedback loop that retrofits the
retro convergence problem -- ``scripts/auto_retro.py`` opens retros from
single-PR-local signals with no mid-to-long-term context, so retros
accumulate without converging. The labels are how operators (and the
scanner under ``scripts/scan_retro_followup_drift.py``) record whether
a given retro was a true positive or a false positive once its
follow-ups settle.

Operator convention (see ``docs/retro-labels.md``):

* ``retro:tp``             -- operator-confirmed true positive: the
  follow-up gate or instruction change has landed and is producing the
  expected reduction in repair loops.
* ``retro:fp``             -- confirmed false positive: either the
  operator marked it so, or the scanner auto-confirmed it because the
  follow-up was closed not-planned or the follow-up PR was closed
  unmerged.
* ``retro:fp-candidate``   -- the scanner detected drift (follow-up
  stale or referenced ``#N`` does not resolve) and is asking the
  operator to confirm ``retro:fp`` or relabel ``retro:tp``.
* ``retro:tentative``      -- auto-opened with low prior confidence
  (reserved for a future PR that retrofits
  ``scripts/auto_retro.py:compute_repair_signals`` with a label-derived
  prior). Not used by the PR1 scanner.

Refs #558.
"""

from __future__ import annotations

from typing import Final

RETRO_TP: Final[str] = "retro:tp"
RETRO_FP: Final[str] = "retro:fp"
RETRO_FP_CANDIDATE: Final[str] = "retro:fp-candidate"
RETRO_TENTATIVE: Final[str] = "retro:tentative"

ALL_RETRO_LABELS: Final[frozenset[str]] = frozenset(
    {RETRO_TP, RETRO_FP, RETRO_FP_CANDIDATE, RETRO_TENTATIVE}
)
