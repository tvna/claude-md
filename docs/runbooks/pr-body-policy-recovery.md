# PR body policy recovery runbook

When a pull request body fails a body-policy gate **after the PR is open**
(the post-2026-05-26 shape gate in `verify-pr.yml`, the Refs check, or the
H2 baseline gate), recover by re-editing the body so a fresh event re-runs
the gate. Do not re-run the stale failed run, and do not add an empty
"retrigger" commit. This runbook is the approved path that keeps the
single-commit contract intact and avoids an avoidable close-and-reopen loop.

Refs #675. Companion to
[`replacement-pr-preflight.md`](replacement-pr-preflight.md),
[`update-pr-branch-recovery.md`](update-pr-branch-recovery.md), and
[`issue-triage.md`](issue-triage.md).

## Why "re-run the failed run" does not work

`verify-pr.yml` triggers on
`pull_request: [opened, edited, synchronize, reopened, ready_for_review]`
and validates `github.event.pull_request.body` from the event payload
(`scripts/body_policy.py verify`). A GitHub Actions **re-run** replays the
*original* event payload, so it re-validates the stale body even after the
body has been edited. Editing the PR body instead emits a new
`pull_request: edited` event whose payload carries the corrected body, which
is what makes the gate pass.

| Action | Payload used | Outcome on a body fix |
|---|---|---|
| Re-run the failed workflow run | original (stale) body | still fails |
| Edit the PR body (`update_pull_request`) | fresh edited body | re-validates the fix |
| Empty "retrigger" commit | n/a | blocked at push, breaks single-commit |

## Recovery procedure

1. **Fix the body locally and validate before sending it.**

   Write the corrected body to a file and run the same checks the server
   runs:

   ```sh
   python3 scripts/preflight_pr_body.py verify --body-file body.md
   # add --issue <N> to also check the Refs/Closes link
   ```

   `scripts/preflight_pr_template_shape.py` runs the identical shape checks
   automatically as the MCP PreToolUse hook bound in `.claude/settings.json`,
   so the update call below is denied client-side if the body is still
   malformed.

2. **Apply the fix by editing the PR body, not by re-running CI.**

   Use `mcp__github__update_pull_request` to replace the body. This emits a
   fresh `pull_request: edited` event, and `verify-pr.yml` re-validates the
   corrected body. Do **not** press "Re-run jobs" on the failed run -- it
   reuses the stale payload (see the table above).

3. **Confirm the new check run, not the old one, goes green.**

   The edit creates a new workflow run. Watch that run; the original failed
   run stays red and is expected to.

## Do not add empty retrigger commits

Never push an empty commit (for example `git commit --allow-empty -m
"retrigger checks"`) to a PR branch to force CI to re-run. It does not carry
the body fix, and it breaks the single-commit contract:

- `scripts/preflight_push_nonempty.py` blocks a push whose local `HEAD`
  adds no new work over the base tip (Refs #1130), so the empty commit is
  refused at push time.
- The repository ruleset (`.github/rulesets/main.json`) is squash-only with
  linear history, and `scripts/auto_retro.py` records a `multi_commit_pr`
  signal post-merge, so extra commits surface in the retrospective even when
  a push slips through.
- Force-push is blocked by the ruleset, so a stray commit cannot be squashed
  away in place -- which is exactly the trap that pushes a session toward a
  replacement PR.

The correct way to re-trigger the PR-body gate is the body edit in step 2,
not a commit.

## Decision tree: which repair for which symptom

| Symptom | Approved repair | Reference |
|---|---|---|
| Body fails the shape / Refs / H2 gate after open | Edit the PR body via `update_pull_request` (fresh `edited` event) | this runbook |
| CI must re-run but the body is already correct | Push a real follow-up commit, or edit the body; never an empty commit | this runbook |
| Branch fell behind `main`, conflict-free | Local `git merge origin/<base>` + plain push | [`refresh-behind-pr.md`](refresh-behind-pr.md) |
| Branch fell behind `main`, cannot fast-forward | New branch from `main`, re-apply as one commit | [`update-pr-branch-recovery.md`](update-pr-branch-recovery.md) |
| Routing label missing or wrong | Manually add/remove the label per the taxonomy | [`issue-triage.md`](issue-triage.md) |
| PR genuinely cannot be repaired in place | Close + replacement PR with a root-cause note | [`replacement-pr-preflight.md`](replacement-pr-preflight.md) |

A replacement PR is the last resort, not the first. Reach for it only after
the body edit, label repair, and behind-refresh paths above are ruled out,
and record the required root-cause note so the replacement-PR guard
(`scripts/preflight_replacement_pr.py`) classifies the churn correctly.

## Verify

```sh
# This runbook is registered in the docs inventory.
python3 scripts/scan_docs_inventory.py verify

# A candidate body passes the same local gate the server runs.
python3 scripts/preflight_pr_body.py verify --body-file body.md
```
