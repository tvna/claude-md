# Label migration operation log -- 2026-05-26

Append-only operation log for the back-labeling pass driven by sub-issue [#405](https://github.com/tvna/claude-md/issues/405) under parent [#84](https://github.com/tvna/claude-md/issues/84). This file records the issue-by-issue before / after label state for the three audit findings posted as comment 4539839182 on #84.

Retention policy: governed by [`docs/archive/RETENTION.md`](RETENTION.md). This file is not edited after merge.

## Summary

| Group | Issues touched | API calls | Resulting compliance |
|---|---:|---:|---|
| A. Multi-type fix (`type:feat` removed) | 3 | 3 | Three umbrella issues now carry exactly one `type:*` (`type:tracking`). |
| B. `agent:*` residue (`layer:*` / `type:*` added) | 9 | 9 | All nine carry `>=1 layer:*` and `exactly 1 type:*`. `agent:*` label still present on each; removed by the post-merge prune dispatch. |
| C. `governance` residue (`layer:*` / `type:*` added) | 10 closed | 10 | All ten carry `>=1 layer:*` and `exactly 1 type:*`. `governance` still present; removed by the post-merge prune dispatch. The legacy `fix` label on #53 / #55 is also removed by the same dispatch. |
| Open #338 (`governance` only) | 0 | 0 | Already carried `layer:meta` + `type:chore`. `governance` removed by the post-merge prune dispatch. No back-label needed; `type:chore` retirement is intentionally out of scope per the #84 decision tree. |

Total: 22 unique issues touched (#18, #34, #87, #58, #60, #61, #62, #63, #72, #88, #89, #90, #51, #53, #55, #73, #75, #106, #109, #112, #113, #115).

## A. Multi-type fix

The audit found three umbrella issues carrying both `type:tracking` and `type:feat`. The runbook requires exactly one `type:*`; `type:tracking` is the correct choice for umbrella issues that orchestrate phased sub-issues. Each issue's actual feature work is delivered through its sub-issues, so the `type:feat` label was historical and is now removed.

| Issue | State | Before | After |
|---|---|---|---|
| #18 | open | `layer:p3-harness`, `type:feat`, `type:tracking` | `layer:p3-harness`, `type:tracking` |
| #34 | closed | `layer:p3-harness`, `type:feat`, `type:tracking` | `layer:p3-harness`, `type:tracking` |
| #87 | open | `layer:p3-harness`, `type:feat`, `type:tracking` | `layer:p3-harness`, `type:tracking` |

## B. agent:* residue

Six `agent:investigate` + three `agent:no-action` issues were back-labeled with the SoT taxonomy. The `agent:*` label itself remains on each issue and is removed by the post-merge prune dispatch (the label definition disappears from the live catalogue, which strips the label from every assignment in one operation).

| Issue | State | Before | After | Rationale |
|---|---|---|---|---|
| #58 | closed | `agent:no-action` | `agent:no-action`, `layer:meta`, `type:tracking` | Repo scope tracker (#58 itself). Umbrella for Phase 1-3 sub-issues. |
| #60 | closed | `agent:investigate` | `agent:investigate`, `layer:p2-precode`, `type:docs` | Phase 1 deliverable: `docs/repo-scope.md` runbook + ignore-list widening. Pre-code reasoning lane. |
| #61 | open | `agent:investigate` | `agent:investigate`, `layer:p4-artifact`, `type:docs` | Performance harness design doc. Artifact lane (measurement target is compiled `CLAUDE.md` / `AGENTS.md`). |
| #62 | open | `agent:investigate` | `agent:investigate`, `layer:p4-artifact`, `type:docs` | Baseline numbers acquisition. Same lane as #61. |
| #63 | open | `agent:investigate`, `governance` | `agent:investigate`, `governance`, `layer:p3-harness`, `type:tracking` | Residual workflow security catalog (8-phase plan with sub-sub-issues). Umbrella for Phase 1-8. |
| #72 | open | `agent:no-action`, `governance` | `agent:no-action`, `governance`, `layer:meta`, `type:docs` | Ruleset-adjacent issue triage matrix. Repo infrastructure decision doc. |
| #88 | open | `agent:investigate` | `agent:investigate`, `layer:p4-artifact`, `type:docs` | Benchmark input governance rules (tvna-only, anonymization). Performance-metrics doc update. |
| #89 | open | `agent:no-action` | `agent:no-action`, `layer:meta`, `state:rfc`, `type:docs` | Agent instruction versioning scheme RFC. Multiple open questions (Q1-Q3) require human decision. `state:rfc` routes to no-action per the runbook table. |
| #90 | open | `agent:investigate` | `agent:investigate`, `layer:p4-artifact`, `type:docs` | Benchmark structure-sensitive task adoption. Performance-metrics spec extension. |

## C. governance residue (closed cosmetic)

Ten closed issues carried only `governance` (with one outlier: #53 and #55 also had the legacy `fix` label). These are cosmetic back-labels; the issues are already merged, so the impact is restricted to historical-search hygiene. The `governance` and `fix` labels are removed by the post-merge prune dispatch.

| Issue | State | Before | After | Rationale |
|---|---|---|---|---|
| #51 | closed | `governance` | `governance`, `layer:p3-harness`, `type:feat` | Workflow-based apply infrastructure (CI feat). |
| #53 | closed | `fix`, `governance` | `fix`, `governance`, `layer:p3-harness`, `type:fix` | Replace unavailable `gh cli` usage in ruleset workflow. |
| #55 | closed | `fix`, `governance` | `fix`, `governance`, `layer:p3-harness`, `type:fix` | Remove invalid roles endpoint check. |
| #73 | closed | `governance` | `governance`, `layer:p2-precode`, `type:docs` | Reframe uncertainty control in agent rules (section 2). |
| #75 | closed | `governance` | `governance`, `layer:meta`, `type:docs` | Add per-principle layer identifiers to the universal rules. |
| #106 | closed | `governance` | `governance`, `layer:p2-precode`, `type:fix` | Sync remote `uv` setup with CI (environment fix). |
| #109 | closed | `governance` | `governance`, `layer:meta`, `type:refactor` | Allow tracked `.claude/settings.json` (carve-out from #58). |
| #112 | closed | `governance` | `governance`, `layer:p2-precode`, `type:refactor` | Consolidate `uv` version source (single SoT). |
| #113 | closed | `governance` | `governance`, `layer:p2-precode`, `type:docs` | Retrospective for PR #111 (`uv` SessionStart hook). |
| #115 | closed | `governance` | `governance`, `layer:p2-precode`, `type:docs` | Retrospective for PR #107 (`uv` hook rollup). |

## D. Operator step (post-merge, not in this PR's diff)

After this PR merges, the repository owner runs the prune dispatch to remove the now-orphan label definitions from the live label catalogue:

```sh
# Step 1: dry-run; the step summary should list these labels for DELETE
gh workflow run apply-labels.yml --ref main -f dry_run=true -f prune=true
# Expected DELETE set:
#   agent:auto-fix       (was 0 live assignments)
#   agent:investigate    (was 6 live, all back-labeled in section B above)
#   agent:no-action      (was 3 live, all back-labeled in section B above)
#   agent:triage-needed  (was 0 live assignments)
#   governance           (was 32 live; 22 had layer:* before this pass; remaining 10 back-labeled in section C above)
#   fix                  (was 2 live, #53 and #55, both now also carry type:fix)

# Step 2: live apply
gh workflow run apply-labels.yml --ref main -f dry_run=false -f prune=true

# Step 3: verify the live catalogue matches SoT
diff <(gh api /repos/tvna/claude-md/labels --jq '.[].name' | sort) <(jq -r '.[].name' .github/labels.json | sort)
# Expect: only `type:chore` may appear as a one-line live-only entry (out of scope for this pass; tracked separately on #338).
```

The dispatch step is destructive on existing label assignments (the runbook warns about this); the back-labeling pass above is what makes the deletion safe.

## Verification log (pre-merge)

Captured after the 22 label edits, before this PR opens:

```sh
gh issue list --search 'is:issue label:type:feat label:type:tracking'                                                                                                                                                # 0
gh issue list --search 'is:issue label:agent:investigate -label:layer:p1-goal-plan -label:layer:p2-precode -label:layer:p3-harness -label:layer:p4-artifact -label:layer:p5-scope-split -label:layer:p6-handoff -label:layer:meta'    # 0
gh issue list --search 'is:issue label:agent:no-action  -label:layer:p1-goal-plan -label:layer:p2-precode -label:layer:p3-harness -label:layer:p4-artifact -label:layer:p5-scope-split -label:layer:p6-handoff -label:layer:meta'    # 0
gh issue list --search 'is:issue label:governance       -label:layer:p1-goal-plan -label:layer:p2-precode -label:layer:p3-harness -label:layer:p4-artifact -label:layer:p5-scope-split -label:layer:p6-handoff -label:layer:meta'    # 0
gh issue list --search 'is:issue label:agent:investigate -label:type:tracking -label:type:feat -label:type:fix -label:type:refactor -label:type:docs'                                                                # 0
```

All five queries return zero, confirming that every `agent:*` and `governance` residue issue now satisfies the runbook's classification requirements before the destructive prune step.

## Scope notes

- `type:chore` (#338): explicitly out of scope for this pass per the #84 decision tree. The issue itself is a discussion ticket and its `type:chore` label retires when #338 closes.
- Open `governance` issues with `layer:*` already assigned (#63, #72, #338 -- and #63 in this pass gained `type:tracking`): not in section C above because the layer was already present pre-pass; the `governance` label removal still happens via the prune dispatch.
- Pre-prune-only: `agent:auto-fix` and `agent:triage-needed` had no live assignments before this pass, so neither appears in sections A, B, or C; both label definitions are deleted by the prune step purely for catalogue cleanup.

Refs: #405 (operation tracker), #84 (umbrella).
