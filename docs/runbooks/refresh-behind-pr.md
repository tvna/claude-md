# Refresh a behind, conflict-free PR branch

When a feature branch falls behind its base (a sibling PR merged into
`main`), the PR becomes `mergeable_state=behind` and cannot merge under the
`strict_required_status_checks_policy` ruleset. This runbook is the
deterministic, agent-agnostic path for the *behind and conflict-free* case.

`scripts/refresh_pr_branch.py` implements it; this document is the operator
contract and the decision the helper encodes.

## Why the obvious recoveries are blocked

- **rebase + force-push** is denied by the `non_fast_forward` ruleset
  (`.github/rulesets/all-branches.json`, applied to every non-default branch
  with `bypass_actors: []`). See `docs/runbooks/rulesets.md`.
- **`mcp__github__update_pull_request_branch`** is denied by
  `scripts/gate_update_pr_branch.py`: the GitHub API performs a server-side
  *merge* (not a rebase) and the gate keeps that path closed.

## Why a local merge + plain push is allowed and correct

`git merge --no-edit origin/<base>` followed by a plain `git push` advances
the branch ref by a *fast-forward* (the new merge commit is a descendant of
the old tip), so the `non_fast_forward` ruleset is satisfied; no force is
involved. The extra merge commit is not a problem for clean linear history:
`main-protection` is squash-only, so the final squash-merge flattens the
branch to a single commit regardless. This is the same effect
`update_pull_request_branch` would produce, done locally so no gated API call
is needed.

## Decision

```
PR mergeable_state == behind ?
  |
  +-- conflict-free  -> scripts/refresh_pr_branch.py  (this runbook)
  |
  +-- conflicts (dirty) -> replacement branch
                           docs/runbooks/update-pr-branch-recovery.md
```

The helper checks for conflicts non-destructively with
`git merge-tree --write-tree` before it merges, and refuses (exit 2) when the
merge would conflict, pointing here at the replacement-branch runbook.

## Procedure

### Prerequisites

- You are on the PR's feature branch (not `main`) with a clean worktree.
- The remote is reachable (the helper runs `git fetch`).

### Steps

1. **From the PR branch, run the helper.**

   ```sh
   python3 scripts/refresh_pr_branch.py --push
   ```

   It fetches `origin/main`, confirms the branch is behind and conflict-free,
   merges `origin/main` in, and pushes (plain push; never `--force`).

2. **Preview first if you want to inspect the plan.**

   ```sh
   python3 scripts/refresh_pr_branch.py --dry-run
   ```

   Omit `--push` to merge locally and push yourself; omit `--no-fetch` only
   when `origin/<base>` is already current.

3. **On a conflict (exit code 2),** do not merge. Switch to the
   replacement-branch path in `docs/runbooks/update-pr-branch-recovery.md`.

## Exit codes

- `0`; already up to date, or merged (and pushed with `--push`) cleanly.
- `2`; the merge would conflict; use the replacement-branch runbook.
- `3`; precondition failed (dirty worktree, on the base branch, git error).

## Companion

- `scripts/refresh_pr_branch.py`; the deterministic helper.
- `scripts/check_pr_mergeability.py`; surfaces `behind` and points here.
- `docs/runbooks/update-pr-branch-recovery.md`; the conflict / replacement path.
- `docs/runbooks/merge-readiness-loop.md`; where this step sits in the loop.
- `docs/runbooks/rulesets.md`; the `non_fast_forward` rule rationale.
- Refs #1361, #893.
