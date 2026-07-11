# Auto-retro triage report

This file is generated from live GitHub retro-issue labels by `python3 scripts/auto_retro.py triage-report`. Do not edit it by hand. Unlike the per-script AST docs it is a non-deterministic snapshot of repository state, so it is refreshed on merge by the `post-merge.yml` workflow (which opens a pull request when the snapshot drifts) rather than as part of the deterministic generated docs.

Retros observed: **93**

Open untriaged: **33**

## Anomalies

None: no fired signal clears both the FP-rate and sample-size thresholds.

## Triage status

```mermaid
pie showData
    title Triage status
    "retro:tp" : 5
    "retro:fp" : 0
    "retro:fp-candidate" : 0
    "retro:tentative" : 0
    "retro:expired" : 0
    "unlabelled" : 88
```

## Signal occurrence and false-positive rates

| Signal | Fired | Fire rate | FP | FP rate | n | Anomaly |
| --- | --: | --: | --: | --: | --: | :-: |
| `inline_review_comments` | 24 | 0.26 | 0 | 0.00 | 24 |  |
| `fix_typed_title` | 5 | 0.05 | 0 | 0.00 | 5 |  |
| `multi_commit_pr` | 28 | 0.30 | 0 | 0.00 | 28 |  |

## False-positive rate trend

- All-time: 0.00 (n=5 triaged)
- Last 20 retros: 0.00 (n=0 triaged); n/a

## Recent retros

| # | State | Status | Title |
| --: | :-- | :-- | :-- |
| 2430 | open | untriaged | chore(auto-retro): review PR #2402 repair loops |
| 2427 | open | untriaged | chore(auto-retro): review PR #2426 repair loops |
| 2423 | open | untriaged | chore(auto-retro): review PR #2422 repair loops |
| 2412 | open | untriaged | docs(runbook): fix retro-doc drift (refresh cadence, phantom script name) |
| 2400 | open | untriaged | chore(auto-retro): review PR #2396 repair loops |
| 2385 | open | untriaged | chore(auto-retro): review PR #2383 repair loops |
| 2377 | open | untriaged | chore(auto-retro): review PR #2374 repair loops |
| 2375 | open | untriaged | chore(auto-retro): review PR #2373 repair loops |
| 2367 | open | untriaged | chore(auto-retro): review PR #2362 repair loops |
| 2365 | open | untriaged | chore(auto-retro): review PR #2345 repair loops |
