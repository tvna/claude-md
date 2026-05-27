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

## Why two preflights, not one

Two separate scripts gate PR shape against `origin/main`, and they intentionally stay separate:

| Script | Issue | Mechanism | Catches |
|---|---|---|---|
| `scripts/preflight_pr_single_commit.py` | [#492](https://github.com/tvna/claude-md/issues/492) | `git rev-list --no-merges {base}..HEAD --count == 1` | More than one author commit ahead of base. |
| `scripts/preflight_pr_no_merge_commits.py` | [#491](https://github.com/tvna/claude-md/issues/491) | Structural: any commit with parent count > 1 in `{base}..HEAD`. | Merge commits (rebase debt) the count gate hides. |

The single-commit gate uses `--no-merges` because rebase debt would otherwise inflate the count and obscure the more common failure: multiple author commits. The trade-off is that `--no-merges` silently drops merge commits, so the count gate **cannot** catch them. The structural gate (#491) closes that hole using parent count, not subject text, so even an unrecognized merge subject still fires it.

A future "DRY refactor" PR may be tempted to collapse the two scripts into a single helper — do not. Each gate fails on a distinct signal class:

- Collapsing into a single count check requires picking one of `--no-merges` (loses merge detection) or omitting it (count gate misfires on rebase debt). Neither path preserves both behaviors.
- The annotation messages encode different remediations: the count gate points at `git rebase -i {base}` (squash); the structural gate points at this runbook (rebase + force-with-lease). Folding them blurs the operator hint.
- The contract test for `_MERGE_FROM_MAIN_PREFIXES` lock-step (next section) assumes the structural gate exists as a discrete module; removing it would orphan the test.

If you genuinely want to reduce duplication, share `resolve_base()` via a small import — do not merge the gates themselves.

## Operator workflow for follow-up commits

The single-commit gate (#492) enforces exactly one author commit ahead of `origin/main` per branch. When CI feedback or review comments require follow-up work, use `git commit --amend` rather than adding a new commit:

```bash
# Stage the follow-up edit.
git add path/to/edited/file

# Amend the existing commit instead of creating a new one.
git commit --amend --no-edit

# Force push with lease so the upstream branch carries the same
# single commit, just with the new content.
git push --force-with-lease
```

`fixup!` and `squash!` commit subjects (the conventional autosquash markers from `git commit --fixup` / `--squash`) trip the single-commit gate at push time: they read as a second author commit ahead of base and fail the count check. Do not rely on the squash merge to flatten them later — the gate catches them earlier so the PR thread stays single-commit through review.

If the branch already carries multiple author commits (e.g. a legacy push that predates this gate, or a forgotten `--amend`), squash them locally before pushing:

```bash
git rebase -i origin/main   # mark every commit except the first as `squash`
git push --force-with-lease
```

## `_MERGE_FROM_MAIN_PREFIXES` lock-step rule

The constant `_MERGE_FROM_MAIN_PREFIXES` is defined in two places:

- [`scripts/preflight_pr_no_merge_commits.py`](../../scripts/preflight_pr_no_merge_commits.py) — used by the blocking gate's annotation to tag known merge-from-main subjects distinctly from "unknown merge" subjects.
- [`scripts/auto_retro.py`](../../scripts/auto_retro.py) — used by the retrospective Repair history table to classify rebase-debt rows as `[policy-artifact]` rather than as a repair loop.

The duplication is intentional. The two scripts have different runtime profiles (the gate runs on every PR push; the report runs after merge), and importing one from the other would couple a fast-path CI gate to the much larger retro reporter module. Keeping the constant copied in two places is cheaper than the cross-module import would be — but it requires a deterministic backstop so the two copies never drift.

**The rule.** The two tuples MUST contain the same prefixes as sets. Order does not matter; content does.

**The backstop.** [`tests/test_merge_from_main_prefixes_lockstep.py`](../../tests/test_merge_from_main_prefixes_lockstep.py) asserts `set(auto_retro._MERGE_FROM_MAIN_PREFIXES) == set(preflight_pr_no_merge_commits._MERGE_FROM_MAIN_PREFIXES)`. The failure message names the entries on each side so the diff is obvious on failure.

**Maintenance.** When adding a new prefix (e.g. for a future `trunk` convention), edit both tuples in the same PR. The contract test fires if you forget.

## Why `HEAD_REF` rather than `GITHUB_SHA` in the workflow

[`.github/workflows/verify-github-content.yml`](../../.github/workflows/verify-github-content.yml) passes `HEAD_REF: ${{ github.event.pull_request.head.sha }}` to the merge-from-main preflight, and the script's `resolve_head()` reads it. The straightforward `GITHUB_SHA` env var, used elsewhere, is **wrong** for this gate.

On `pull_request` events GitHub creates a synthetic merge ref at `refs/pull/<N>/merge` that points at a commit with two parents — the PR head and the base tip — so that CI can test what the merged tree would look like. `actions/checkout` checks this synthetic ref out by default and `GITHUB_SHA` resolves to it.

If the gate walked `{base}..HEAD` from that synthetic commit, it would always find the synthetic merge itself (parent count == 2), and every PR would false-positive the gate. Even a clean rebase would fail.

`github.event.pull_request.head.sha`, on the other hand, is the actual PR head — the commit the author pushed — not the synthetic merge. Walking back from there returns only commits the author authored, which is the comparison endpoint the gate needs.

Locally and in the pre-push hook, `HEAD_REF` is unset and `resolve_head()` returns `HEAD`, which is the branch tip the contributor is about to push — again the actual head, not a synthetic merge. The two paths converge on the same semantic.

Do not change the workflow to use `GITHUB_SHA` "for consistency"; the inconsistency is load-bearing.

## Related references

- Tracking issue: [#491](https://github.com/tvna/claude-md/issues/491)
- Sibling preflight (single-commit contract): [`scripts/preflight_pr_single_commit.py`](../../scripts/preflight_pr_single_commit.py), Issue [#492](https://github.com/tvna/claude-md/issues/492)
- Detection logic in retro reporter: `scripts/auto_retro.py` `_MERGE_FROM_MAIN_PREFIXES` and `_count_merge_from_main`
- Ruleset source of truth: [`.github/rulesets/main.json`](../../.github/rulesets/main.json)
