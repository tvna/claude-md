# update_pull_request_branch recovery runbook

`mcp__github__update_pull_request_branch` is blocked by
`scripts/gate_update_pr_branch.py` (PreToolUse hook, Refs #893).

## Why it is blocked

The GitHub API for `update_pull_request_branch` performs a server-side
**merge** from the base branch into the feature branch -- not a rebase.
This adds a merge commit to the branch that the squash-only merge queue
would just flatten again (`main` is squash-only:
`allowed_merge_methods: ["squash"]`). Catching up with `main` this way is
also unnecessary: GitHub Merge Queue validates the up-to-date base state
at merge time (issue #895), so the feature branch does not need to absorb
`main` before merge.

## Recovery procedure

When the feature branch falls behind the base (e.g., after a sibling PR
merges into `main`), use the following steps instead of calling
`update_pull_request_branch`.

### Prerequisites

- The PR's original commit(s) are available in the local branch or
  can be identified via `git log`.
- You have `GH_TOKEN` set (for re-targeting the PR via `mcp__github__`
  tools if needed).

### Steps

1. **Fetch the latest base branch.**

   ```sh
   git fetch origin main
   ```

2. **Create a replacement branch from the current `origin/main` HEAD.**

   Use a name that is distinct from the old branch to avoid confusion:

   ```sh
   git checkout -b <issue-slug>-v2 origin/main
   ```

3. **Re-apply the PR change on top of `main`.**

   If the original commit is in a local branch `<old-branch>`:

   ```sh
   git cherry-pick <old-branch>
   ```

   Or apply the change directly and commit:

   ```sh
   # ... make changes ...
   git add <files>
   git commit -m "<original commit message>"
   ```

4. **Push the replacement branch.**

   ```sh
   git push -u origin <issue-slug>-v2
   ```

5. **Retarget or replace the open PR.**

   Close the stale PR and open a new one targeting `main` from
   `<issue-slug>-v2`, or update the existing PR's head branch via
   `mcp__github__update_pull_request`.

   When closing the stale PR, use `preflight_replacement_pr.py` to
   ensure the closure satisfies the replacement-PR gate:

   ```sh
   python3 scripts/preflight_replacement_pr.py --old-pr <N> --new-branch <issue-slug>-v2
   ```

## Companion

- `scripts/gate_update_pr_branch.py` -- PreToolUse hook that blocks the call
- `.github/rulesets/main.json` -- squash-only `allowed_merge_methods` and the `merge_queue` rule that make a catch-up merge unnecessary
- `docs/runbooks/replacement-pr-preflight.md` -- replacement-PR closure gate
- Refs #893, #895
