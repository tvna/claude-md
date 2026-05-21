# Branch cleanup — runbook

Operator-facing companion to [`.github/workflows/branch-cleanup.yml`](../.github/workflows/branch-cleanup.yml). Tracking issue: [#31](https://github.com/tvna/claude-md/issues/31). Parent: [#18](https://github.com/tvna/claude-md/issues/18) Phase 4-B.

## Overview

`.github/rulesets/all-branches.json` (applied via Phase 2-A, [#27](https://github.com/tvna/claude-md/issues/27) / PR [#59](https://github.com/tvna/claude-md/pull/59)) intentionally omits a deletion rule and excludes `~DEFAULT_BRANCH` from its scope, so non-default branches auto-delete on PR merge ([repo setting `delete_branch_on_merge: true`](https://github.com/tvna/claude-md/issues/27)). Branches that never get a PR (abandoned `claude/**`, agent-interrupted in-flight branches) accumulate. This workflow surveys those branches weekly and reports candidates for cleanup.

## Current phase: dry-run only

This workflow ships in **survey-and-report-only** form. It has:

- `permissions: contents: read` — cannot delete branches even if mis-dispatched.
- No `gh api DELETE /git/refs/heads/...` call anywhere in the YAML.
- Default `dry_run: true` (the input is a placeholder; flipping it does nothing in this PR).

Flipping to actual deletion is tracked as **Goal D of [#31](https://github.com/tvna/claude-md/issues/31)** and requires a separate PR that:

1. Widens permissions to `contents: write`.
2. Adds the gated `DELETE` call behind `if [ "$INPUT_DRY_RUN" = "false" ]`.
3. Flips the input default to `false` (or leaves it `true` and requires explicit opt-in per dispatch).

Per [#31](https://github.com/tvna/claude-md/issues/31), the deletion path lands only **after 2 weeks of dry-run observation** confirm the candidate list is correct.

## Schedule

```
cron: "0 20 * * 0"
```

= 20:00 UTC every Sunday = **05:00 JST Monday**. Offset from `generate-agents.yml` (`0 18 * * 6` = 03:00 JST Sun) to avoid contention.

Also dispatchable on demand via **Actions → Branch cleanup (dry-run) → Run workflow**.

## Selection criteria

A branch qualifies as a deletion candidate iff **all** of the following hold:

1. `name != default_branch` (resolved at run time from `GET /repos/{owner}/{repo}` `.default_branch`).
2. No open PR with the branch as `head` (`gh pr list --head <branch> --state open` returns 0).
3. `now - last_commit_date > min_age_days` (default 60 days; committer timestamp from `GET /repos/{owner}/{repo}/commits/<sha>`).

## Dispatch inputs

| Input | Type | Default | Purpose |
|---|---|---|---|
| `dry_run` | boolean | `true` | Reserved. No effect in the current code path (no DELETE exists). Will gate deletion in the follow-up PR. |
| `min_age_days` | number | `60` | Override the age threshold. Use `min_age_days=0` to force every non-default branch into the candidate list (useful for verifying the survey logic from a PR branch). |

## Summary issue convention

The workflow creates and maintains **one rolling issue**:

- **Title:** `[branch-cleanup] weekly summary log` (exact match).
- **Labels:** `layer:meta`, `type:docs`.
- **Owner:** `github-actions[bot]` (created via `GITHUB_TOKEN`).
- **Lookup:** by exact title + `state: open`. If found, the workflow appends a new comment; if not, it opens a new issue.

Each comment contains:

- Run metadata (trigger, run URL, dry_run state, min_age_days).
- A Markdown table of candidate branches (or a single `_(none)_` row if zero).
- A footer with the candidate count and the dry-run disclaimer.

### Resetting the log

If the rolling issue grows too long, **close it**. The next scheduled run will not find an open issue with the matching title and will open a fresh one.

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

- [#18](https://github.com/tvna/claude-md/issues/18) — parent ruleset tracker (Phase 4-B = this workflow).
- [#31](https://github.com/tvna/claude-md/issues/31) — tracking issue for this workflow.
- [`.github/rulesets/all-branches.json`](../.github/rulesets/all-branches.json) — confirms deletion is not blocked on non-default branches.
- [`docs/rulesets.md`](./rulesets.md) — sibling runbook this file's structure is patterned after.
