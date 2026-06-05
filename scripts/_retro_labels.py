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

Operator convention (see ``docs/runbooks/retro-labels.md``):

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

# Thresholds for the label-derived prior consumed by
# ``scripts/auto_retro.py`` (PR2 of the TP/FP retrofit, refs #582).
#
# The prior maps each repair signal (`inline_review_comments`,
# `fix_typed_title`, `multi_commit_pr`, `verification_pairs_failed`) to
# its historical false-positive rate, computed from past retros that
# carry ``retro:fp``. (`body_cites_refs` was retired as a standalone
# trigger in #1227 because it fired on nearly every PR -- CLAUDE.md
# section 3 mandates a ``Refs #N`` line -- and dominated prior pollution.)
# ``auto_retro.run``
# evaluates the prior AFTER signal computation and uses the MAX
# fp_rate across active signals to decide:
#
# * fp_rate >= PRIOR_SKIP_THRESHOLD              -> skip retro opening
# * PRIOR_TENTATIVE_THRESHOLD <= fp_rate < SKIP  -> open with retro:tentative
# * fp_rate < PRIOR_TENTATIVE_THRESHOLD          -> open normally
#
# The decision is gated by ``PRIOR_MIN_SAMPLE_SIZE`` so an unknown
# prior (fewer than N past observations of the signal) does not skip:
# the gate degrades safely toward "open normally" when the population
# is too thin to estimate. This replaces the date-based
# ``BOOTSTRAP_UNTIL`` from the original plan -- sample-size driven
# safety is more robust than a date and self-clears as the operator +
# the #560 scanner populate labels organically.
PRIOR_SKIP_THRESHOLD: Final[float] = 0.5
PRIOR_TENTATIVE_THRESHOLD: Final[float] = 0.3
PRIOR_MIN_SAMPLE_SIZE: Final[int] = 5
PRIOR_FETCH_LIMIT: Final[int] = 50

# Prior epoch boundary (refs #1227). Retros opened before the #1227
# signal-semantics fix measured the OLD (buggy) ``verification_pairs_failed``
# and the now-retired ``body_cites_refs`` definitions, so their ``retro:fp``
# labels must not drive ``should_skip_by_prior`` after the fix -- otherwise
# the #1226 cleanup, which labels ~33 pre-fix false positives ``retro:fp``,
# would poison the prior and suppress genuine post-fix repair retros. Only
# retros whose issue number is at or above this boundary contribute to the
# live skip decision (``auto_retro.run`` passes it; the descriptive
# triage report keeps the full population). The value sits just above the
# pre-fix retro population (highest pre-fix retro was #1225; #1226 is the
# tracking issue, #1227 the fix issue), so the prior degrades to the
# empty-prior safety net (open normally) until post-fix retros accumulate.
PRIOR_EPOCH_MIN_RETRO_NUMBER: Final[int] = 1228
