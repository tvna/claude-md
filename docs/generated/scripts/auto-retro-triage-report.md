# Auto-retro triage report

This file is generated from live GitHub retro-issue labels by `python3 scripts/auto_retro.py triage-report`. Do not edit it by hand. Unlike the per-script AST docs it is a non-deterministic snapshot of repository state, so it is refreshed on merge by the `post-merge.yml` workflow (which opens a pull request when the snapshot drifts) rather than as part of the deterministic generated docs.

Retros observed: **50**

Open untriaged: **13**

## Anomalies

None: no fired signal clears both the FP-rate and sample-size thresholds.

## Triage status

```mermaid
pie showData
    title Triage status
    "retro:tp" : 0
    "retro:fp" : 1
    "retro:fp-candidate" : 0
    "retro:tentative" : 0
    "unlabelled" : 49
```

## Signal occurrence and false-positive rates

| Signal | Fired | Fire rate | FP | FP rate | n | Anomaly |
| --- | --: | --: | --: | --: | --: | :-: |
| `inline_review_comments` | 32 | 0.64 | 0 | 0.00 | 32 |  |
| `fix_typed_title` | 17 | 0.34 | 0 | 0.00 | 17 |  |
| `multi_commit_pr` | 44 | 0.88 | 0 | 0.00 | 44 |  |

## False-positive rate trend

- All-time: 1.00 (n=1 triaged)
- Last 20 retros: 0.00 (n=0 triaged); n/a

## Recent retros

| # | State | Status | Title |
| --: | :-- | :-- | :-- |
| 1997 | open | untriaged | chore(auto-retro): review PR #1988 repair loops |
| 1990 | open | untriaged | chore(auto-retro): review PR #1980 repair loops |
| 1972 | open | untriaged | chore(auto-retro): review PR #1960 repair loops |
| 1964 | open | untriaged | chore(auto-retro): review PR #1961 repair loops |
| 1956 | open | untriaged | chore(auto-retro): review PR #1948 repair loops |
| 1951 | open | untriaged | chore(auto-retro): review PR #1949 repair loops |
| 1939 | closed | untriaged | chore(auto-retro): review PR #1933 repair loops |
| 1935 | open | untriaged | chore(auto-retro): review PR #1934 repair loops |
| 1929 | closed | untriaged | chore(auto-retro): review PR #1927 repair loops |
| 1917 | open | untriaged | chore(auto-retro): review PR #1909 repair loops |
