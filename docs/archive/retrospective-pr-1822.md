# Retrospective: PR #1822 ADR-0001 prek hook manager selection (retro close-out)

This document is the triage close-out for retro issue
[#1824](https://github.com/tvna/claude-md/issues/1824), the auto-opened
retrospective for PR [#1822](https://github.com/tvna/claude-md/pull/1822)
(ADR-0001, prek hook manager selection, merged 2026-06-17). It records the
true-positive verdict that closes the retro: all three durable improvement
candidates recorded in #1824 (R1-R3) have landed, so the retro is closed
`completed` with the `retro:tp` label per the close-time convention in
[`docs/runbooks/retro-labels.md`](../runbooks/retro-labels.md).

Per the same runbook, a retro is a triage signal, not a unit of work to
implement directly; the durable fixes were therefore implemented under a
separate follow-up issue and PR (#2100) and the retro is closed here by a
`docs(auto-retro): ...` retro-close PR rather than by the implementation PR.

## Scope

- Retro issue: [#1824](https://github.com/tvna/claude-md/issues/1824)
  (`type:retrospective`, `retro`, `layer:p3-harness`), opened 2026-06-17.
- Source PR: [#1822](https://github.com/tvna/claude-md/pull/1822)
  (ADR-0001 prek hook manager selection), merged 2026-06-17.
- Implementation PR for the durable fixes:
  [#2100](https://github.com/tvna/claude-md/pull/2100), merged as commit
  `a7d8395` ("chore(retro): land PR-1822 retro durable fixes R1-R3").
- Out of scope: the process repairs that occurred *during* #2100 itself.
  Those are recorded in their own follow-up retrospective,
  [#2109](https://github.com/tvna/claude-md/issues/2109) (an independent open
  retro), and are not a precondition for closing #1824.

## Triage verdict: true positive (retro:tp)

The three repairs #1824 recorded between PR #1822 open and merge were each a
real repair loop with a durable fix that has now landed. Under the runbook
close convention ("every follow-up issue listed in the retro body has closed
`completed` AND the retro acceptance criteria are checked off -> `retro:tp`"),
the follow-up work landed via #2100; the verdict is true positive.

## Repair disposition

| # | Repair (from #1824) | Classification | Durable fix | Landed in |
|---|---|---|---|---|
| R1 | Trailing whitespace rejected at push time by the prek `trailing-whitespace` hook | Missing deterministic gate | Added the `pre-commit` (commit-time) stage to the `trailing-whitespace` hook in `.pre-commit-config.yaml` so the violation surfaces at `git commit` instead of only at push/CI | #2100 (`a7d8395`) |
| R2 | Rebase-then-non-fast-forward loop on an already-pushed, force-push-prohibited branch | Unclear agent instruction | `docs/runbooks/remote-session-base-update.md` and the `preflight_session_base_freshness.py` messages gained a merge-vs-rebase decision branch (merge when a remote ref exists, rebase only when it does not) | #2100 (`a7d8395`) |
| R3 | ADR rationale implied automatic pre-push hook activation that the wiring does not perform | Unclear agent instruction | Added a wiring-accuracy verification item to the ADR authoring checklist in `docs/adr/TEMPLATE.md` | #2100 (`a7d8395`) |

### Note on the R2 probe correction

R2 as first implemented in #2100 used `git rev-parse --verify origin/<branch>`
to decide the merge-vs-rebase branch. A review on #2100 found that probe only
resolves the local remote-tracking ref under `refs/remotes/origin/`, which a
fresh remote session may not have fetched, so it could misroute an
already-published branch onto the rebase path. The probe was corrected to
`git ls-remote --exit-code --heads origin`, which queries the remote directly.
That correction and two other process repairs are captured in retro #2109; they
are listed here only for traceability and do not change the #1824 verdict.

## Why this is closed by a retro-close PR, not the implementation PR

`scripts/auto_retro.py verify-no-direct-retro-pr` (wired into
`.github/workflows/verify-pr.yml`) blocks any PR that closes or references a
retro issue unless that PR is itself a retro-close PR (a `type(auto-retro): ...`
title recognized by `is_retro_pr`). Implementation PR #2100 therefore used
`Refs #1824` with a `partial-pr` opt-out so its merge did not close the retro;
this `docs(auto-retro): ...` PR is the retro-close PR that records the verdict
and closes #1824 via `Closes #1824`.

Closing the retro here, with the `retro:tp` label applied before close, also
pre-empts the `daily-maintenance.yml` retro sentinel, which would otherwise
close #1824 as `not_planned` after `AUTO_RETRO_SENTINEL_DAYS` (~14 days) of
inactivity and mislabel a genuine true positive as an untriaged timeout.

## References

- Retro issue: [#1824](https://github.com/tvna/claude-md/issues/1824) (this
  document closes it).
- Source PR: [#1822](https://github.com/tvna/claude-md/pull/1822).
- Durable-fix implementation PR:
  [#2100](https://github.com/tvna/claude-md/pull/2100) (commit `a7d8395`).
- Follow-up retro for #2100 process repairs:
  [#2109](https://github.com/tvna/claude-md/issues/2109).
- Close convention: [`docs/runbooks/retro-labels.md`](../runbooks/retro-labels.md)
  ("Operator close-time convention").
- Sentinel backstop:
  [`docs/runbooks/retrospective-noise-flooding-procedure.md`](../runbooks/retrospective-noise-flooding-procedure.md)
  section 5.1.
- Framework: CLAUDE.md section 3 (auto-open a retrospective after each merge;
  classify each repair; turn the finding into a durable gate).
- Sibling retrospectives: `retrospective-pr-237.md`, `retrospective-pr-349.md`.
