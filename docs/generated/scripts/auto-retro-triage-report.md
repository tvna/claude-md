# Auto-retro triage report

This file is generated from live GitHub retro-issue labels by `python3 scripts/auto_retro.py triage-report`. Do not edit it by hand. Unlike the per-script AST docs it is a non-deterministic snapshot of repository state, so it is refreshed on merge by the `post-merge.yml` workflow (which opens a pull request when the snapshot drifts) rather than as part of the deterministic generated docs.

Retros observed: **50**

Open untriaged: **29**

## Anomalies

None: no fired signal clears both the FP-rate and sample-size thresholds.

## Triage status

```mermaid
pie showData
    title Triage status
    "retro:tp" : 3
    "retro:fp" : 18
    "retro:fp-candidate" : 0
    "retro:tentative" : 0
    "unlabelled" : 29
```

## Signal occurrence and false-positive rates

| Signal | Fired | Fire rate | FP | FP rate | n | Anomaly |
| --- | --: | --: | --: | --: | --: | :-: |
| `inline_review_comments` | 17 | 0.34 | 0 | 0.00 | 17 |  |
| `fix_typed_title` | 16 | 0.32 | 4 | 0.25 | 16 |  |
| `multi_commit_pr` | 32 | 0.64 | 5 | 0.16 | 32 |  |

## False-positive rate trend

- All-time: 0.86 (n=21 triaged)
- Last 20 retros: 0.00 (n=0 triaged) -- n/a

## Recent retros

| # | State | Status | Title |
| --: | :-- | :-- | :-- |
| 1845 | open | untriaged | chore(auto-retro): review PR #1841 repair loops |
| 1842 | open | untriaged | chore(auto-retro): review PR #1838 repair loops |
| 1835 | open | untriaged | chore(auto-retro): review PR #1834 repair loops |
| 1831 | open | untriaged | chore(auto-retro): review PR #1830 repair loops |
| 1823 | open | untriaged | chore(auto-retro): review PR #1822 repair loops |
| 1816 | open | untriaged | chore(auto-retro): review PR #1815 repair loops |
| 1811 | open | untriaged | chore(auto-retro): review PR #1727 repair loops |
| 1806 | open | untriaged | chore(auto-retro): review PR #1780 repair loops |
| 1803 | open | untriaged | chore(auto-retro): review PR #1801 repair loops |
| 1797 | open | untriaged | chore(auto-retro): review PR #1796 repair loops |
