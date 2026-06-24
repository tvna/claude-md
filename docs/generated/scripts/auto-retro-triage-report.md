# Auto-retro triage report

This file is generated from live GitHub retro-issue labels by `python3 scripts/auto_retro.py triage-report`. Do not edit it by hand. Unlike the per-script AST docs it is a non-deterministic snapshot of repository state, so it is refreshed on merge by the `post-merge.yml` workflow (which opens a pull request when the snapshot drifts) rather than as part of the deterministic generated docs.

Retros observed: **50**

Open untriaged: **8**

## Anomalies

None: no fired signal clears both the FP-rate and sample-size thresholds.

## Triage status

```mermaid
pie showData
    title Triage status
    "retro:tp" : 1
    "retro:fp" : 7
    "retro:fp-candidate" : 0
    "retro:tentative" : 0
    "unlabelled" : 42
```

## Signal occurrence and false-positive rates

| Signal | Fired | Fire rate | FP | FP rate | n | Anomaly |
| --- | --: | --: | --: | --: | --: | :-: |
| `inline_review_comments` | 27 | 0.54 | 0 | 0.00 | 27 |  |
| `fix_typed_title` | 19 | 0.38 | 2 | 0.11 | 19 |  |
| `multi_commit_pr` | 39 | 0.78 | 2 | 0.05 | 39 |  |

## False-positive rate trend

- All-time: 0.88 (n=8 triaged)
- Last 20 retros: 0.00 (n=0 triaged); n/a

## Recent retros

| # | State | Status | Title |
| --: | :-- | :-- | :-- |
| 1935 | open | untriaged | chore(auto-retro): review PR #1934 repair loops |
| 1929 | open | untriaged | chore(auto-retro): review PR #1927 repair loops |
| 1917 | open | untriaged | chore(auto-retro): review PR #1909 repair loops |
| 1910 | open | untriaged | chore(auto-retro): review PR #1908 repair loops |
| 1905 | open | untriaged | chore(auto-retro): review PR #1900 repair loops |
| 1894 | open | untriaged | chore(auto-retro): review PR #1891 repair loops |
| 1887 | open | untriaged | chore(auto-retro): review PR #1883 repair loops |
| 1885 | closed | untriaged | chore(auto-retro): review PR #1883 repair loops |
| 1879 | open | untriaged | chore(auto-retro): review PR #1877 repair loops |
| 1865 | closed | untriaged | chore(auto-retro): review PR #1864 repair loops |
