# Retrospective Labels - Operator Runbook

This document is the operator-facing runbook for the four retrospective
labels that govern the TP/FP feedback loop. The labels turn human
classification (`retro:tp` / `retro:fp`) into machine-readable prior
information that future PRs will consume in
`scripts/auto_retro.py:compute_repair_signals` and the classification
heuristic. The labels are also written by the scanner
`scripts/scan_retro_followup_drift.py` when follow-up issues/PRs drift.

The labels live as a single source of truth in
[`scripts/_retro_labels.py`](../scripts/_retro_labels.py). Refs #558.

## SoT layout

| File | Purpose |
|---|---|
| `scripts/_retro_labels.py` | Label string constants and `ALL_RETRO_LABELS` frozenset |
| `scripts/scan_retro_followup_drift.py` | Daily scanner that applies `retro:fp-candidate` and `retro:fp` based on follow-up state |
| `.github/workflows/retro-followup-drift.yml` | Cron + `workflow_dispatch` driver for the scanner |
| `docs/retro-labels.md` *(this file)* | Operator runbook |

## The four labels

### `retro:tp`

Operator-confirmed **true positive**: the retro identified a real repair
loop, the follow-up gate or instruction change has landed, and the
follow-up has produced the expected reduction in subsequent repair
loops.

Applied by: operator only. The scanner never applies this label.

When to apply: at retro issue close time, when the follow-up issues
listed in the retro body have closed `completed` AND the retro's
acceptance criteria are checked off.

### `retro:fp`

**Confirmed false positive**: the retro was a noise hit. Two paths:

- Operator-confirmed: the operator decided the retro reflects a
  non-recurring local condition rather than a systemic gap.
- Scanner-confirmed: the follow-up issue closed with `state_reason:
  not_planned`, or the follow-up PR closed unmerged. Both signals are
  unambiguous enough that the scanner promotes the candidate label
  directly without operator intervention.

Applied by: operator OR scanner.

### `retro:fp-candidate`

**Scanner-detected drift candidate**: the scanner observed a soft drift
signal (follow-up `#N` does not resolve, or follow-up is open and stale
for 30 or more days by `updated_at`) and is asking the operator to
review. The operator's job is to either:

- Investigate, conclude the retro is genuinely a false positive, and
  relabel `retro:fp` (the candidate label may be left in place or
  stripped manually -- the scanner does not strip it).
- Investigate, conclude the retro is a true positive whose follow-up
  is merely slow, and relabel `retro:tp`. The operator may also
  bump the follow-up `updated_at` (a comment is sufficient) to take
  the retro out of stale-candidate consideration on the next scan.

Applied by: scanner only. Operators are not expected to apply this
label by hand; they apply `retro:fp` directly when they have made the
call.

### `retro:tentative`

**Auto-opened with low prior confidence**: reserved for a future PR
that retrofits `scripts/auto_retro.py:compute_repair_signals` with a
label-derived prior. Not used by the PR1 scanner.

When the future signal-layer retrofit lands, the auto-retro flow will
attach this label to retros opened when the per-signal-combination
historical false-positive rate is in a "uncertain" middle band: the
retro is opened (so the audit trail is preserved) but flagged for the
operator to make the call.

## Operator close-time convention

When closing a retro issue, apply exactly one of `retro:tp` or
`retro:fp` BEFORE closing. The rule is mechanical, not subjective:

1. If every follow-up issue listed in the retro body has closed
   `completed` and the retro acceptance criteria are checked off, apply
   `retro:tp`.
2. If any follow-up closed `not_planned`, or was closed unmerged (PR),
   or no follow-up was opened at all and the original repair was a
   one-off, apply `retro:fp`.
3. If the scanner already applied `retro:fp` or `retro:fp-candidate`,
   the operator decision still stands: relabel as needed before
   closing.

The labels are read-only after close. If a later observation changes
the picture, open a new retro that refs the old one rather than
re-labelling history -- the prior calculator treats the historical
record as a snapshot in time.

## Scanner behaviour summary

The scanner under `scripts/scan_retro_followup_drift.py` runs daily at
06:37 UTC. For each open retro issue (filtered by `type:docs +
layer:meta` labels per the `auto_retro.issue_labels` convention) it:

1. Parses the retro body for follow-up `#N` references in checkbox
   bullet form (`- [ ]` or `- [x]` with a `#N` somewhere on the same
   line). HTML comments are stripped first.
2. Fetches each `#N` via `gh api /repos/{repo}/issues/{N}` (the GitHub
   Issues endpoint resolves both issues and PRs).
3. For each follow-up, classifies the drift:

   | Follow-up state | Result |
   |---|---|
   | 404 (does not resolve) | `not_found` -> `fp_candidate` after aggregation |
   | Issue closed `not_planned` | `fp_confirmed` |
   | PR closed unmerged | `fp_confirmed` |
   | Open, `updated_at` 30+ days stale | `fp_candidate` |
   | Anything else | `ok` |

4. Aggregates per-followup results into one verdict (worst signal
   wins).
5. Decides the label to apply:
   - `retro:tp` or `retro:fp` already present -> no-op.
   - `fp_confirmed` -> apply `retro:fp` (upgrading any candidate
     present).
   - `fp_candidate` without existing `retro:fp-candidate` -> apply
     `retro:fp-candidate`.
   - Otherwise -> no-op.

The scanner never removes labels. Operators who want a clean label set
on close can strip `retro:fp-candidate` manually before applying the
final `retro:tp` / `retro:fp`.

## Idempotency

The scanner is safe to re-run: every state change is gated by an
existing-label check (see `decide_target_label` in
`scripts/scan_retro_followup_drift.py`). A retro that has been
labelled `retro:fp-candidate` on one day will not be re-labelled the
next day unless its drift verdict escalates to `fp_confirmed`.

## Why these particular signals

The drift signals are deliberately restricted to GitHub state and link
structure (per CLAUDE.md section 2, body text is untrusted). The
choice rules out:

- Body text parsing of follow-up issues to "infer" whether they were
  abandoned.
- Comment-counting heuristics ("low engagement = false positive").
- Author-pattern matching ("this operator's retros are usually false
  positives").

Each of those would introduce a noise channel that operators would
have to compensate for. The chosen rules are crude but they are also
deterministic and auditable; an operator looking at any
`retro:fp-candidate` label can trace it to exactly one of the five
rules above and verify the signal on the linked follow-up.

## Verify

```sh
# 1. The doc is ASCII-only (it must pass scan-non-ascii.yml).
python3 -c "import pathlib; pathlib.Path('docs/retro-labels.md').read_text().encode('ascii')"

# 2. The label SoT exposes the four constants this doc enumerates.
python3 -c "from scripts._retro_labels import ALL_RETRO_LABELS; \
  assert ALL_RETRO_LABELS == {'retro:tp', 'retro:fp', 'retro:fp-candidate', 'retro:tentative'}"

# 3. Targeted tests pass.
uv run pytest tests/test_scan_retro_followup_drift.py -v
```

## References

- [`scripts/_retro_labels.py`](../scripts/_retro_labels.py) -- label SoT.
- [`scripts/scan_retro_followup_drift.py`](../scripts/scan_retro_followup_drift.py) -- scanner.
- [`.github/workflows/retro-followup-drift.yml`](../.github/workflows/retro-followup-drift.yml) -- cron driver.
- [`scripts/auto_retro.py`](../scripts/auto_retro.py) -- the retro generator the labels feed back into.
- [CLAUDE.md](../CLAUDE.md) section 3 -- retro framework rationale.
- [#558](https://github.com/tvna/claude-md/issues/558) -- PR1 issue.
