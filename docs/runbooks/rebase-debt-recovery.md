# Rebase debt recovery — runbook

Operator-facing companion to [`scripts/preflight_pr_no_merge_commits.py`](../../scripts/preflight_pr_no_merge_commits.py) and the CI step `Validate no merge-from-main commits` inside [`.github/workflows/verify-github-content.yml`](../../.github/workflows/verify-github-content.yml). Tracking issue: [#491](https://github.com/tvna/claude-md/issues/491).

## When this runbook fires

The deterministic gate prints an annotation that looks like:

```
::error::PR has N merge commit(s), expected 0 (base: origin/main)
Merge commits ahead of base:
  - <sha> [merge-from-main] Merge branch 'main' into ...
Recovery: rebase onto origin/main and force-with-lease. See docs/runbooks/rebase-debt-recovery.md.
See Issue #491 for the no-merge-commits contract.
```

Two structural rules fire the gate:

1. **`[merge-from-main]`** — commit subject starts with `Merge branch 'main'`, `Merge remote-tracking branch 'origin/main'`, or the `master` variants. These appear when a branch was synced via `git merge` instead of `git rebase`.
2. **`[merge]`** — commit has parent count > 1 (any other merge commit, e.g. `Merge pull request #99 ...`). The squash merge policy in `.github/rulesets/main.json` flattens these at merge time, but the diff and review history still carry the noise until then.

## Canonical recovery (rebase + force-with-lease)

This is the approved procedure. It preserves the PR's review state, CI history, and inline comments.

```bash
# 1. Fetch the latest base.
git fetch origin main

# 2. Replay your branch on top of origin/main, dropping the merge commit.
#    Interactive rebase lets you inspect each commit; the merge commit
#    appears as a `merge` line that you delete (or skip) to drop it.
git rebase -i origin/main

# 3. Push with --force-with-lease. The lease guards against overwriting
#    work pushed by someone else after your last fetch.
git push --force-with-lease
```

If the gate also annotated `[merge-from-main]` rows, the rebase will automatically replay each non-merge commit onto the new base and the merge-from-main commits drop out — no manual conflict resolution is needed beyond what `git rebase` would already prompt for.

### Single-command variant via `gh`

When the branch has no local edits beyond what is already pushed:

```bash
gh pr update-branch --rebase <pr-number>
```

GitHub performs the rebase server-side and force-updates the head ref. Use this only when you are confident the branch's local copy is identical to the remote, since `update-branch --rebase` resets your local view on the next `git fetch`.

## Why not close-and-reopen?

Closing the PR and opening a new one is **not** the recommended path because it:

- discards inline review comments and the resolved/unresolved thread state;
- breaks the link between linked issue, retro issue, and the original PR number;
- forces CI to rebuild caches from scratch on the new PR head.

Reserve close-and-reopen for cases where the rebase produces an unsolvable conflict tree (rare; ask in the issue thread before going this route).

## Why rebase rather than merge in the first place

`.github/rulesets/main.json` enforces both `required_linear_history: true` and `allowed_merge_methods: ["squash"]`. The squash merge absorbs intermediate merge commits at merge time, so the protection rules never trip — but the PR diff carries the noise until then. `scripts/auto_retro.py` flagged this pattern in 22 of 23 open retrospective issues (~95%), which is what Issue #491 set out to eliminate.

The deterministic gate enforces the rebase-only contract at PR push time so the repair never reaches the retro table.

## Related references

- Tracking issue: [#491](https://github.com/tvna/claude-md/issues/491)
- Sibling preflight (single-commit contract): [`scripts/preflight_pr_single_commit.py`](../../scripts/preflight_pr_single_commit.py), Issue [#492](https://github.com/tvna/claude-md/issues/492)
- Detection logic in retro reporter: `scripts/auto_retro.py` `_MERGE_FROM_MAIN_PREFIXES` and `_count_merge_from_main`
- Ruleset source of truth: [`.github/rulesets/main.json`](../../.github/rulesets/main.json)
