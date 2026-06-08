# Auto-retro triage report

This file is generated from live GitHub retro-issue labels by `python3 scripts/auto_retro.py triage-report`. Do not edit it by hand. Unlike the decision-tree doc it is a non-deterministic snapshot of repository state, so it is refreshed on merge by the `post-merge.yml` workflow (which opens a pull request when the snapshot drifts) rather than the `generate-docs.yml` drift gate.

Retros observed: **50**

Open untriaged: **3**

## Anomalies

Signals whose prior FP rate is at or above 0.50 (n >= 5); these signals now suppress new retros via `should_skip_by_prior`:

- `fix_typed_title`: FP rate 0.64 (n=11)
- `multi_commit_pr`: FP rate 0.56 (n=16)

## Triage status

```mermaid
pie showData
    title Triage status
    "retro:tp" : 10
    "retro:fp" : 37
    "retro:fp-candidate" : 0
    "retro:tentative" : 0
    "unlabelled" : 3
```

## Signal occurrence and false-positive rates

| Signal | Fired | Fire rate | FP | FP rate | n | Anomaly |
| --- | --: | --: | --: | --: | --: | :-: |
| `inline_review_comments` | 0 | 0.00 | 0 | 0.00 | 0 |  |
| `fix_typed_title` | 11 | 0.22 | 7 | 0.64 | 11 | !! |
| `multi_commit_pr` | 16 | 0.32 | 9 | 0.56 | 16 | !! |

## False-positive rate trend

- All-time: 0.79 (n=47 triaged)
- Last 20 retros: 0.82 (n=17 triaged) -- rising

## Recent retros

| # | State | Status | Title |
| --: | :-- | :-- | :-- |
| 1482 | open | untriaged | chore(auto-retro): review PR #1480 repair loops |
| 1479 | open | untriaged | chore(auto-retro): review PR #1474 repair loops |
| 1470 | open | untriaged | chore(auto-retro): review PR #1469 repair loops |
| 1465 | closed | retro:fp | chore(auto-retro): review PR #1464 repair loops |
| 1459 | closed | retro:fp | chore(auto-retro): review PR #1457 repair loops |
| 1445 | closed | retro:tp | chore(auto-retro): review PR #1444 repair loops |
| 1426 | closed | retro:fp | chore(auto-retro): review PR #1425 repair loops |
| 1423 | closed | retro:fp | chore(auto-retro): review PR #1421 repair loops |
| 1419 | closed | retro:fp | chore(auto-retro): review PR #1417 repair loops |
| 1415 | closed | retro:fp | chore(auto-retro): review PR #1409 repair loops |
