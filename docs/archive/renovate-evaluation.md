# Renovate as Dependabot Replacement -- Evaluation and Migration Sketch

> **Status: DECLINED (2026-05-31, [#1014](https://github.com/tvna/claude-md/issues/1014)).** The Renovate migration path evaluated here (the #276 / #279 cutover) was **not** adopted. The #273 rebase gap was instead closed by deleting the dedicated `non_fast_forward` ruleset on `refs/heads/dependabot/*` (mirroring the `refs/heads/claude/*` treatment) so `@dependabot rebase` force-pushes in place again, plus a deterministic author-verification gate (`scripts/verify_dependabot_author.py`) that fails any `dependabot/*` PR whose author is not a trusted bot login. That fix restores in-place rebase without adopting a third-party dependency bot, expanding write scope (Renovate's `Workflows: write`, Q4), or depending on the still-unconfirmed Q1 (whether the Mend Renovate Installation actor is accepted by the Rulesets API). This document is retained as the record of the evaluation; the sub-issue chain #280-#284 is superseded.

Parent issue: [#276](https://github.com/tvna/claude-md/issues/276)
Gap tracker: [#273](https://github.com/tvna/claude-md/issues/273)
PoC evidence: [docs/archive/renovate-poc-279.md](renovate-poc-279.md) ([#279](https://github.com/tvna/claude-md/issues/279))

## Scope

This document is the deliverable for issue #276: a documented evaluation of whether switching dependency update automation from Dependabot to Mend Renovate (SaaS) restores in-place rebase under `non_fast_forward` enforcement on update branches, plus the one-shot cutover migration sketch and a bounded list of open questions with their current status.

## Background -- why the evaluation was opened

### Fact 1 -- Dependabot Integration bypass was granted, then removed

PR [#140](https://github.com/tvna/claude-md/pull/140) added `actor_id: 49699333` (Dependabot Integration) to `bypass_actors` in `.github/rulesets/dependabot.json` so that `@dependabot rebase` could force-push under the `non_fast_forward` rule.

On 2026-05-24 GitHub deprecated the standalone Dependabot GitHub App. The Rulesets API began returning HTTP 422 for that bypass actor; PR [#274](https://github.com/tvna/claude-md/pull/274) removed the bypass. Today only `bypass_actors: []` remains, as seen in `.github/rulesets/dependabot.json` lines 11-14 (post-PR-#454 state).

Evidence: `.github/rulesets/dependabot.json` (current SoT), `docs/runbooks/rulesets.md` line 13, PR #273, PR #274, PR #454.

### Fact 2 -- rebase is broken, gap tracked

`@dependabot rebase` is now blocked by `non_fast_forward` on `refs/heads/dependabot/*`. Dependabot falls back to closing and reopening the PR with a freshly created branch. This gap is tracked by [#273](https://github.com/tvna/claude-md/issues/273) and recorded in:

- `docs/runbooks/rulesets.md` line 13 (SoT layout table, `dependabot.json` row).
- `docs/prd/security-control-inventory.md` line 70 (`dependabot.json` row, status `partially covered`, gap #273).

### Fact 3 -- Mend Renovate is a third-party GitHub App

Mend Renovate is unaffected by the first-party integration consolidation that retired the standalone Dependabot GitHub App. Its Installation actor should be registrable in `bypass_actors` through the normal `actor_type: "Integration"` path, which would restore in-place rebase under the existing ruleset shape.

Status: **speculation** (confirmed plausible by GitHub API docs that list `Integration` as a valid `actor_type` enum value for `bypass_actors`, but not yet validated by a live API call with the Mend Renovate Installation `actor_id`).

## Open questions -- status

Each question was enumerated in issue #276. Primary-source evidence is recorded in `docs/archive/renovate-poc-279.md` (PR [#390](https://github.com/tvna/claude-md/pull/390)).

| ID | Question | Status | Evidence |
|---|---|---|---|
| Q1 | Can the Mend Renovate App Installation actor be registered in `bypass_actors` with `actor_type: "Integration"`, and how is its `actor_id` obtained? | **pending human follow-up** | Requires Mend Renovate App install (web-only flow). `GET /repos/{owner}/{repo}/installations` returns the Installation `actor_id` once installed. The Rulesets API documents `Integration` as a valid `actor_type` enum. See `docs/archive/renovate-poc-279.md` Q1 and human follow-up checklist. |
| Q2 | Does Renovate's `pep621` manager update `uv.lock` directly, or does `lockFileMaintenance` need to be configured? | **answered** | The `pep621` manager supports `uv` including `uv.lock` files and `uv` workspaces natively. No `lockFileMaintenance` needed. Source: `renovatebot/renovate` `lib/modules/manager/pep621/readme.md` (fetched 2026-05-25). |
| Q3 | Does the Renovate rebase action require force-push under `non_fast_forward`, or does Renovate have a close-and-reopen fallback? | **answered (with caveat)** | Renovate rebases via force-push. No close-and-reopen fallback is documented. Implication: `non_fast_forward` on `renovate/*` blocks rebase unless the Mend App Installation actor is in `bypass_actors`. Source: `renovatebot/renovate` `docs/usage/configuration-options.md` lines 754, 1972, 4482-4504 (fetched 2026-05-25). |
| Q4 | What permissions does the Mend Renovate App request at install, and do they stay within least-privilege expectations? | **answered** | Nine global permissions; six with write scope (Checks, Code, Commit statuses, Issues, Pull Requests, Workflows). Notable new scope vs Dependabot: `Workflows: write` (required for updating pinned-Action SHAs in workflow files). Source: `renovatebot/renovate` `docs/usage/security-and-permissions.md` lines 33-44 (fetched 2026-05-25). |

### Q1 human follow-up steps (reproduced from PoC doc)

1. Install the Mend Renovate App on `tvna/claude-md` from `https://github.com/apps/renovate`.
2. Run `gh api /repos/tvna/claude-md/installations` and record the entry whose `app_slug` is `renovate`. The `target_id` is the Installation actor id.
3. Dispatch `Apply rulesets` with `dry_run=true` using a candidate `renovate.json` that references the captured `actor_id` with `actor_type: "Integration"`. The API response confirms whether the Rulesets API accepts or rejects the third-party App Installation bypass.

## Evaluation conclusion

### Recommendation: proceed with cutover

Based on the evidence gathered (Q2-Q4 answered, Q1 plausible), the evaluation recommends proceeding with the one-shot cutover migration from Dependabot to Mend Renovate, contingent on Q1 confirmation. The rationale:

1. **Rebase restoration**: Renovate's rebase is force-push (Q3). If the Mend Renovate App Installation actor can be registered in `bypass_actors` (Q1), in-place rebase on `renovate/*` branches is restored -- closing the #273 gap that Dependabot's close-and-reopen fallback cannot address.
2. **uv.lock native support**: Renovate's `pep621` manager natively handles `uv.lock` (Q2), matching Dependabot's `uv` ecosystem support.
3. **Permission scope acceptable**: The `Workflows: write` scope (Q4) is required for the same Action-SHA-bump workflow that Dependabot performs today via its GitHub-managed permissions. An explicit acceptance decision for `Workflows: write` should be recorded in the cutover PR.
4. **Cooldown parity**: Renovate's `minimumReleaseAge` maps to Dependabot's `cooldown` settings (7d default, 30d major, 7d minor, 3d patch).

### Contingency: Q1 rejection

If the Rulesets API rejects the Mend Renovate App Installation `actor_id` (reproducing the HTTP 422 that retired the Dependabot bypass), the decision reverts to Shape A (`bypass_actors: []`) and the rebase gap persists under Renovate as it does under Dependabot. In that scenario, the cutover still has value for `pep621` native `uv.lock` support and config-as-code via `renovate.json5`, but the #273 gap remains open.

## One-shot cutover migration sketch

No parallel run with Dependabot. The sub-issues are already opened under #276.

### Phase 1 -- PoC ([#279](https://github.com/tvna/claude-md/issues/279))

Install Mend Renovate App and answer Q1 with primary-source evidence. Documentary evidence for Q2-Q4 is captured in `docs/archive/renovate-poc-279.md` (PR #390, merged).

### Phase 2 -- introduce config and switch ruleset target ([#280](https://github.com/tvna/claude-md/issues/280))

Blocked by #279.

| Surface | Action |
|---|---|
| `.github/renovate.json5` | **New file.** `extends: ["config:recommended"]`, weekly Monday schedule, `dependencies` label, `chore` commit prefix, `packageRules` with `minimumReleaseAge` mapping: 7d default, 30d major, 7d minor, 3d patch. |
| `.github/rulesets/dependabot.json` | **Rename** to `renovate.json`. Switch `ref_name.include` from `refs/heads/dependabot/*` to `refs/heads/renovate/*`. Add Renovate Installation actor to `bypass_actors` if Q1 is confirmed (Shape B from PoC doc); otherwise keep `bypass_actors: []` (Shape A). |
| `.github/rulesets/all-branches.json` | **Update** `exclude` entry from `refs/heads/dependabot/*` to `refs/heads/renovate/*`. |
| `scripts/rulesets_apply.py` | **Update** `TARGETS` map: rename key `"dependabot"` to `"renovate"`, update filename from `"dependabot.json"` to `"renovate.json"`. Update `"all"` list entry. |
| `scripts/ruleset_drift.py` | **Update** `DEFAULT_SOT_FILES`: replace `"dependabot.json"` with `"renovate.json"`. |
| `.github/workflows/apply-rulesets.yml` | **Update** workflow input choices: replace `dependabot` with `renovate` in the selector enum. |

### Phase 3 -- retarget auto-merge ([#281](https://github.com/tvna/claude-md/issues/281))

Blocked by #280.

| Surface | Action |
|---|---|
| `.github/dependabot-automerge.json` | **Rename** to `.github/renovate-automerge.json`. No content change. |
| `.github/workflows/dependabot-automerge.yml` | **Rename** to `.github/workflows/renovate-automerge.yml`. Retarget `if:` condition from `dependabot[bot]` to `renovate[bot]`. Update concurrency group prefix. |
| `scripts/dependabot_automerge.py` | **Rename** to `scripts/renovate_automerge.py`. Update `_TRUSTED_BOT_LOGINS` import usage to check `renovate[bot]`. Update branch prefix check from `dependabot/` to `renovate/`. |
| `tests/test_dependabot_automerge.py` | **Rename** to `tests/test_renovate_automerge.py`. Update fixture data and imports. |
| `scripts/_trusted_bots.py` | **No rename.** Update `_DEFAULT_GENERAL` fallback from `dependabot[bot]` to `renovate[bot]`. |
| `.github/trusted_bots.toml` | **Update** `[general].logins` from `dependabot[bot]` to `renovate[bot]`. |

### Phase 4 -- cutover ([#282](https://github.com/tvna/claude-md/issues/282))

Blocked by #280 and #281.

| Surface | Action |
|---|---|
| `.github/dependabot.yml` | **Delete.** |
| `.github/workflows/verify-dependabot-labels.yml` | **Delete.** Renovate carries its own JSON config; label verification is Dependabot-specific. |
| `scripts/dependabot_labels.py` | **Delete.** |
| `tests/test_dependabot_labels.py` | **Delete.** |

### Phase 5 -- docs rewrite ([#283](https://github.com/tvna/claude-md/issues/283))

Blocked by #282.

| Surface | Action |
|---|---|
| `docs/runbooks/dependabot-automerge.md` | **Rename** to `docs/runbooks/renovate-automerge.md`. Rewrite to reference `renovate[bot]`, `renovate/*`, `renovate-automerge.json`. |
| `docs/prd/security-control-inventory.md` | **Rewrite** rows referencing Dependabot surfaces: `dependabot-automerge.yml` (line 48), `verify-dependabot-labels.yml` (line 56), `dependabot.json` ruleset (line 70), `.github/dependabot.yml` (line 97), `dependabot_automerge.py` (line 124), `dependabot_labels.py` (line 125), `docs/runbooks/dependabot-automerge.md` (line 145). |
| `docs/runbooks/rulesets.md` | **Update** line 13 footnote: replace Dependabot references with Renovate equivalents. Update SoT layout table row for the renamed ruleset. |
| `docs/standards/remote-environment.md` | **Update** line 19 and line 125: replace `.github/dependabot.yml` references with `.github/renovate.json5`. Update line 125 Renovate mention from future possibility to current state. |
| `docs/INDEX.md` | **Update** `dependabot-automerge.md` row to `renovate-automerge.md`. Remove `verify-dependabot-labels.yml` generated workflow diagram row if applicable. |
| `docs/standards/dependency-freshness.md` | **Update** Dependabot references to Renovate equivalents. |

### Phase 6 -- retrospective ([#284](https://github.com/tvna/claude-md/issues/284))

Blocked by #282 merge. Pre-opened per CLAUDE.md section 3 so post-merge repair-free review is a deterministic gate. Issue #276 closes only after #284 closes.

## Decision gate

The decision on whether to open the implementation PR or close issue #276 as `not_planned` is recorded as the final comment on issue #276 once all open questions are resolved. As of this document:

- Q2, Q3, Q4: resolved with primary-source evidence.
- Q1: pending human follow-up (Mend Renovate App installation is a web-only flow).
- Recommendation: **proceed** (contingent on Q1 confirmation).

Once Q1 is confirmed, the sub-issue chain (#280 through #284) unblocks and the cutover proceeds in the phased order documented above.
