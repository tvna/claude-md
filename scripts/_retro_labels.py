"""Single source of truth for retrospective issue labels.

Mirrors the pattern in ``scripts/_trusted_bots.py`` and
``scripts/_ref_classifier.py``: constants only, no side effects,
importable from both ``scripts/`` and ``tests/``.

The labels here govern the TP/FP feedback loop that retrofits the
retro convergence problem; ``scripts/auto_retro.py`` opens retros from
single-PR-local signals with no mid-to-long-term context, so retros
accumulate without converging. The labels are how operators (and the
scanner under ``scripts/scan_retro_followup_drift.py``) record whether
a given retro was a true positive or a false positive once its
follow-ups settle.

Operator convention (see ``docs/runbooks/retro-labels.md``):

* ``retro:tp``            ; operator-confirmed true positive: the
  follow-up gate or instruction change has landed and is producing the
  expected reduction in repair loops.
* ``retro:fp``            ; confirmed false positive: either the
  operator marked it so, or the scanner auto-confirmed it because the
  follow-up was closed not-planned or the follow-up PR was closed
  unmerged.
* ``retro:fp-candidate``  ; the scanner detected drift (follow-up
  stale or referenced ``#N`` does not resolve) and is asking the
  operator to confirm ``retro:fp`` or relabel ``retro:tp``.
* ``retro:tentative``     ; auto-opened with low prior confidence
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

# The retrospective issue's identity label. Not a retro:* feedback-loop label,
# so it is deliberately absent from ALL_RETRO_LABELS, but it shares the same
# labels.json prune-safety coupling (tests/test_retro_labels_in_sot.py) and the
# same runtime source: it is a live label applied by the retro creation path,
# not authored in .github/label-policy.toml. Defined here as the single source
# so consumers (e.g. scripts/scan_label_sot_drift.py) import it instead of
# freezing the string.
TYPE_RETROSPECTIVE: Final[str] = "type:retrospective"

# Thresholds for the label-derived prior consumed by
# ``scripts/auto_retro.py`` (PR2 of the TP/FP retrofit, refs #582).
#
# The prior maps each repair signal (`inline_review_comments`,
# `fix_typed_title`, `multi_commit_pr`, `verification_pairs_failed`) to
# its historical false-positive rate, computed from past retros that
# carry ``retro:fp``. (`body_cites_refs` was retired as a standalone
# trigger in #1227 because it fired on nearly every PR; CLAUDE.md
# section 3 mandates a ``Refs #N`` line; and dominated prior pollution.)
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
# ``BOOTSTRAP_UNTIL`` from the original plan; sample-size driven
# safety is more robust than a date and self-clears as the operator +
# the #560 scanner populate labels organically.
PRIOR_SKIP_THRESHOLD: Final[float] = 0.5
PRIOR_TENTATIVE_THRESHOLD: Final[float] = 0.3
PRIOR_MIN_SAMPLE_SIZE: Final[int] = 5
PRIOR_FETCH_LIMIT: Final[int] = 50

# Default fetch cap for the descriptive triage report (refs #2413), distinct
# from PRIOR_FETCH_LIMIT: the live skip decision above intentionally samples
# only the most recent PRIOR_FETCH_LIMIT retros, but the report exists to
# describe the FULL retro population, so it needs a much larger ceiling. 1000
# is GitHub's own hard cap on a single search query (10 pages x per_page=100);
# fetch_past_retro_population paginates up to this many results and reports
# any live total beyond it as an explicit truncation rather than a silent cap.
TRIAGE_REPORT_FETCH_LIMIT: Final[int] = 1000

# Prior epoch boundary (refs #1227, advanced for #1236). Retros opened
# before a signal-semantics fix measured the OLD (buggy) signal
# definitions, so their ``retro:fp`` labels must not drive
# ``should_skip_by_prior`` after the fix; otherwise a mass ``retro:fp``
# cleanup would poison the prior and suppress genuine post-fix repair
# retros. Only retros whose issue number is at or above this boundary
# contribute to the live skip decision (``auto_retro.run`` passes it; the
# descriptive triage report keeps the full population).
#
# History:
# - 1228 (#1227): first epoch, just above the original pre-fix population
#   (highest pre-fix retro #1225) for the #1226 Phase B cleanup of ~33 FPs.
# - 1460 (#1236): advanced after ``verification_pairs_failed`` was retired
#   as a standalone trigger and its prose ``Verification fail`` rows were
#   demoted to non-actionable policy-artifact anomaly hints. The second
#   retro flood (#1235..#1459) was the prose-verification FP class the
#   #1227 fix did not reach; labelling that batch ``retro:fp`` would poison
#   the surviving ``multi_commit_pr`` / ``fix_typed_title`` priors, so the
#   boundary moves just above the highest retro in that batch (#1459).
PRIOR_EPOCH_MIN_RETRO_NUMBER: Final[int] = 1460
