# GitHub Rulesets — Apply / Verify / Rollback Runbook

This document is the operator-facing companion to the JSON source of truth in `.github/rulesets/`. The JSON files describe the rules; this document describes how to push them to GitHub, verify them, and roll them back.

The rulesets are introduced incrementally per the phased rollout in [#18](https://github.com/tvna/claude-md/issues/18). The JSON files do not auto-apply — the **primary path** is the [`Apply rulesets`](../.github/workflows/apply-rulesets.yml) workflow ([#51](https://github.com/tvna/claude-md/issues/51)); a manual `gh api` fallback is preserved below each section as an escape hatch.

## SoT layout

| File | Target | Purpose |
|---|---|---|
| `.github/rulesets/main.json` | `~DEFAULT_BRANCH` | Strict `main` protection (PR-only, squash-only, required status check, linear history) |
| `.github/rulesets/all-branches.json` | `~ALL` except `~DEFAULT_BRANCH` | `non_fast_forward` only (deletion intentionally omitted; see [#18 comment 2](https://github.com/tvna/claude-md/issues/18#issuecomment-4482555311)) |
| `docs/rulesets.md` *(this file)* | — | Runbook |

## Phase mapping

The apply step is split across phases so that the strictest rule (`commit_message_pattern: #\d+`) is the very last to land and can be observed for 1 week before enforcing. After [#51](https://github.com/tvna/claude-md/issues/51) the apply is driven by the `Apply rulesets` workflow.

| Phase | File | Workflow dispatch inputs |
|---|---|---|
| **2-A** ([#27](https://github.com/tvna/claude-md/issues/27)) | `all-branches.json` | `ruleset=all-branches`, `dry_run=false`, `enable_auto_delete=true` |
| **3-A** ([#41](https://github.com/tvna/claude-md/issues/41)) | `main.json` (as-is, without `commit_message_pattern`) | `ruleset=main`, `dry_run=false`, `enable_auto_delete=false` |
| **3-B** ([#42](https://github.com/tvna/claude-md/issues/42)) | `main.json` (after adding `commit_message_pattern`) | `ruleset=main`, `dry_run=false`, `enable_auto_delete=false` (PUT path, ≥7 days after 3-A) |

Run with `dry_run=true` first for every phase to inspect the planned POST/PUT and the per-field diff in the job summary.

## Required secret: `RULESETS_PAT`

The workflow uses a fine-grained PAT stored as repo secret `RULESETS_PAT`.

| Property | Value |
|---|---|
| Type | Fine-grained personal access token |
| Resource owner | `tvna` |
| Repository access | Only `tvna/claude-md` |
| Repository permissions | **`Administration: Read and write`** (covers both `/repos/{owner}/{repo}/rulesets` and `PATCH /repos/{owner}/{repo}` for `delete_branch_on_merge`) |
| Expiry | Set to ≤90 days; renew via the same secret name before expiry |

**Rotation**: Record the PAT expiry in your calendar. When rotating, generate a new PAT first, update the `RULESETS_PAT` secret, then revoke the old token. Rotation does not require code changes; the workflow reads `${{ secrets.RULESETS_PAT }}` at dispatch time.

## Apply via workflow (primary)

1. Go to **Actions → Apply rulesets → Run workflow**.
2. Choose inputs per the [Phase mapping](#phase-mapping) row you intend to execute.
3. Run with `dry_run=true` first. The job summary prints:
   - For first-time apply: a "POST planned" row with no diff (no live ruleset exists yet).
   - For updates: a per-field unified diff of `name` / `target` / `enforcement` / `conditions` / `bypass_actors` / `rules`.
4. Re-run with `dry_run=false` once the diff matches your intent.
5. Record the returned ruleset id(s) (visible in the job summary's "Result id" column) in the PR body that closes the associated phase issue. The id is needed for future PUTs and for `DELETE` rollback.

The workflow performs deterministic safety checks before any state change:

- `RULESETS_PAT` presence
- `jq empty` JSON syntax check
- Admin role id reconciliation (`bypass_actors[0].actor_id` in JSON must match the live `admin` role id from `GET /repos/{owner}/{repo}/roles`)
- Name-collision check (`>1` existing ruleset with the same name → fail; never guess)

<details>
<summary>Manual fallback (only if the workflow is unavailable)</summary>

```sh
# First-time apply (POST)
gh api \
  --method POST \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/tvna/claude-md/rulesets \
  --input .github/rulesets/all-branches.json

gh api \
  --method POST \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/tvna/claude-md/rulesets \
  --input .github/rulesets/main.json
```

Each call returns the new ruleset id; record it in the PR body that authorizes the apply.

</details>

## Update (re-apply with PUT)

For Phase 3-B and any future SoT edit, run the `Apply rulesets` workflow with the target ruleset name. The workflow auto-detects an existing match (by `name` field) and switches to PUT.

<details>
<summary>Manual fallback (only if the workflow is unavailable)</summary>

```sh
# 1) List rulesets to find the id matching the ruleset name in the JSON
gh api /repos/tvna/claude-md/rulesets

# 2) PUT the updated JSON onto that id
gh api \
  --method PUT \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/tvna/claude-md/rulesets/<id> \
  --input .github/rulesets/main.json
```

</details>

## Prerequisite — retrieve bypass actor ids

The workflow's "Pre-check admin role id matches bypass_actors" step automates this; the manual recipe below is for ad-hoc inspection.

```sh
gh api /repos/tvna/claude-md/roles
```

If the returned `Admin` role has a different `id` than the `bypass_actors[].actor_id` field in the JSON, open a PR to update the JSON before re-running the workflow.

## Verify

After every apply or update:

```sh
gh api /repos/tvna/claude-md/rulesets/<id>
```

Confirm the response body's `rules`, `conditions`, `bypass_actors`, and `enforcement` fields equal the committed JSON. The workflow's "Plan and apply rulesets" step already does this diff under a `<details>` block in the job summary for any PUT path.

Smoke tests for the live behaviour (from [#18 §Verification](https://github.com/tvna/claude-md/issues/18)):

1. From a clean clone with a non-bypass account, `git push origin main` is rejected.
2. `git push --force origin <any-branch>` is rejected.
3. A PR whose squash commit subject lacks `#\d+` is blocked at merge (after Phase 3-B).
4. A PR where `Verify agent instructions / gate` is failing is blocked at merge (after Phase 3-A).
5. The PR merge UI exposes only the "Squash and merge" button.

## Rollback

```sh
gh api \
  --method DELETE \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/tvna/claude-md/rulesets/<id>
```

Deleting a ruleset is non-destructive — the JSON file in git remains, and re-running the `Apply rulesets` workflow restores the previous state byte-for-byte (the workflow takes the POST path again once the live id is gone).

## Drift detection

A scheduled workflow that diffs the live rulesets returned by `gh api` against the committed JSON files is planned as `.github/workflows/ruleset-drift.yml` (Phase 4-A, [#30](https://github.com/tvna/claude-md/issues/30)). Until it lands, drift is detected only by:

- Manual review during retrospectives
- Running the `Apply rulesets` workflow with `dry_run=true` ad-hoc and inspecting the diff section in the job summary
