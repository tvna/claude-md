# Remote-session base-update runbook

Use this runbook when:

- You are in a **remote Claude session** (container, web, or CI environment),
- The branch is a `claude/*` branch (or any branch subject to the
  `all-branches-no-force-push` ruleset — i.e., not `main` and not
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
  contains `origin/main` — a chicken-and-egg deadlock.
- Force-push after a local rebase is denied by `non_fast_forward`.

The server-side procedure below works around both constraints using only
`mcp__github__create_or_update_file` (plain file pushes, always fast-forward)
and `mcp__github__update_pull_request_branch` (server-side merge of `main`).

### Prerequisites

- The PR is open and the branch is the one shown by `git branch --show-current`.
- You have the GitHub MCP tools available (`mcp__github__*`).

### Step 1 — Identify conflicting files

```sh
git fetch origin main
git merge-tree --write-tree HEAD origin/main 2>&1 | grep "^CONFLICT"
```

Record the conflicting paths. In most cases these are generated artifacts
(e.g. `docs/standards/module-size-distribution.toml`).

### Step 2 — Find the merge-base SHA

```sh
MERGE_BASE=$(git merge-base HEAD origin/main)
echo "$MERGE_BASE"
```

### Step 3 — Neutralize each conflicting file

For each conflicting file, read its content at the merge-base commit and push
that version to the branch via `mcp__github__create_or_update_file`.

```sh
# Get the file content at merge-base (for reference / diffing)
git show "$MERGE_BASE:<path/to/file>"

# Get the current HEAD SHA of the file on the remote branch (needed as `sha`
# parameter for the API call)
git ls-tree -r HEAD -- <path/to/file>
```

Then call `mcp__github__create_or_update_file` with:

- `path`: the file path (e.g. `docs/standards/module-size-distribution.toml`)
- `message`: a commit message citing the issue (e.g.
  `chore: set generated file to merge-base for server-side base-update #1802`)
- `content`: the base64-encoded merge-base content
- `sha`: the blob SHA of the current HEAD version of the file (from `git ls-tree` above)
- `branch`: the current branch name

This push is a plain non-force append commit; it satisfies `non_fast_forward`.
After this step the conflicting file on the remote branch is at the merge-base
version, so merging `main` into the branch will have no conflict there.

Repeat for each conflicting file.

### Step 4 — Server-side merge of main

Call `mcp__github__update_pull_request_branch` for the open PR.

> **Gate note**: `scripts/gate_update_pr_branch.py` (PreToolUse hook) will
> show a denial prompt for this tool. In the base-update context described
> here, **approve the operation**. The gate exists to prevent unnecessary
> merge commits on clean branches; here the merge commit is the intended
> mechanism and is acceptable because the final merge is squash-only (the
> merge commit does not appear in `main`'s history).

After this call the remote branch HEAD is a Verified merge commit that
contains `origin/main`. The freshness invariant is now satisfied.

### Step 5 — Sync local worktree to the merged state

```sh
git fetch origin
git reset --hard origin/<branch-name>
```

This is a local-only operation (no push), so `non_fast_forward` does not
apply.

### Step 6 — Regenerate generated artifacts

Re-run whatever script produces the generated files that were neutralized in
Step 3. For example, to regenerate `module-size-distribution.toml`:

```sh
python3 scripts/gen_module_size_distribution.py
```

Confirm the output differs from the merge-base version (it should now reflect
the merged state of `main` plus the feature-branch changes).

### Step 7 — Push the regenerated artifacts

For each regenerated file, push it via `mcp__github__create_or_update_file`:

- `path`: the file path
- `message`: e.g. `chore(generated): regenerate after server-side base-update #1802`
- `content`: the base64-encoded regenerated content
- `sha`: the blob SHA of the file currently on the remote branch (i.e. the
  merge-base version pushed in Step 3; get it with `git ls-tree` against the
  latest remote HEAD after Step 5)
- `branch`: the current branch name

### Step 8 — Verify CI and base freshness

1. Monitor the PR's CI checks until all required checks pass.
2. Confirm `python3 scripts/preflight_session_base_freshness.py check` exits 0.

If CI fails on an unrelated check, fix it with normal commits (the gate now
allows `git commit` because HEAD contains the session-start `origin/main` SHA
via the merge commit).

---

## Final merge

The PR cannot be self-merged from a remote session:
`main-protection` requires `require_code_owner_review: true` and
`bypass_actors: []`. The owner must merge using:

```sh
gh pr merge <PR-number> --squash --admin
```

The `--admin` flag bypasses the code-owner review requirement (the reviewer
and owner are the same person in a solo-dev repository). The squash-merge
produces a single Verified commit on `main`; the branch's merge commit does
not appear in `main`'s history.

---

## Apply rulesets after a SoT-only ruleset change

**Constraint**: `mcp__github__actions_run_trigger` (workflow_dispatch) returns
`403 Resource not accessible by integration` from a remote Claude session
because the integration token lacks `actions: write`. This cannot be lifted by
operator approval — it is a token-scope limit, not a permission prompt.

**When it matters**: Any PR that merges a change to `.github/rulesets/*.json`
onto `main` leaves the live ruleset behind the SoT JSON until the owner
manually dispatches the `Apply rulesets` workflow. While the live ruleset lags,
`Verify ruleset sync / gate` fails on **every open PR** — this is an effective
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
   the check in the Actions UI) — the check caches the stale result until
   re-triggered.

See `docs/runbooks/rulesets.md` for the full `Apply rulesets` procedure and
the `Dispatch authorization criteria`.

---

## Companion documents

- `docs/runbooks/refresh-behind-pr.md` — conflict-free fast path
- `docs/runbooks/update-pr-branch-recovery.md` — replacement-branch path for
  persistent conflicts
- `docs/runbooks/merge-readiness-loop.md` — where base-update sits in the
  overall PR loop
- `docs/runbooks/rulesets.md` — `non_fast_forward` rationale and `Apply
  rulesets` procedure
- `scripts/preflight_session_base_freshness.py` — the gate that detects a
  stale base and blocks `git commit`
- `scripts/refresh_pr_branch.py` — the conflict-free helper
