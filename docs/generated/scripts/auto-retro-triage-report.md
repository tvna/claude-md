# Auto-retro triage report

This file is generated from live GitHub retro-issue labels by `python3 scripts/auto_retro.py triage-report`. Do not edit it by hand. Unlike the per-script AST docs it is a non-deterministic snapshot of repository state, so it is refreshed on merge by the `post-merge.yml` workflow (which opens a pull request when the snapshot drifts) rather than as part of the deterministic generated docs.

Retros observed: **50**

Open untriaged: **12**

## Anomalies

None: no fired signal clears both the FP-rate and sample-size thresholds.

## Triage status

```mermaid
pie showData
    title Triage status
    "retro:tp" : 1
    "retro:fp" : 3
    "retro:fp-candidate" : 0
    "retro:tentative" : 0
    "unlabelled" : 46
```

## Signal occurrence and false-positive rates

| Signal | Fired | Fire rate | FP | FP rate | n | Anomaly |
| --- | --: | --: | --: | --: | --: | :-: |
| `inline_review_comments` | 31 | 0.62 | 0 | 0.00 | 31 |  |
| `fix_typed_title` | 18 | 0.36 | 1 | 0.06 | 18 |  |
| `multi_commit_pr` | 41 | 0.82 | 0 | 0.00 | 41 |  |

## False-positive rate trend

- All-time: 0.75 (n=4 triaged)
- Last 20 retros: 0.00 (n=0 triaged); n/a

## Recent retros

| # | State | Status | Title |
| --: | :-- | :-- | :-- |
| 1964 | open | untriaged | chore(auto-retro): review PR #1961 repair loops |
| 1956 | open | untriaged | chore(auto-retro): review PR #1948 repair loops |
| 1951 | open | untriaged | chore(auto-retro): review PR #1949 repair loops |
| 1939 | open | untriaged | chore(auto-retro): review PR #1933 repair loops |
| 1935 | open | untriaged | chore(auto-retro): review PR #1934 repair loops |
| 1929 | open | untriaged | chore(auto-retro): review PR #1927 repair loops |
| 1917 | open | untriaged | chore(auto-retro): review PR #1909 repair loops |
| 1910 | open | untriaged | chore(auto-retro): review PR #1908 repair loops |
| 1905 | open | untriaged | chore(auto-retro): review PR #1900 repair loops |
| 1894 | open | untriaged | chore(auto-retro): review PR #1891 repair loops |
