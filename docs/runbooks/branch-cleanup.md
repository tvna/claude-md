# Branch cleanup; runbook

Operator-facing companion to the `branch-cleanup` job in [`.github/workflows/weekly-maintenance.yml`](../../.github/workflows/weekly-maintenance.yml). Tracking issue: [#31](https://github.com/tvna/claude-md/issues/31). Parent: [#18](https://github.com/tvna/claude-md/issues/18) Phase 4-B.

## Overview

`.github/rulesets/all-branches.json` (applied via Phase 2-A, [#27](https://github.com/tvna/claude-md/issues/27) / PR [#59](https://github.com/tvna/claude-md/pull/59)) intentionally omits a deletion rule and excludes `~DEFAULT_BRANCH` from its scope, so non-default branches auto-delete on PR merge ([repo setting `delete_branch_on_merge: true`](https://github.com/tvna/claude-md/issues/27)). Branches that never get a PR (abandoned `claude/**`, agent-interrupted in-flight branches) accumulate. This workflow surveys those branches weekly and reports candidates for cleanup.

## Current phase: dry-run only

This workflow ships in **survey-and-report-only** form. It has:

- `permissions: contents: read`; cannot delete branches even if mis-dispatched.
- No `gh api DELETE /git/refs/heads/...` call anywhere in the YAML.
- Default `dry_run: true` (the input is a placeholder; flipping it does nothing in this PR).

Flipping to actual deletion is tracked as **Goal D of [#31](https://github.com/tvna/claude-md/issues/31)** (live tracker: [#375](https://github.com/tvna/claude-md/issues/375)) and requires a separate PR that:

1. Widens permissions to `contents: write`.
2. Adds the gated `DELETE` call behind `if [ "$INPUT_DRY_RUN" = "false" ]`.
3. Flips the input default to `false` (or leaves it `true` and requires explicit opt-in per dispatch).

The `Guard dispatch ref` step (rejects `workflow_dispatch` runs from non-`main` refs) is pre-landed as of [#375](https://github.com/tvna/claude-md/issues/375), matching the pattern in `apply-rulesets.yml` / `apply-labels.yml`. The Goal D PR does not need to add it.

Per [#31](https://github.com/tvna/claude-md/issues/31), the deletion path lands only **after 2 weeks of dry-run observation** confirm the candidate list is correct.

## Schedule

```
cron: "0 20 * * 0"
```

= 20:00 UTC every Sunday = **05:00 JST Monday**. Weekly maintenance tasks share this trigger.

Also dispatchable on demand via **Actions -> Weekly maintenance -> Run workflow** with `task=branch-cleanup`.

## Selection criteria

A branch qualifies as a deletion candidate iff **all** of the following hold:

1. `name != default_branch` (resolved at run time from `GET /repos/{owner}/{repo}` `.default_branch`).
2. No open PR with the branch as `head` (`gh pr list --head <branch> --state open` returns 0).
3. `now - last_commit_date > min_age_days` (default 60 days; committer timestamp from `GET /repos/{owner}/{repo}/commits/<sha>`).

## Dispatch inputs

| Input | Type | Default | Purpose |
|---|---|---|---|
| `branch_cleanup_dry_run` | boolean | `true` | Reserved. No effect in the current code path (no DELETE exists). Will gate deletion in the follow-up PR. |
| `branch_cleanup_min_age_days` | number | `60` | Override the age threshold. Use `branch_cleanup_min_age_days=0` to force every non-default branch into the candidate list (useful for verifying the survey logic from a PR branch). |

## Summary issue convention

The workflow maintains **at most one open rolling issue**, but creates and writes to it **only when there are candidates**. The steady state with zero stale branches is silent; no issue, no comments.

- **Title:** `[branch-cleanup] weekly summary log` (exact match).
- **Labels:** `layer:p3-harness`, `area:ci-ops`, `type:docs`.
- **Owner:** `github-actions[bot]` (created via `GITHUB_TOKEN`).
- **Lookup:** by exact title + `state: open`.

### Per-run behaviour

| Candidates | Open rolling issue exists | Action |
|---|---|---|
| 0 | no | Silent. `$GITHUB_STEP_SUMMARY` records proof-of-life only. |
| 0 | yes, idle < 28 days | Silent. `$GITHUB_STEP_SUMMARY` records proof-of-life only. |
| 0 | yes, idle ≥ 28 days | **Auto-close** with a final comment naming the run and the idle window. |
| > 0 | no | **Create** a new rolling issue with the candidate table as body. |
| > 0 | yes | **Append a comment** with the candidate table to the existing issue. |

"Idle" = seconds since the more recent of `issue.created_at` or the latest comment `created_at`. The 28-day threshold ≈ 4 consecutive empty weekly runs.

Each created issue / appended comment contains:

- Run metadata (trigger, run URL, dry_run state, min_age_days).
- A Markdown table of candidate branches.
- A footer with the candidate count and the dry-run disclaimer.

### Resetting the log

- **Automatic:** after 4 consecutive empty weeks the workflow closes the issue itself; the next non-empty survey opens a fresh one.
- **Manual:** close the rolling issue whenever. The next non-empty run opens a new one with a fresh history; if the next run is empty, nothing happens.

### Operator note: the rolling issue is **not** authoritative

`$GITHUB_STEP_SUMMARY` on every workflow run is the durable per-run audit trail (preserved in the Actions log retention window). The rolling issue is a convenience surface for "things needing a human eye". Empty weeks intentionally produce no issue activity.

## Rollback

GitHub retains deleted refs for **90 days**. To restore a branch deleted by a future deletion-mode run:

```sh
gh api \
  --method POST \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/tvna/claude-md/git/refs \
  -f ref="refs/heads/<branch-name>" \
  -f sha="<last_commit_sha_from_summary_comment>"
```

The summary comment records the last commit SHA in the `Last commit SHA` column precisely for this purpose. After the 90-day retention window, the ref is permanently gone.

## Required secrets

None. The workflow uses the default `GITHUB_TOKEN` because the only write it performs is issue creation/commenting; branch deletion (when added) is also writable by `GITHUB_TOKEN` against unprotected non-default branches under the current `all-branches.json` ruleset.

## References

- [#18](https://github.com/tvna/claude-md/issues/18); parent ruleset tracker (Phase 4-B = this workflow).
- [#31](https://github.com/tvna/claude-md/issues/31); tracking issue for this workflow.
- [`.github/rulesets/all-branches.json`](../../.github/rulesets/all-branches.json); confirms deletion is not blocked on non-default branches.
- [`docs/runbooks/rulesets.md`](./rulesets.md); sibling runbook this file's structure is patterned after.
