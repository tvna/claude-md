# Repair-free merge rate ledger

Primary convergence signal for CLAUDE.md section 3 ("measurably better each cycle"): repair-free merge rate = the weekly share of merges auto_retro.py evaluates where no repair signal fired. Refreshed by a bot PR after every merge (a non-deterministic GitHub-state snapshot, same treatment as the sibling triage report). Refs #2415.

## Stop rule

If the 4-week moving average declines for two consecutive observed weeks, stop scaling and re-plan per CLAUDE.md section 5 ("When the measured proportion of quality to volume degrades, stop and re-plan") instead of adding more scale on top of a regressing repair-free rate. The moving average spans 4 consecutive calendar weeks (a merge-free week counts toward the span with no rate of its own), not merely the last 4 weeks that happened to have a merge.

## Weekly repair-free rate

| ISO week | Merges | Repair-free | Rate | 4-week moving avg |
|---|---|---|---|---|
| 2026-W28 | 2 | 1 | 50.0% | n/a |
| 2026-W29 | 3 | 0 | 0.0% | n/a |

## Per-merge history

<!-- auto-retro-ledger:rows -->
| PR | Merged at (UTC) | Repair-free |
|---|---|---|
| #2443 | 2026-07-11T11:22:49Z | no |
| #2468 | 2026-07-11T14:12:57Z | yes |
| #2479 | 2026-07-14T00:06:31Z | no |
| #2484 | 2026-07-14T07:59:09Z | no |
| #2488 | 2026-07-14T08:36:52Z | no |
<!-- /auto-retro-ledger:rows -->
