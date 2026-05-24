# Retrospective -- PR #248 Agent-Rules Design Philosophy Repair-Free Merge

This document is the retrospective for [#250](https://github.com/tvna/claude-md/issues/250) -- the post-merge review of PR [#248](https://github.com/tvna/claude-md/pull/248), which closed issue [#246](https://github.com/tvna/claude-md/issues/246) ("docs(agent-rules): add design philosophy and responsibility boundary doc") and refs the parent tracker [#226](https://github.com/tvna/claude-md/issues/226). The retrospective framework lives in CLAUDE.md section 3: classify each pre-merge repair, identify the earliest deterministic gate that should have prevented it, and state the no-repair reproduction path for the next similar PR. This is a positive-control entry; zero repairs were observed, so the classification and prevention sections explain the no-repair path that the existing harness already delivers.

## Scope

- Target PR: [#248](https://github.com/tvna/claude-md/pull/248), merged as commit `27e1e9a` on 2026-05-24T00:53:31Z.
- Closed issue: [#246](https://github.com/tvna/claude-md/issues/246) -- a meta document for `master.instructions.md` capturing the responsibility boundary between universal rules, harness, repo-local docs, and project-local instructions.
- Parent tracker: [#226](https://github.com/tvna/claude-md/issues/226) -- the umbrella issue for the agent-rules redesign workstream.
- Out of scope: the substance of the merged `docs/agent-rules-design-philosophy.md` and the five "Design rationale" cross-link edits in `docs/repo-scope.md`, `docs/security-control-inventory.md`, `docs/issue-pr-body-standard.md`, `docs/non-ascii-defense.md`, `docs/workflow-script-quality.md` -- those were accepted as-merged.

## Repair history

PR #248 landed via a single commit (`1c92d9b`) on branch `claude/agent-rules-design-docs-i01VN` with **zero pre-merge repairs**. No reviewer comments, no PR-level comments, no review threads, and no failed CI check runs. The PR was open for 8 minutes (opened `2026-05-24T00:45:16Z`, merged `00:53:31Z`).

| # | Repair | What the reviewer caught |
|---|---|---|
| -- | (none) | (none) |

Observed CI surface at merge time: 14 check runs across the open and merge events, all reporting `success` except two that correctly reported `skipped` (`verify` and `audit` short-circuited because the diff did not touch APM source or `dependabot[bot]` paths). The `open-retro` check fired on the merge commit and produced this retrospective issue.

## Classification

Per CLAUDE.md section 3 taxonomy ("missing deterministic gate / unclear agent instruction / external or human decision that cannot be automated"):

| Repair | Classification | Reasoning |
|---|---|---|
| -- | n/a | The repair set is empty, so no entry maps into any of the three categories. The classification framework is restated here so the next retrospective writer has a template even when the positive-control case fires again. |

## Earliest prevention point

Reframed for the positive-control case as "earliest deterministic gates that already enforced the no-repair path." Each gate fired on first try with no operator intervention:

- **`verify-title-policy.yml`** accepted the title `docs(agent-rules): add design philosophy and responsibility boundary doc` against its conventional-commit regex on first try.
- **`verify-body-policy.yml`** accepted the PR body section structure (Summary, Related Issue, Facts, Assumptions, Risk & blast radius, Rollback, Verification, Checklist) on first try. This gate was paid down by PR #220 and is the most likely place a future similar PR would regress.
- **`verify-issue-link.yml`** resolved `Closes #246` (and `Refs #226`) and pinned the close-on-merge linkage on first try.
- **`verify-apm-drift.yml`** confirmed source-output equivalence: the diff did not touch `.apm/instructions/master.instructions.md`, so the compiled `CLAUDE.md` / `AGENTS.md` artifacts stayed in sync without a regeneration step.
- **`verify-apm-portability.yml`** ran clean: the new doc and the five touched docs introduced no repo-local references that would leak into a standalone downstream consumer of the compiled rules.
- **`scan-non-ascii.yml`** raised no advisory because the PR body and the six touched files stayed within the ASCII boundary the policy enforces.
- **`verify-agents.yml`** detect job correctly short-circuited because no `.apm/instructions/**` or `scripts/**` path was touched, avoiding an unnecessary compile-and-diff pass.
- **`lint-scripts.yml`** had no Python source to lint in this diff and short-circuited cleanly.
- **`gate.yml`** (pytest matrix) ran the 699-test suite with zero regressions.

## No-repair reproduction path

For the next PR that follows the same shape as #248 (net-new docs file under `docs/` plus minimal "Design rationale" cross-links in existing sibling docs, with no touch to agent rules, scripts, workflows, or compiled artifacts), the path to a repair-free merge is:

1. **Plan phase**: enumerate facts and assumptions in the PR body before writing code; tag every line that is a guess with `speculation:` so reviewers see the surface area immediately (CLAUDE.md section 2). For meta-documentation PRs, state up front whether the doc is a judgment aid or a new gate -- this prevents reviewers from expecting CI enforcement that the PR does not deliver.
2. **Edit phase**: add the new doc under `docs/<descriptive-name>.md`. Touch sibling docs only with a single-line cross-link header (e.g. "Design rationale: see `agent-rules-design-philosophy.md`") and only where the boundary is most easily lost. Do not touch `.apm/**`, `scripts/**`, `.github/**`, `CLAUDE.md`, or `AGENTS.md` in the same PR -- those paths trigger compile, portability, and agent-verification gates that would invite repair loops on a docs-only intent.
3. **Local verify phase**: run `LC_ALL=C grep -P "[^\x00-\x7F]" docs/<new-file>.md` to confirm ASCII-only; run `git diff --stat origin/main..HEAD` to confirm no APM artifact drift.
4. **Test phase**: run `uv run pytest -q` and quote the pass count in the PR body's `## Verification` block.
5. **Body phase**: copy `.github/PULL_REQUEST_TEMPLATE.md` and fill every section in order. Cite the closing issue with `Closes #NN` on the `Related Issue` line; add `Refs #<tracker>` when an umbrella issue exists. Keep the body ASCII-safe so `preflight_non_ascii.py` does not block subsequent automation that re-posts excerpts via `mcp__github__*` write tools.
6. **CI phase**: open the PR. The `verify-title-policy`, `verify-body-policy`, `verify-issue-link`, `verify-apm-drift`, `verify-apm-portability`, `scan-non-ascii`, `verify-agents` (correctly skipping), `lint-scripts` (correctly skipping), and `gate.yml` (pytest) gates run automatically. CI green means ready for merge.

## Gates exercised alongside this retrospective

| Gate | Outcome on PR #248 |
|---|---|
| `auto-retro.yml` (post-merge delivery from PR #237) | Fired post-merge at `2026-05-24T00:53:35Z` on commit `27e1e9a`; opened retro issue #250 successfully. This single observation confirms the auto-retro path stays green for the docs-only PR shape. |
| `verify-body-policy` (on issue #250) | Auto-opened body contains all five `_ISSUE_COMMON_REQUIRED` sections (`Scope`, `Facts`, `Proposed work`, `Verification`, `Acceptance criteria`). |
| `is_retro_pr` skip rule (PR #247 fix) | The PR closing this retro (`docs(retro): ...`) is correctly skipped by `auto_retro.py` via the `(retro) in type-scope` branch, preventing a recursive retro-on-retro filing. |

## Follow-up issues

(none) -- no missing deterministic gate, unclear agent instruction, or external/human decision was surfaced by PR #248. The no-repair outcome is the artifact.

## References

- Retro issue: [#250](https://github.com/tvna/claude-md/issues/250) (this document closes it).
- Source PR: [#248](https://github.com/tvna/claude-md/pull/248) (merge commit `27e1e9a`).
- Closed issue: [#246](https://github.com/tvna/claude-md/issues/246).
- Parent tracker: [#226](https://github.com/tvna/claude-md/issues/226).
- Framework: CLAUDE.md section 3, codified in commit `daa5179` (#225).
- Sibling retrospectives: `docs/retrospective-pr-229.md`, `docs/retrospective-pr-235.md`, `docs/retrospective-pr-237.md`.
- Auto-retrospective workflow: `.github/workflows/auto-retro.yml`, shipped by PR [#237](https://github.com/tvna/claude-md/pull/237) and hardened against retro-on-retro recursion by PR [#247](https://github.com/tvna/claude-md/pull/247).
