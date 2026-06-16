# Auto-retro triage report

This file is generated from live GitHub retro-issue labels by `python3 scripts/auto_retro.py triage-report`. Do not edit it by hand. Unlike the per-script AST docs it is a non-deterministic snapshot of repository state, so it is refreshed on merge by the `post-merge.yml` workflow (which opens a pull request when the snapshot drifts) rather than as part of the deterministic generated docs.

Retros observed: **50**

Open untriaged: **16**

## Anomalies

None: no fired signal clears both the FP-rate and sample-size thresholds.

## Triage status

```mermaid
pie showData
    title Triage status
    "retro:tp" : 8
    "retro:fp" : 26
    "retro:fp-candidate" : 0
    "retro:tentative" : 0
    "unlabelled" : 16
```

## Signal occurrence and false-positive rates

| Signal | Fired | Fire rate | FP | FP rate | n | Anomaly |
| --- | --: | --: | --: | --: | --: | :-: |
| `inline_review_comments` | 5 | 0.10 | 0 | 0.00 | 5 |  |
| `fix_typed_title` | 16 | 0.32 | 5 | 0.31 | 16 |  |
| `multi_commit_pr` | 24 | 0.48 | 7 | 0.29 | 24 |  |

## False-positive rate trend

- All-time: 0.76 (n=34 triaged)
- Last 20 retros: 0.75 (n=4 triaged) -- falling

## Recent retros

| # | State | Status | Title |
| --: | :-- | :-- | :-- |
| 1760 | open | untriaged | chore(auto-retro): review PR #1757 repair loops |
| 1758 | open | untriaged | chore(auto-retro): review PR #1755 repair loops |
| 1747 | open | untriaged | chore(auto-retro): review PR #1746 repair loops |
| 1741 | open | untriaged | chore(auto-retro): review PR #1738 repair loops |
| 1733 | open | untriaged | chore(auto-retro): review PR #1730 repair loops |
| 1661 | open | untriaged | chore(auto-retro): review PR #1659 repair loops |
| 1600 | open | untriaged | chore(auto-retro): review PR #1599 repair loops |
| 1592 | open | untriaged | chore(auto-retro): review PR #1589 repair loops |
| 1585 | open | untriaged | chore(auto-retro): review PR #1584 repair loops |
| 1568 | open | untriaged | chore(auto-retro): review PR #1567 repair loops |
