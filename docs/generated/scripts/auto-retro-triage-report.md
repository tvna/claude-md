# Auto-retro triage report

This file is generated from live GitHub retro-issue labels by `python3 scripts/auto_retro.py triage-report`. Do not edit it by hand. Unlike the per-script AST docs it is a non-deterministic snapshot of repository state, so it is refreshed on merge by the `post-merge.yml` workflow (which opens a pull request when the snapshot drifts) rather than as part of the deterministic generated docs.

Retros observed: **105**

Open untriaged: **45**

## Anomalies

- **unlabelled ratio 0.94**: 99 of 105 observed retros carry no `retro:*` label (>= 0.50, n >= 5); retros are being opened faster than they are triaged.

## Loop health

- Triage rate: **6 / 105** (6%) of observed retros carry a `retro:*` label; **99** (94%) remain unlabelled.
- Sentinel disposal: **0** (0%) auto-closed via `retro:expired` without operator engagement.

## Triage status

```mermaid
pie showData
    title Triage status
    "retro:tp" : 5
    "retro:fp" : 1
    "retro:fp-candidate" : 0
    "retro:tentative" : 0
    "retro:expired" : 0
    "unlabelled" : 99
```

## Signal occurrence and false-positive rates

| Signal | Fired | Fire rate | FP | FP rate | n | Anomaly |
| --- | --: | --: | --: | --: | --: | :-: |
| `inline_review_comments` | 34 | 0.32 | 0 | 0.00 | 34 |  |
| `fix_typed_title` | 8 | 0.08 | 0 | 0.00 | 8 |  |
| `multi_commit_pr` | 40 | 0.38 | 0 | 0.00 | 40 |  |

## False-positive rate trend

- All-time: 0.17 (n=6 triaged)
- Last 20 retros: 0.00 (n=0 triaged); n/a

## Recent retros

| # | State | Status | Title |
| --: | :-- | :-- | :-- |
| 2517 | open | untriaged | chore(auto-retro): review PR #2516 repair loops |
| 2511 | open | untriaged | chore(auto-retro): review PR #2510 repair loops |
| 2502 | open | untriaged | chore(auto-retro): review PR #2501 repair loops |
| 2498 | open | untriaged | chore(auto-retro): review PR #2497 repair loops |
| 2493 | open | untriaged | chore(auto-retro): review PR #2492 repair loops |
| 2489 | open | untriaged | chore(auto-retro): review PR #2488 repair loops |
| 2485 | open | untriaged | chore(auto-retro): review PR #2484 repair loops |
| 2480 | open | untriaged | chore(auto-retro): review PR #2479 repair loops |
| 2469 | open | untriaged | chore(auto-retro): review PR #2443 repair loops |
| 2464 | open | untriaged | chore(auto-retro): review PR #2463 repair loops |
