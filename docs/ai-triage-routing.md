# AI Agent Triage Routing — Apply / Verify / Rollback Runbook

This document is the operator-facing runbook for the `agent:*` label set that gates AI agent involvement on every issue. The labels themselves are the deterministic routing signal; this document describes how to push them to GitHub, verify them, and roll them back.

The label taxonomy is introduced incrementally per the phased rollout in [#34](https://github.com/tvna/claude-md/issues/34). The JSON SoT lives at `.github/labels.json`; the values in the Apply section below MUST match it byte-for-byte. Per [CLAUDE.md §3](../blob/main/CLAUDE.md), agents must be concentrated at one workflow point *after* deterministic gates pass — the `agent:*` label is that gate, and per §5 it exists to avoid wasting tokens on issues the agent should not read in full.

## SoT layout

| File | Target | Purpose |
|---|---|---|
| `.github/labels.json` | `/repos/tvna/claude-md/labels` | JSON source of truth for the `agent:*` labels |
| `docs/ai-triage-routing.md` *(this file)* | — | Runbook |

## Label taxonomy

Default for every newly opened issue is `agent:triage-needed`. Exactly one `agent:*` label must be applied to each issue.

| Label | 意味 | Agent action | 全文読みの要否 |
|---|---|---|---|
| `agent:auto-fix` | 機械的に対処可能 (typo, dependency bump, format 等) | autonomous に PR を起票 | 必要 |
| `agent:investigate` | 調査・設計判断要 (新機能設計, bug 原因調査) | 探索 + plan 提案、実装は人承認後 | 必要 |
| `agent:no-action` | 人間判断専用 (governance 決定, parked, discussion) | 関与しない | 不要 (title のみ確認) |
| `agent:triage-needed` | 未分類 (新規 issue 既定値) | title だけ読んで上記いずれかへ再分類 | 不要 |

## Apply (first-time `POST`)

Apply one label at a time. Each call returns the created label object; labels are addressed by name (no id is required for later updates). The `-f color=` / `-f description=` values below are byte-for-byte mirrors of `.github/labels.json` — if either side changes, update both in the same PR.

```sh
gh api \
  --method POST \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/tvna/claude-md/labels \
  -f name='agent:auto-fix' \
  -f color='0e8a16' \
  -f description='Machine-actionable. Agent may open a PR autonomously.'

gh api \
  --method POST \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/tvna/claude-md/labels \
  -f name='agent:investigate' \
  -f color='fbca04' \
  -f description='Requires investigation. Agent proposes a plan; implementation awaits approval.'

gh api \
  --method POST \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/tvna/claude-md/labels \
  -f name='agent:no-action' \
  -f color='b60205' \
  -f description='Human judgment only. Agent does not engage.'

gh api \
  --method POST \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/tvna/claude-md/labels \
  -f name='agent:triage-needed' \
  -f color='bfdadc' \
  -f description='Uncategorized (default for new issues). Re-classify by title.'
```

## Update (re-apply with `PATCH`)

Use the update path when fixing drift detected by Phase 4 or when adjusting colour / description. Labels are addressed by their current name; pass `-f new_name=` to rename.

```sh
gh api \
  --method PATCH \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/tvna/claude-md/labels/agent:auto-fix \
  -f color='0e8a16' \
  -f description='Machine-actionable. Agent may open a PR autonomously.'
```

## Verify

After every apply or update:

```sh
gh api /repos/tvna/claude-md/labels --jq '.[] | select(.name | startswith("agent:")) | .name'
```

The response must list exactly 4 names: `agent:auto-fix`, `agent:investigate`, `agent:no-action`, `agent:triage-needed`. For each one, confirm the `color` and `description` fields returned by `gh api /repos/tvna/claude-md/labels/<name>` equal the values passed to the Apply step.

## Rollback

```sh
gh api \
  --method DELETE \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/tvna/claude-md/labels/<name>
```

Note: unlike ruleset deletion (`docs/rulesets.md` § Rollback), deleting a label is **destructive on existing issues** — GitHub removes the label from every issue and PR it was applied to. Re-`POST`ing the same label restores its definition but does **not** restore the per-issue assignments; those must be re-applied manually (Phase 3 will be the operation log for that).

## Drift detection

A scheduled workflow that diffs the live labels returned by `gh api` against the committed `.github/labels.json` is planned as Phase 4 of [#34](https://github.com/tvna/claude-md/issues/34) (parked). Until it lands, drift is detected only by manual review during retrospectives.
