# Remote-session base-update runbook

Use this runbook when:

- You are in a **remote Claude session** (container, web, or CI environment),
- The branch is a `claude/*` branch (or any branch subject to the
  `all-branches-no-force-push` ruleset; i.e., not `main` and not
  `dependabot/*`), and
- `scripts/preflight_session_base_freshness.py` warns that the branch base is
  stale.

The normal recovery (`git rebase origin/main` + force-push) is blocked in this
environment: `non_fast_forward` in `.github/rulesets/all-branches.json` denies
any push that is not a fast-forward, with `bypass_actors: []`. This runbook
documents the fully server-side, no-force-push path proven in PR #1727
(retro #1775).

Refs #1802, #1775, #1727, #1632, #745.

---

## Decision: merge vs. rebase when updating the base

Before running any base-update command, decide between `git merge` and
`git rebase`. Rebase rewrites the branch's commit SHAs, so a branch that has
already been pushed becomes non-fast-forward and the follow-up push is rejected
when force-push is prohibited (the circular failure recorded in retro #1824, PR
#1822 R2). Branch on whether the branch already has a remote ref:

```sh
git rev-parse --verify origin/"$(git branch --show-current)"
```

| Result | Meaning | Action |
|---|---|---|
| Succeeds (prints a SHA) | The branch is already pushed; on a `claude/*` branch force-push is prohibited by `non_fast_forward` | Use `git merge origin/main` (the merge commit keeps the remote tip as an ancestor, so the push stays fast-forward). For a conflict-free update prefer the helper in the [Conflict-free path](#conflict-free-path), which performs exactly this merge. |
| Fails (no such ref) | The branch has not been pushed yet | `git rebase origin/main` is safe; there is no remote ref to diverge from, so re-publishing the branch is a normal (non-force) push. |

This decision is the local-command counterpart to the conditional guidance in
the `scripts/preflight_session_base_freshness.py` error message: when the branch
is already pushed and force-push is prohibited, merge rather than rebase.

---

## Decision: conflict-free vs. generated-file conflict

First probe whether the merge would conflict:

```sh
git fetch origin main
python3 scripts/refresh_pr_branch.py --dry-run
```

| Result | Action |
|---|---|
| Exit 0: conflict-free | [Conflict-free path](#conflict-free-path) |
| Exit 2: conflicts | [Conflict path](#conflict-path-generated-file-or-other-conflict) |
| Exit 3: precondition | Fix the reported precondition, then re-probe |

---

## Conflict-free path

Run the helper with `--push`; it does a local `git merge --no-edit
origin/main` and a plain (non-force) push:

```sh
python3 scripts/refresh_pr_branch.py --push
```

The merge commit is acceptable: `main-protection` is squash-only, so the
final squash-merge flattens the branch regardless. After the push the base
is no longer stale and CI re-runs automatically.

See `docs/runbooks/refresh-behind-pr.md` for the full decision tree and exit
code contract.

---

## Conflict path (generated-file or other conflict)

When `refresh_pr_branch.py` exits 2, the merge conflicts must be resolved
server-side because:

- A local `git commit` (needed to record the conflict resolution) is blocked
  by `scripts/preflight_session_base_freshness.py` until HEAD already
  contains `origin/main`; a chicken-and-egg deadlock.
- Force-push after a local rebase is denied by `non_fast_forward`.

The server-side procedure below works around both constraints using only
`mcp__github__create_or_update_file` (plain file pushes, always fast-forward)
and `mcp__github__update_pull_request_branch` (server-side merge of `main`).

### Prerequisites

- The PR is open and the branch is the one shown by `git branch --show-current`.
- You have the GitHub MCP tools available (`mcp__github__*`).

### Step 1; Identify conflicting files

```sh
git fetch origin main
git merge-tree --write-tree HEAD origin/main 2>&1 | grep "^CONFLICT"
```

Record the conflicting paths. In most cases these are generated artifacts
(e.g. `docs/standards/module-size-distribution.toml`).

### Step 2; Find the merge-base SHA

```sh
MERGE_BASE=$(git merge-base HEAD origin/main)
echo "$MERGE_BASE"
```

### Step 3; Neutralize each conflicting file

For each conflicting file, read its content at the merge-base commit and push
that version to the branch via `mcp__github__create_or_update_file`.

```sh
# Get the file content at merge-base (pipe directly into the MCP call)
git show "$MERGE_BASE:<path/to/file>"

# Get the blob SHA of the file currently on the branch (required by the MCP tool
# when updating an existing file)
git rev-parse HEAD:<path/to/file>
```

Then call `mcp__github__create_or_update_file` with:

- `path`: the file path (e.g. `docs/standards/module-size-distribution.toml`)
- `message`: a commit message citing the issue (e.g.
  `chore: set generated file to merge-base for server-side base-update #1802`)
- `content`: the **raw file content** from `git show "$MERGE_BASE:<path>"` above
  (the MCP tool accepts a plain string; do not base64-encode it)
- `sha`: the blob SHA from `git rev-parse HEAD:<path>` above
- `branch`: the current branch name

This push is a plain non-force append commit; it satisfies `non_fast_forward`.
After this step the conflicting file on the remote branch is at the merge-base
version, so merging `main` into the branch will have no conflict there.

Repeat for each conflicting file.

### Step 4; Server-side merge of main (owner action required)

**The agent cannot perform this step directly.**
`scripts/gate_update_pr_branch.py` (PreToolUse hook) unconditionally denies
`mcp__github__update_pull_request_branch` with a hard `permissionDecision:
deny`; the hook contract does not offer an override prompt.

**The owner must click the "Update branch" button** on the PR page in the
GitHub web UI. This performs the same server-side merge that
`update_pull_request_branch` would: it merges `main` into the feature branch
as a Verified, non-force merge commit and satisfies `non_fast_forward`.

After the owner completes this step, the remote branch HEAD is a Verified
merge commit that contains `origin/main`. The freshness invariant is now
satisfied.

### Step 5; Sync local worktree to the merged state

```sh
git fetch origin
git reset --hard origin/<branch-name>
```

This is a local-only operation (no push), so `non_fast_forward` does not
apply.

### Step 6; Regenerate generated artifacts

Re-run whatever script produces the generated files that were neutralized in
Step 3. For example, to regenerate `module-size-distribution.toml`:

```sh
python3 scripts/gen_module_size_distribution.py
```

Confirm the output differs from the merge-base version (it should now reflect
the merged state of `main` plus the feature-branch changes).

### Step 7; Push the regenerated artifacts

For each regenerated file, push it via `mcp__github__create_or_update_file`:

- `path`: the file path
- `message`: e.g. `chore(generated): regenerate after server-side base-update #1802`
- `content`: the **raw file content** (plain string, not base64-encoded)
- `sha`: the blob SHA of the file currently on the remote branch (i.e. the
  merge-base version pushed in Step 3); get it with
  `git rev-parse origin/<branch>:<path>` after Step 5's fetch
- `branch`: the current branch name

### Step 8; Verify CI and base freshness

1. Monitor the PR's CI checks until all required checks pass.
2. Confirm `python3 scripts/preflight_session_base_freshness.py check` exits 0.

If CI fails on an unrelated check, fix it with normal commits (the gate now
allows `git commit` because HEAD contains the session-start `origin/main` SHA
via the merge commit).

---

## Final merge

The PR cannot be self-merged from a remote session:
`main-protection` requires `require_code_owner_review: true` and
`bypass_actors: []`. In a solo-dev repository the code-owner and PR author
are the same person and cannot self-approve, so the only available path is an
admin override.

**Preconditions before running the command below; verify all of these first:**

1. All required CI checks are green on the PR head commit.
2. All review threads are resolved.
3. The only remaining `mergeable_state` blocker is `require_code_owner_review`.

Only when all three hold should the owner run:

```sh
gh pr merge <PR-number> --squash --admin
```

`--admin` overrides branch-protection rules (including code-owner review). It
does **not** skip CI: if any required check is still failing, the merge will
fail even with `--admin` unless the repo uses admin-bypass rules; in this
repo there are none (`bypass_actors: []`). Confirm CI is green before
running.

The squash-merge produces a single Verified commit on `main`; the branch's
intermediate merge commit does not appear in `main`'s history.

---

## Apply rulesets after a SoT-only ruleset change

**Constraint**: `mcp__github__actions_run_trigger` (workflow_dispatch) returns
`403 Resource not accessible by integration` from a remote Claude session
because the integration token lacks `actions: write`. This cannot be lifted by
operator approval; it is a token-scope limit, not a permission prompt.

**When it matters**: Any PR that merges a change to `.github/rulesets/*.json`
onto `main` leaves the live ruleset behind the SoT JSON until the owner
manually dispatches the `Apply rulesets` workflow. While the live ruleset lags,
`Verify ruleset sync / gate` fails on **every open PR**; this is an effective
repo-wide merge freeze, not a per-PR defect.

**Symptom**: All open PRs show `Verify ruleset sync / gate` red after a
`.github/rulesets/*.json` change lands on `main`, even PRs that do not touch
ruleset files.

**Resolution** (owner must perform manually):

1. Go to **Actions → Apply rulesets → Run workflow** in the GitHub UI.
2. Set `ruleset` to the changed file name (e.g. `main` or `all-branches`).
3. Run with `dry_run=true` first; confirm the planned diff matches the
   merged SoT JSON.
4. Re-run with `dry_run=false`.
5. Re-run `Verify ruleset sync / gate` on each open PR (re-push or re-run
   the check in the Actions UI); the check caches the stale result until
   re-triggered.

See `docs/runbooks/rulesets.md` for the full `Apply rulesets` procedure and
the `Dispatch authorization criteria`.

---

## Companion documents

- `docs/runbooks/refresh-behind-pr.md`; conflict-free fast path
- `docs/runbooks/update-pr-branch-recovery.md`; replacement-branch path for
  persistent conflicts
- `docs/runbooks/merge-readiness-loop.md`; where base-update sits in the
  overall PR loop
- `docs/runbooks/rulesets.md`; `non_fast_forward` rationale and `Apply
  rulesets` procedure
- `scripts/preflight_session_base_freshness.py`; the gate that detects a
  stale base and blocks `git commit`
- `scripts/refresh_pr_branch.py`; the conflict-free helper
