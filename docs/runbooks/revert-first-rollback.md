# Revert-First Rollback

When the operator's intent is to roll back, undo, or revert a previously
merged change, default to `git revert` of the original commit(s) rather than
hand-authoring inverse edits. A `git revert` reproduces the exact prior state
deterministically, keeps a clean audit trail, and cannot silently diverge from
the state it claims to restore. Hand-authored inverse edits are slower,
error-prone, and lose that provenance (issue #1020).

This runbook is the knowledge source for the planned rollback skill: it records
how to identify the commit/PR set, the revert order, verification, and the
explicit conditions that justify a manual fallback.

## When this applies

Operator intent signals a rollback when the request is to "revert", "roll
back", "undo", "abandon", "back out", or "restore the state before" a change
that is already merged into the target branch. The rule is intent-based, not
tied to any subsystem.

## Procedure

1. **Identify the commit/PR set to revert.**
   - From a PR: the merge commit SHA is the anchor. For a squash-merged PR the
     single squash commit is the target; for a merge-commit PR use
     `git revert -m 1 <merge_sha>` so the first parent is treated as the
     mainline.
   - From history: list candidates and confirm scope.
     ```sh
     git log --oneline <good_base>..<current_head>
     ```
   - Prefer reverting the **smallest set of original commits** that restores the
     intended prior state. If the operator names a target commit to restore to,
     confirm that the revert set is exactly `target..HEAD`.

2. **Revert in the correct order.** For stacked changes, revert **newest
   first** so each inverse applies cleanly against the current tree:
   ```sh
   git revert --no-commit <good_base>..<current_head>   # range form, or
   git revert --no-commit <c4> <c3> <c2> <c1>           # explicit, newest first
   ```
   Use `--no-commit` to stage all inverses, then make a single revert commit so
   the rollback lands as one reviewable unit.

3. **Verify the tree matches the intended prior state** before committing. This
   is the proof that the rollback is faithful:
   ```sh
   git diff --quiet HEAD <target_commit> && echo MATCH || echo DIFFERS
   ```
   `MATCH` means the staged tree is byte-identical to the restore target. If it
   reports `DIFFERS`, a later commit touched the same files; resolve before
   committing rather than shipping a partial rollback.

4. **Commit and cite the issue.** One revert commit, message naming the
   reverted PR/commit numbers and the restore target, with the issue reference
   per section 3 of the agent instructions.

5. **Open the PR and drive it to a terminal state** as for any change.

## When to fall back to hand-authored inverse edits

Revert is the default. Fall back only when revert is genuinely infeasible, and
**state the reason in the PR/commit before doing so**:

- **Non-contiguous interleaving**: later commits modified the same lines for
  reasons that must be kept, so a clean revert would also undo wanted work.
- **Partial-scope rollback**: only part of a commit's change should be undone.
- **Unavoidable conflicts**: the revert conflicts and the resolution is itself
  a re-derivation, with no smaller revert set that avoids it.

In each case, prefer the smallest manual diff that reaches the target state,
and verify it the same way (step 3).

## Anti-pattern (issue #1020)

Re-deriving a prior state by hand across many files (config, workflows, docs,
scripts, tests) to undo a merged change, when a `git revert` of the original
rollout commits would reproduce that state deterministically. In the #1020
session the agent began hand-authoring inverse edits across `main.json`, five
workflows, runbooks, `scripts/`, and `tests/` to abandon the merge-queue
rollout; the operator corrected it and the rollback completed cleanly via
`git revert` (PR #1018). If you catch yourself authoring inverse edits for a
rollback intent, STOP and check whether a revert of the original commits is
feasible first.
