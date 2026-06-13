# Auto-retro triage report

This file is generated from live GitHub retro-issue labels by `python3 scripts/auto_retro.py triage-report`. Do not edit it by hand. Unlike the per-script AST docs it is a non-deterministic snapshot of repository state, so it is refreshed on merge by the `post-merge.yml` workflow (which opens a pull request when the snapshot drifts) rather than as part of the deterministic generated docs.

Retros observed: **50**

Open untriaged: **11**

## Anomalies

None: no fired signal clears both the FP-rate and sample-size thresholds.

## Triage status

```mermaid
pie showData
    title Triage status
    "retro:tp" : 9
    "retro:fp" : 30
    "retro:fp-candidate" : 0
    "retro:tentative" : 0
    "unlabelled" : 11
```

## Signal occurrence and false-positive rates

| Signal | Fired | Fire rate | FP | FP rate | n | Anomaly |
| --- | --: | --: | --: | --: | --: | :-: |
| `inline_review_comments` | 0 | 0.00 | 0 | 0.00 | 0 |  |
| `fix_typed_title` | 17 | 0.34 | 7 | 0.41 | 17 |  |
| `multi_commit_pr` | 21 | 0.42 | 8 | 0.38 | 21 |  |

## False-positive rate trend

- All-time: 0.77 (n=39 triaged)
- Last 20 retros: 0.78 (n=9 triaged) -- rising

## Recent retros

| # | State | Status | Title |
| --: | :-- | :-- | :-- |
| 1661 | open | untriaged | chore(auto-retro): review PR #1659 repair loops |
| 1600 | open | untriaged | chore(auto-retro): review PR #1599 repair loops |
| 1592 | open | untriaged | chore(auto-retro): review PR #1589 repair loops |
| 1585 | open | untriaged | chore(auto-retro): review PR #1584 repair loops |
| 1568 | open | untriaged | chore(auto-retro): review PR #1567 repair loops |
| 1518 | open | untriaged | chore(auto-retro): review PR #1517 repair loops |
| 1505 | open | untriaged | chore(auto-retro): review PR #1500 repair loops |
| 1483 | open | untriaged | chore(auto-retro): review PR #1481 repair loops |
| 1482 | open | untriaged | chore(auto-retro): review PR #1480 repair loops |
| 1479 | open | untriaged | chore(auto-retro): review PR #1474 repair loops |
