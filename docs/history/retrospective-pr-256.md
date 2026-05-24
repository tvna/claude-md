# Retrospective -- PR #256 Agent-Rules Philosophy Extension Repair-Free Merge

This document is the retrospective for [#258](https://github.com/tvna/claude-md/issues/258) -- the post-merge review of PR [#256](https://github.com/tvna/claude-md/pull/256), which closed issue [#252](https://github.com/tvna/claude-md/issues/252) ("docs(agent-rules): consume 226 checklist items 2 to 4") and refs the parent tracker [#226](https://github.com/tvna/claude-md/issues/226). The retrospective framework lives in CLAUDE.md section 3: classify each pre-merge repair, identify the earliest deterministic gate that should have prevented it, and state the no-repair reproduction path for the next similar PR. This is a positive-control entry; zero repairs were observed, so the classification and prevention sections explain the no-repair path that the existing harness already delivers.

## Scope

- Target PR: [#256](https://github.com/tvna/claude-md/pull/256), merged as commit `c9665cd` on 2026-05-24T01:28:45Z by `tvna`.
- Closed issue: [#252](https://github.com/tvna/claude-md/issues/252) -- consume the remaining three checklist items on parent #226 by extending the existing `docs/agent-rules-design-philosophy.md` (introduced by #246 / PR #248) with section 6.4 (retrospective taxonomy to ownership lanes), section 1 non-goals decision (do not extract a separate examples doc), and section 7 (instruction-PR review criteria), plus a single new line in `.github/PULL_REQUEST_TEMPLATE.md`.
- Parent tracker: [#226](https://github.com/tvna/claude-md/issues/226) -- umbrella issue for the agent-rules redesign workstream; PR #256 consumed items 2 to 4 on its checklist while leaving the universal source (`.apm/instructions/master.instructions.md`) and the compiled artifacts (`CLAUDE.md`, `AGENTS.md`) untouched.
- Out of scope: the substance of the new section 6.4 / section 7 wording and the one new PR-template checklist line -- those were accepted as-merged. The section-renumber (former 7 to 9 became 8 to 10) and the single internal "section 7" reference rewrite to "section 8" were both shipped in the same commit and are also out of scope here.

## Repair history

PR #256 landed via two commits on branch `claude/agent-rules-followup-226-items-2-4` with **zero pre-merge repairs**. No reviewer comments, no PR-level comments, no review threads, and no failed CI check runs. The PR was open for 2 minutes 29 seconds (opened `2026-05-24T01:26:16Z`, merged `01:28:45Z` by `tvna`).

| # | Repair | What the reviewer caught |
|---|---|---|
| -- | (none) | (none) |

Diff at merge time: 2 files changed, +151 / -6. The two files were `docs/agent-rules-design-philosophy.md` (+150 / -6, the section-6.4 / section-7 extension plus the renumber) and `.github/PULL_REQUEST_TEMPLATE.md` (+1 / -0, the single section-7 reviewer-checklist line). The two commits were independent: `docs(agent-rules): extend philosophy doc...` (extension + renumber) and `docs(pr-template): point reviewers to agent-rules philosophy section 7 for APM-touching PRs` (template line). Both commit subjects ended with `refs #252`, not `closes #252`; the `Closes #252` line lived only in the PR body, which is the supported shape under `verify-issue-link.yml`. Observed CI surface at merge time: 10 check runs covering the open and merge events, all reporting `success` except two that correctly reported `skipped` (`verify` and `audit` short-circuited because the diff did not touch APM source or `dependabot[bot]` paths). The `open-retro` check fired on the merge commit and produced this retrospective's source issue (#258) 9 seconds after merge.

## Classification

Per CLAUDE.md section 3 taxonomy ("missing deterministic gate / unclear agent instruction / external or human decision that cannot be automated"):

| Repair | Classification | Reasoning |
|---|---|---|
| -- | n/a | The repair set is empty, so no entry maps into any of the three categories. The classification framework is restated here so the next retrospective writer has a template even when the positive-control case fires again. |

## Earliest prevention point

Reframed for the positive-control case as "earliest deterministic gates that already enforced the no-repair path." Each gate fired on first try with no operator intervention:

- **`verify-title-policy.yml`** accepted the title `docs(agent-rules): consume 226 checklist items 2 to 4` against its conventional-commit regex on first try.
- **`verify-body-policy.yml`** accepted the PR body section structure (Summary, Related Issue, Facts, Assumptions, Risk & blast radius, Rollback, Verification, Checklist) on first try. This gate was paid down by PR #220 and remains the most likely place a future similar PR would regress.
- **`verify-issue-link.yml`** resolved `Closes #252` and pinned the close-on-merge linkage on first try, even though the two commit subjects only used `refs #252`. The body-level `Closes #` line is the binding signal for this gate, which keeps commit subjects free to record the looser "refs" relationship.
- **`verify-apm-drift.yml`** confirmed source-output equivalence: the diff did not touch `.apm/instructions/master.instructions.md`, so the compiled `CLAUDE.md` / `AGENTS.md` artifacts stayed in sync without a regeneration step. The PR body explicitly recorded the verification command `uv run --with "apm-cli==0.12.1" apm compile` and its zero-diff outcome.
- **`verify-apm-portability.yml`** ran clean: the section-6.4 and section-7 extension introduced no repository-specific references in universal text (none was added, because the PR did not edit universal text at all), and the new section 7.4 documents the `portability-ack:` escape-hatch policy that this gate enforces. The PR body recorded `python3 scripts/scan_apm_portability.py verify --path .apm/instructions/master.instructions.md --path CLAUDE.md --path AGENTS.md` exiting 0.
- **`scan-non-ascii.yml`** raised no advisory: the PR body and the two modified files stayed within the ASCII boundary the policy enforces. The PR body recorded `grep -nP '[^\x00-\x7F]' docs/agent-rules-design-philosophy.md` returning no matches.
- **`verify-agents.yml`** detect job correctly short-circuited because no `.apm/instructions/**` or `scripts/**` path was touched, avoiding an unnecessary compile-and-diff pass.
- **`lint-scripts.yml`** had no Python source to lint in this diff and short-circuited cleanly.
- **`gate.yml`** (pytest matrix) ran the 769-test suite with zero regressions (the count recorded by the PR body under `## Verification`).

A latent risk on this PR shape that did not surface as a repair, but is worth naming for the next writer: renumbering long-form section headers (PR #256 bumped sections 7 to 9 into 8 to 10) requires every internal "see section N" reference inside the same document to move in the same commit. PR #256 found and fixed exactly one such reference ("section 7" inside the update procedure became "section 8") in the same commit as the renumber, which is why no repair landed. A future similar PR that misses one of these references would surface only at human read-through (no deterministic gate covers intra-document section-number consistency today), so the no-repair path below restates the manual check.

## No-repair reproduction path

For the next PR that follows the same shape as #256 (extension of an existing `docs/` file with new sections appended near the end, a small number of pre-existing trailing sections renumbered, plus a one-line touch in `.github/PULL_REQUEST_TEMPLATE.md`, and no touch to agent rules, scripts, workflows, universal source, or compiled artifacts), the path to a repair-free merge is:

1. **Plan phase**: enumerate facts and assumptions in the PR body before writing code; tag every line that is a guess with `speculation:` so reviewers see the surface area immediately (CLAUDE.md section 2). When the diff appends sections to an existing long doc, list up front which trailing sections will be renumbered and which internal "see section N" references will need to move with them. This forces the writer to grep for the affected references before the first commit, not after the reviewer asks.
2. **Edit phase**: keep the diff to the two surfaces the closing issue requires (one existing `docs/` file plus one optional template line). Do not touch `.apm/instructions/**`, `CLAUDE.md`, `AGENTS.md`, `scripts/**`, or `.github/workflows/**` in the same PR -- those paths trigger compile, portability, agent-verification, and lint gates whose repair loops are out of proportion to a docs extension. If the new sections cross-link existing sections inside the same doc, write the anchor in lowercase-hyphenated form (`#4-decision-tree`, `#5-boundary-patterns-and-worked-examples`) so the link survives heading punctuation.
3. **Renumber phase**: when appending a new numbered section before the trailing ones, run `grep -nE 'section [0-9]+' docs/<file>.md` and walk every match. Each hit either points at one of the sections you renumbered (fix it in the same commit) or is intentional (leave it). Record the grep result in the PR body's `## Facts` so the reviewer does not have to re-walk it.
4. **Local verify phase**: run `LC_ALL=C grep -P "[^\x00-\x7F]" docs/<file>.md` to confirm ASCII-only on the modified doc; run `git diff --stat origin/main..HEAD` to confirm exactly the two intended files changed with the expected line counts; run `uv run --with "apm-cli==0.12.1" apm compile && git diff --exit-code -- CLAUDE.md AGENTS.md` to confirm no APM artifact drift even though the diff did not touch universal source (this is a one-second positive control); run `python3 scripts/scan_apm_portability.py verify --path .apm/instructions/master.instructions.md --path CLAUDE.md --path AGENTS.md` to confirm the portability gate stays clean.
5. **Test phase**: run `uv run pytest -q` and quote the pass count in the PR body's `## Verification` block.
6. **Body phase**: copy `.github/PULL_REQUEST_TEMPLATE.md` and fill every section in order. Cite the closing issue with `Closes #NN` on the `Related Issue` line; add `Refs #<tracker>` when an umbrella issue exists. Commit subjects may use the looser `refs #NN` form; the body's `Closes` line is what binds the auto-close. Keep the body ASCII-safe so `preflight_non_ascii.py` (Layer 2.5) does not block subsequent automation that re-posts excerpts via `mcp__github__*` write tools.
7. **PR-template phase**: if the extension introduces a new reviewer-facing rule (PR #256's section 7), add at most one new checklist line to `.github/PULL_REQUEST_TEMPLATE.md` that points reviewers at the new section. Keep the line ASCII-safe and under the line-length convention of the surrounding bullets; this single-line addition stays well below the threshold that would trigger a template-policy repair.
8. **CI phase**: open the PR. The `verify-title-policy`, `verify-body-policy`, `verify-issue-link`, `verify-apm-drift`, `verify-apm-portability`, `scan-non-ascii`, `verify-agents` (correctly skipping), `lint-scripts` (correctly skipping for a no-Python diff), and `gate.yml` (pytest) gates run automatically. CI green means ready for merge.

## Gates exercised alongside this retrospective

| Gate | Outcome on PR #256 |
|---|---|
| `auto-retro.yml` (post-merge delivery from PR #237, hardened by PR #247) | Fired post-merge at `2026-05-24T01:28:54Z` on commit `c9665cd`; opened retro issue #258 successfully 9 seconds after merge. The opening was expected under the rules in effect at that moment: PR #254's "skip when source PR has zero inline review comments" rule (commit `53ae146`) merged at 2026-05-24T02:01:39Z, about 33 minutes after PR #256, so the skip rule was not yet on `main` when the workflow ran. The same-shape PR would now be skipped, and no follow-up issue is needed because the gate gap is already closed. |
| `verify-body-policy` (on issue #258) | Auto-opened body contains all five `_ISSUE_COMMON_REQUIRED` sections (`Scope`, `Facts`, `Proposed work`, `Verification`, `Acceptance criteria`); body-policy preflight passed on first read. |
| `is_retro_pr` skip rule (from PR #247) | The PR closing this retro (`docs(retro): ...`) is correctly skipped by `auto_retro.py` via the `(retro) in type-scope` branch, preventing a recursive retro-on-retro filing. |
| `find_existing_retro` PR-number match (tightened by PR #260, delivered via PR #261) | The tightened matcher correctly identifies retro issue #258 as the unique retro for source PR #256, preventing a duplicate retro from being opened on any subsequent re-trigger of the workflow on the same merge commit. |

## Follow-up issues

(none) -- no missing deterministic gate, unclear agent instruction, or external/human decision was surfaced by PR #256. The one observation worth noting (the auto-retro fired on a zero-review-comment merge) is already addressed on `main` by PR #254's skip rule, which merged 33 minutes after the source PR; no new issue is required.

## References

- Retro issue: [#258](https://github.com/tvna/claude-md/issues/258) (this document closes it).
- Source PR: [#256](https://github.com/tvna/claude-md/pull/256) (merge commit `c9665cd`).
- Closed issue: [#252](https://github.com/tvna/claude-md/issues/252).
- Parent tracker: [#226](https://github.com/tvna/claude-md/issues/226).
- Framework: CLAUDE.md section 3, codified in commit `daa5179` (#225).
- Sibling retrospectives: `retrospective-pr-229.md`, `retrospective-pr-235.md`, `retrospective-pr-237.md`, `retrospective-pr-248.md`, `retrospective-pr-249.md`.
- Auto-retrospective workflow: `.github/workflows/auto-retro.yml`, shipped by PR [#237](https://github.com/tvna/claude-md/pull/237) and hardened against retro-on-retro recursion by PR [#247](https://github.com/tvna/claude-md/pull/247); skip rule tightened further by PR [#254](https://github.com/tvna/claude-md/pull/254) (merged after PR #256) and PR-number matcher tightened by PR [#260](https://github.com/tvna/claude-md/pull/260) (delivered via PR [#261](https://github.com/tvna/claude-md/pull/261)).
- Source-PR feature: `docs/agent-rules-design-philosophy.md` (introduced by PR [#248](https://github.com/tvna/claude-md/pull/248) for #246; extended by PR #256 for #252).
