# GitHub Rulesets — Apply / Verify / Rollback Runbook

This document is the operator-facing companion to the JSON source of truth in `.github/rulesets/`. The JSON files describe the rules; this document describes how to push them to GitHub, verify them, and roll them back.

The rulesets are introduced incrementally per the phased rollout in [#18](https://github.com/tvna/claude-md/issues/18). The JSON files do not auto-apply — running `gh api` against `/repos/tvna/claude-md/rulesets` is what makes them live.

## SoT layout

| File | Target | Purpose |
|---|---|---|
| `.github/rulesets/main.json` | `~DEFAULT_BRANCH` | Strict `main` protection (PR-only, squash-only, required status check, linear history) |
| `.github/rulesets/all-branches.json` | `~ALL` except `~DEFAULT_BRANCH` | `non_fast_forward` only (deletion intentionally omitted; see [#18 comment 2](https://github.com/tvna/claude-md/issues/18#issuecomment-4482555311)) |
| `docs/rulesets.md` *(this file)* | — | Runbook |

## Phase mapping

The `gh api` apply step is split across phases so that the strictest rule (`commit_message_pattern: #\d+`) is the very last to land and can be observed for 1 week before enforcing.

| Phase | File | Action |
|---|---|---|
| **2-A** | `all-branches.json` | First-time `POST` apply. Also enable GitHub repo setting *Automatically delete head branches*. |
| **3-A** | `main.json` (as-is, without `commit_message_pattern`) | First-time `POST` apply. The `Verify agent instructions / gate` check must be passing on `main` before applying. |
| **3-B** | `main.json` (after adding `commit_message_pattern`) | Edit `main.json` to add the `commit_message_pattern: #\d+` rule, then `PUT` to update the existing ruleset id. Wait at least 1 week after Phase 3-A. |

## Prerequisite — retrieve bypass actor ids

The JSON files declare a bypass entry with `actor_type: RepositoryRole` and `actor_id: 5` (the GitHub default id for the `Admin` role). Confirm the id for this repository before applying:

```sh
gh api /repos/tvna/claude-md/roles
```

If the returned `Admin` role has a different `id`, edit the `bypass_actors[].actor_id` field in the JSON file and commit the change in a follow-up PR before applying.

## Apply (first-time `POST`)

Apply one ruleset at a time. Each call returns the new ruleset id — record it in the PR body that authorizes the apply.

```sh
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

## Update (re-apply with `PUT`)

Use the update path when fixing drift detected by Phase 4-A or when adding a new rule (Phase 3-B):

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

## Verify

After every apply or update:

```sh
gh api /repos/tvna/claude-md/rulesets/<id>
```

Confirm the response body's `rules`, `conditions`, `bypass_actors`, and `enforcement` fields equal the committed JSON.

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

Deleting a ruleset is non-destructive — the JSON file in git remains, and a re-`POST` of the same file restores the previous state byte-for-byte.

## Drift detection

A scheduled workflow that diffs the live rulesets returned by `gh api` against the committed JSON files is planned as `.github/workflows/ruleset-drift.yml` (Phase 4-A, [#18 rollout](https://github.com/tvna/claude-md/issues/18#issuecomment-4482593584)). Until it lands, drift is detected only by manual review during retrospectives.
