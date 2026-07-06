# Auto-retro triage report

This file is generated from live GitHub retro-issue labels by `python3 scripts/auto_retro.py triage-report`. Do not edit it by hand. Unlike the per-script AST docs it is a non-deterministic snapshot of repository state, so it is refreshed on merge by the `post-merge.yml` workflow (which opens a pull request when the snapshot drifts) rather than as part of the deterministic generated docs.

Retros observed: **50**

Open untriaged: **27**

## Anomalies

None: no fired signal clears both the FP-rate and sample-size thresholds.

## Triage status

```mermaid
pie showData
    title Triage status
    "retro:tp" : 0
    "retro:fp" : 0
    "retro:fp-candidate" : 0
    "retro:tentative" : 0
    "unlabelled" : 50
```

## Signal occurrence and false-positive rates

| Signal | Fired | Fire rate | FP | FP rate | n | Anomaly |
| --- | --: | --: | --: | --: | --: | :-: |
| `inline_review_comments` | 42 | 0.84 | 0 | 0.00 | 42 |  |
| `fix_typed_title` | 8 | 0.16 | 0 | 0.00 | 8 |  |
| `multi_commit_pr` | 46 | 0.92 | 0 | 0.00 | 46 |  |

## False-positive rate trend

No triaged retros yet (no `retro:tp`/`retro:fp` labels).

## Recent retros

| # | State | Status | Title |
| --: | :-- | :-- | :-- |
| 2400 | open | untriaged | chore(auto-retro): review PR #2396 repair loops |
| 2385 | open | untriaged | chore(auto-retro): review PR #2383 repair loops |
| 2377 | open | untriaged | chore(auto-retro): review PR #2374 repair loops |
| 2375 | open | untriaged | chore(auto-retro): review PR #2373 repair loops |
| 2367 | open | untriaged | chore(auto-retro): review PR #2362 repair loops |
| 2365 | open | untriaged | chore(auto-retro): review PR #2345 repair loops |
| 2356 | open | untriaged | chore(auto-retro): review PR #2344 repair loops |
| 2353 | open | untriaged | chore(auto-retro): review PR #2321 repair loops |
| 2348 | open | untriaged | chore(auto-retro): review PR #2347 repair loops |
| 2346 | open | untriaged | chore(auto-retro): review PR #2343 repair loops |
