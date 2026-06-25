# 0002. Merge-time INDEX budget gate and in-repo per-lane governance

Date: 2026-06-25
Refs: [#2012](https://github.com/tvna/claude-md/issues/2012),
[#2005](https://github.com/tvna/claude-md/issues/2005),
[#2007](https://github.com/tvna/claude-md/issues/2007),
[#1665](https://github.com/tvna/claude-md/issues/1665)

## Status

Accepted. Approved by the repository owner (@tvna) during the #2012
retrospective session: both the gate approach and the governance direction
were selected from prepared options.

## Context

`docs/INDEX.md` is the operator-facing inventory of the docs tree. A D3
navigation budget (`MAX_INDEX_BYTES`, 40960 bytes, in
`scripts/scan_docs_inventory.py`) caps its per-navigation read cost. The
`scan_docs_inventory verify` gate measures the byte size of the branch's own
working-tree `docs/INDEX.md`.

PR #2007 (per-lane document templates) failed its first CI run on seven checks,
all tracing to one root cause: when the PR head was test-merged with the live
`main`, `docs/INDEX.md` reached 41122 bytes, 162 over budget. Neither side was
over budget alone (`origin/main` 40109 B, PR branch 40622 B); `main` had
concurrently merged a proposals row (#2004) that, combined with the PR's four
template rows, crossed the budget only in the merge result. Because the working
-tree budget gate measures each branch in isolation, the additive merge growth
of two independent docs PRs was invisible until merge-time CI.

The repair was classified as a missing deterministic gate: the earliest gate
that should have caught it is one that measures the test-merge of HEAD against
the live base in branch preflight, which did not exist.

The deeper force is that `docs/INDEX.md` is a single mutable chokepoint. Every
docs PR, regardless of lane, contends for one shared byte budget, so unrelated
PRs serialize against each other near the ceiling.

## Decision

We will take two coordinated steps.

1. We will add a branch-preflight gate,
   `scripts/preflight_merge_index_budget.py`, that fetches the live base,
   computes the test-merge tree of HEAD with it via
   `git merge-tree --write-tree` (no working-tree mutation), and fails when the
   merged `docs/INDEX.md` exceeds `MAX_INDEX_BYTES`. It imports the budget
   constant from `scan_docs_inventory` so the budget stays single-sourced and is
   never bumped.

2. We will govern the `docs/INDEX.md` inventory by splitting it per lane
   **inside this repository** (the work tracked in #2005), and we will not
   extract the inventory into a separate repository.

## Why

- The merge-result measurement is the faithful fix for the observed failure:
  it measures exactly what merge-time CI measures, brought forward to branch
  preflight, so additive growth from an independent docs PR surfaces before
  push instead of at merge time.
- The in-repo per-lane split keeps every existing deterministic gate intact
  (inventory completeness, local-link resolution, generated-doc ownership) and
  has a small blast radius: it relocates tables and teaches the inventory gate
  to follow links transitively, with no cross-repository machinery.
- The two steps are complementary, not redundant: the gate holds the budget
  line deterministically now, while the per-lane split removes the chokepoint
  that makes the budget tight in the first place. The merge-result gate remains
  useful after the split, applied to whatever top-level INDEX the budget governs.

## Why not

- Per-PR headroom reservation (lowering the effective budget) is a heuristic
  margin, not a measurement: concurrent growth that exceeds the reserved margin
  still overflows at merge time, and it shrinks the usable budget for every PR.
- Extracting the inventory out of the repository removes the chokepoint but
  introduces a second source of truth and cross-repository sync, and either
  erodes or forces a cross-repository rewrite of the existing inventory and
  link gates. The cost outweighs the benefit for a harness-centric repository
  whose gates assume a single working tree.
- Raising `MAX_INDEX_BYTES` is forbidden by D3 and was not considered a
  remediation.

## Consequences

- Easier: merge-time-only INDEX overflow now fails in branch preflight and
  pre-push, with a message that names the per-lane-split remediation; the
  failure mode that took seven CI checks to surface is caught locally.
- Easier: the governance question is settled and recorded, so future docs PRs
  near the ceiling have a clear remediation path (#2005) instead of an open
  question.
- Harder: the new gate fetches the live base, so it needs network access and
  runs after `preflight_branch_base`; on a conflicting base it defers (warns,
  does not fail) to that gate rather than reporting a false budget number.
- Harder, transitional: until #2005 lands, INDEX headroom stays tight, so a
  new INDEX row plus concurrent base growth can still trip the new gate at
  merge time. That is the gate working as intended; the durable relief is the
  per-lane split.

## Considered Alternatives

- **Per-PR headroom reservation.** Rejected: a fixed margin is a guess that
  both under-protects (concurrent growth beyond the margin still overflows at
  merge) and over-penalizes (every PR loses usable budget). Fact: it would have
  caught #2007 only with a reserved margin above 338 bytes. Speculation: tuning
  that margin would become its own recurring maintenance burden.
- **Extract the inventory from the repository.** Rejected for blast radius: a
  second source of truth, cross-repository sync, and gate erosion or rewrite,
  as detailed in "Why not".
- **Rely solely on the #2005 per-lane split.** Rejected as the sole step: #2005
  is scoped to its own PR (the transitive-link-following change is the larger
  part), and leaving the budget ungated until it lands keeps the merge-time
  blind spot open. The gate is the immediate deterministic fix; #2005 is the
  structural one.
- **Raise `MAX_INDEX_BYTES`.** Rejected: D3 forbids a budget bump as the
  remediation.
