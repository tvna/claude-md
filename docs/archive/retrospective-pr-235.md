# Retrospective -- PR #235 Security Control Inventory Repair-Free Merge

This document is the retrospective for [#236](https://github.com/tvna/claude-md/issues/236) -- the post-merge review of PR [#235](https://github.com/tvna/claude-md/pull/235), which closed issue [#179](https://github.com/tvna/claude-md/issues/179) ("docs(security): inventory ATT&CK control coverage"). The retrospective framework lives in `.apm/instructions/master.instructions.md` §3: classify each pre-merge repair, identify the earliest deterministic gate that should have prevented it, and state the no-repair reproduction path for the next similar PR. This is a positive-control entry: zero repairs were observed, so the classification and prevention sections explain the no-repair path that the existing harness already delivers.

## Scope

- Target PR: [#235](https://github.com/tvna/claude-md/pull/235), merged as commit `ca1bd43` on 2026-05-23.
- Requested issue: [#179](https://github.com/tvna/claude-md/issues/179) -- a baseline inventory of security-relevant repository surfaces mapped to MITRE ATT&CK tactics.
- Parent tracker: [#178](https://github.com/tvna/claude-md/issues/178).
- Out of scope: the contents of the inventory file (`docs/security-control-inventory.md`) and any follow-up gate work for the surfaces it lists (those are tracked under reused issues #56, #63, #102, #120, #170, #180-184).

## Repair history

PR #235 landed via one commit on branch `claude/github-issue-209-1bxbq`. No repair loops are observable between PR open and merge:

| # | Repair | What the reviewer caught |
|---|---|---|
| -- | none | -- |

Observed CI surface at merge time: nine check runs, seven success (gate x4, detect, lint-scripts, scan), two correctly-skipped (verify-agents short-circuits when no APM or script paths change; dependabot-automerge audit runs only for `dependabot[bot]` PRs). No review comments were posted on PR #235. No PR-level comments were posted on PR #235. Time from PR open to merge was under ten minutes.

A single pre-open friction is recorded for completeness but is not a merge repair: the first `git push --force-with-lease=...` to the head branch returned `stale info` because the remote ref had been deleted server-side after the issue label sync. Resolved by a plain `git push -u origin <branch>` that created a fresh remote ref. This happened before PR open and falls outside the repair window defined by the framework.

## Classification

Per the `.apm/instructions/master.instructions.md` §3 taxonomy ("missing deterministic gate / unclear agent instruction / external or human decision"):

| Repair | Classification | Reasoning |
|---|---|---|
| -- | n/a | The repair set is empty, so no entry maps into any of the three categories. The classification framework is restated here so the next retrospective writer has a template even when the positive-control case fires. |

The pre-open `stale info` push friction was an external repository-state event (the remote ref was deleted between branch creation and push), not a repair tied to PR review or CI. It is recorded under Repair history for completeness but does not require a follow-up gate.

## Earliest prevention point

Reframed for the positive-control case as "earliest deterministic gates that already enforced the no-repair path." Each gate fired on first try with no operator intervention:

- **`verify-title-policy.yml`** accepted the title `docs(security): inventory ATT&CK control coverage` against its conventional-commit regex on first try.
- **`verify-body-policy.yml`** accepted the PR body section structure (Summary, Related Issue, Facts, Assumptions, Risk & blast radius, Rollback, Verification, Checklist) on first try. This gate was paid down by PR #220 and is the most likely place a future similar PR would regress.
- **`verify-issue-link.yml`** resolved `Closes #179` and pinned the close-on-merge linkage on first try.
- **`scan-non-ascii.yml`** raised no advisory because the PR body and the file content stayed within the ASCII boundary the policy enforces (the file itself is allowed to contain em-dashes; the gate only blocks them in issue and PR bodies posted via the `mcp__github__*` write tools through `scripts/preflight_non_ascii.py`).
- **`verify-agents.yml`** detect job correctly short-circuited because no `.apm/instructions/**` or `scripts/**` path was touched, avoiding an unnecessary compile-and-diff pass.

## No-repair reproduction path

For the next PR that follows the same shape as #235 (docs-only inventory or runbook addition that does not touch agent rules, scripts, workflows, or CLAUDE.md / AGENTS.md), the path to a repair-free merge is:

1. **Scope phase**: keep the change docs-only when the goal is to record state rather than change behavior. Inventory updates, runbook edits, and retrospective entries qualify. Avoid touching `.apm/**`, `scripts/**`, `.github/**`, `CLAUDE.md`, or `AGENTS.md` in the same PR -- those paths trigger compile, portability, and agent-verification gates that would invite repair loops on a docs-only intent.
2. **Edit phase**: place the file under `docs/<descriptive-name>.md`. Keep the content ASCII-safe where downstream consumers might re-post it through `mcp__github__*` write tools; em-dashes and similar punctuation are acceptable in the file itself.
3. **Title phase**: pick a conventional-commit title that matches `verify-title-policy.yml` (`^(?:build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test|tracking)(?:\([a-z0-9][a-z0-9-]*\))?: .+`). Do not embed the issue number in the title.
4. **Body phase**: copy `.github/PULL_REQUEST_TEMPLATE.md` and fill every section in order. Cite the closing issue with `Closes #NN` on the `Related Issue` line so the tracker auto-closes on merge.
5. **Parent-tracker phase**: if a tracker issue (`type:tracking`) lists the PR deliverable as a checklist item, post the checklist comment within the same session that opens the PR, before subscribing to PR activity, so the closing issue's verification step is satisfied immediately.
6. **PR phase**: open the PR. The `verify-title-policy`, `verify-body-policy`, `verify-issue-link`, `scan-non-ascii`, `verify-agents` (correctly skipping), and `verify-apm-portability` (correctly skipping) gates run automatically. CI green means ready for merge.

## Gates introduced alongside this retrospective

| Gate | Introduced here | Reasoning |
|---|---|---|
| -- | no | This is a positive-control retrospective: no repairs were observed, so no preventive gate is needed. The contrast with PR #232 (which shipped `scan_apm_portability.py` to close PR #229 repair loop B) is intentional and documents that the existing harness already delivers the no-repair path for docs-only PRs that follow the existing body and title policies. |

A single follow-up is restated rather than introduced: bump issue [#149](https://github.com/tvna/claude-md/issues/149) (the formally-open tracker for the auto-open retrospective workflow). PR [#237](https://github.com/tvna/claude-md/pull/237) shipped `.github/workflows/auto-retro.yml` against issue #234 ("centralize post-merge follow-up tracking") and substantively closes the operator-memory dependency that #149 was opened to fix; formal closure of #149 can be folded into the next pass on #234 part 2.

## References

- Issue: [#236](https://github.com/tvna/claude-md/issues/236) (this retrospective).
- PR: [#235](https://github.com/tvna/claude-md/pull/235) (merge commit `ca1bd43`).
- Closed issue: [#179](https://github.com/tvna/claude-md/issues/179).
- Parent tracker: [#178](https://github.com/tvna/claude-md/issues/178).
- Auto-retrospective workflow (deterministic opener, shipped after PR #235 merged; expected to fire on this retrospective PR merge): [#237](https://github.com/tvna/claude-md/pull/237).
- Formally-open harness gap: [#149](https://github.com/tvna/claude-md/issues/149).
- Retrospective format authority: PR [#225](https://github.com/tvna/claude-md/pull/225), codified in commit `daa5179`.
- Recent retrospectives following the same format: [#230](https://github.com/tvna/claude-md/issues/230), [#150](https://github.com/tvna/claude-md/issues/150), [#148](https://github.com/tvna/claude-md/issues/148), [#132](https://github.com/tvna/claude-md/issues/132).
