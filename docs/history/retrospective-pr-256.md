# Retrospective -- PR #256 Agent-Rules Checklist Followup Repair-Free Merge

This document is the retrospective for [#258](https://github.com/tvna/claude-md/issues/258) -- the post-merge review of PR [#256](https://github.com/tvna/claude-md/pull/256), which closed issue [#252](https://github.com/tvna/claude-md/issues/252) ("docs(agent-rules): consume 226 checklist items 2 to 4") and refs the parent tracker [#226](https://github.com/tvna/claude-md/issues/226). The retrospective framework lives in CLAUDE.md section 3: classify each pre-merge repair, identify the earliest deterministic gate that should have prevented it, and state the no-repair reproduction path for the next similar PR. This is a positive-control entry; zero repairs were observed, so the classification and prevention sections explain the no-repair path that the existing harness already delivers. One framework-level observation about the auto-retro firing itself is recorded below.

## Scope

- Target PR: [#256](https://github.com/tvna/claude-md/pull/256), merged as commit `c9665cd` on 2026-05-24T01:28:45Z.
- Closed issue: [#252](https://github.com/tvna/claude-md/issues/252) -- the followup tracker for the three remaining checklist items in #226 (retrospective findings to action lanes, separate examples doc decision, instruction-PR review criteria).
- Parent tracker: [#226](https://github.com/tvna/claude-md/issues/226) -- the umbrella issue for the agent-rules redesign workstream.
- Out of scope: the substance of the new section 6.4 / section 7 additions to `docs/agent-rules-design-philosophy.md` (+150/-6) and the single new checklist item appended to `.github/PULL_REQUEST_TEMPLATE.md` (+1/-0) -- those were accepted as-merged.

## Repair history

PR #256 landed via two commits (`df29391` followed by `e770209`) on branch `claude/agent-rules-followup-226-items-2-4` with **zero pre-merge repairs**. No reviewer comments, no PR-level comments, no review threads, and no failed CI check runs. The PR was open for ~2.5 minutes (opened `2026-05-24T01:26:16Z`, merged `2026-05-24T01:28:45Z`).

| # | Repair | What the reviewer caught |
|---|---|---|
| -- | (none) | (none) |

Observed CI surface at merge time: ten check runs across the open and merge events, all reporting `success` except two that correctly reported `skipped` (`verify` and `audit` short-circuited because the diff did not touch APM source or `dependabot[bot]` paths). The `open-retro` check fired on the merge commit at `2026-05-24T01:28:49Z` and produced retrospective issue #258 in 7 seconds.

Framework observation: the `open-retro` firing on a zero-review-comment merge was the deterministic-correct behaviour under the harness state at PR #256's merge time. The zero-review-comment skip rule shipped by PR [#254](https://github.com/tvna/claude-md/pull/254) merged at `2026-05-24T02:01:39Z`, approximately 33 minutes after PR #256 -- so the gate that would have prevented #258 from being filed did not yet exist on `main`. The same lag also produced sibling retro issue #259 for PR #257. Both are pre-#254 artifacts and are not classified as repairs to PR #256 itself.

## Classification

Per CLAUDE.md section 3 taxonomy ("missing deterministic gate / unclear agent instruction / external or human decision that cannot be automated"):

| Repair | Classification | Reasoning |
|---|---|---|
| -- | n/a | The repair set is empty, so no entry maps into any of the three categories. The classification framework is restated here so the next retrospective writer has a template even when the positive-control case fires again. The framework-level observation above (auto-retro firing on a zero-comment merge) is not a repair to PR #256; the missing gate was already filed as #253 and closed by PR #254, so it requires no fresh classification entry. |

## Earliest prevention point

Reframed for the positive-control case as "earliest deterministic gates that already enforced the no-repair path." Each gate fired on first try with no operator intervention:

- **`verify-title-policy.yml`** accepted the title `docs(agent-rules): consume 226 checklist items 2 to 4` against its conventional-commit regex on first try.
- **`verify-body-policy.yml`** accepted the PR body section structure (Summary, Related Issue, Facts, Assumptions, Risk & blast radius, Rollback, Verification, Checklist) on first try. The body explicitly distinguished Facts from Assumptions (three lines tagged `Speculation:` in the Assumptions block), satisfying the section 2 facts-vs-speculation split that PR #220 codified.
- **`verify-issue-link.yml`** resolved `Closes #252` on the `Related Issue` line and pinned the close-on-merge linkage on first try.
- **`verify-apm-drift.yml`** confirmed source-output equivalence: the diff did not touch `.apm/instructions/master.instructions.md`, so the compiled `CLAUDE.md` / `AGENTS.md` artifacts stayed in sync without a regeneration step. The workflow `verify` job correctly short-circuited via its `paths:` filter.
- **`verify-apm-portability.yml`** ran clean: the two touched files introduced no repo-local references that would leak into a standalone downstream consumer of the compiled rules; the new section 7 explicitly governs APM-portability review for future PRs.
- **`scan-non-ascii.yml`** raised no advisory because the PR body and the two touched files stayed within the ASCII boundary the policy enforces.
- **`verify-agents.yml`** `audit` job correctly short-circuited (recorded `skipped`) because no `.apm/instructions/**` or `scripts/**` path was touched, avoiding an unnecessary compile-and-diff pass.
- **`lint-scripts.yml`** had no Python source to lint in this diff and short-circuited cleanly.
- **`gate.yml`** (pytest matrix) ran the 769-test suite with zero regressions, as quoted in the PR `## Verification` block.

## No-repair reproduction path

For the next PR that follows the same shape as #256 (consuming a tracker checklist by extending an existing doc under `docs/`, with at most a single one-line touch to `.github/PULL_REQUEST_TEMPLATE.md`, and no touch to `.apm/**`, `scripts/**`, `CLAUDE.md`, or `AGENTS.md`), the path to a repair-free merge is:

1. **Plan phase**: enumerate the specific tracker checklist items being consumed in the PR `## Summary` (e.g. "items 2, 3, 4 of #226"); for each item, point to the section of the existing doc that already cross-links to the item's intent so reviewers can verify the extension lands in the right place. Tag every line that is a guess with `Speculation:` in `## Assumptions` (CLAUDE.md section 2) -- this PR landed with three explicit speculations on discoverability, colocation, and anchor-link stability.
2. **Edit phase**: extend the existing doc with the new sections in place (do not extract them to a new file unless the doc's non-goals authorise the split); renumber any sections that shift and update internal section-reference text in the same commit so the diff is self-consistent. For PR-template touches, keep the addition to a single checklist line that points back to the doc, not to inline criteria.
3. **Local verify phase**: run `LC_ALL=C grep -nP "[^\x00-\x7F]" docs/<edited-file>.md` to confirm ASCII-only; run `git diff --stat origin/main..HEAD` to confirm the file list matches intent; run `uv sync --locked && uv run --with "apm-cli==<pinned-version>" apm compile` to confirm zero-diff against `CLAUDE.md` and `AGENTS.md`; run `python3 scripts/scan_apm_portability.py verify --path .apm/instructions/master.instructions.md --path CLAUDE.md --path AGENTS.md` and confirm exit 0.
4. **Test phase**: run `uv run pytest -q` and quote the pass count in the PR body's `## Verification` block.
5. **Body phase**: copy `.github/PULL_REQUEST_TEMPLATE.md` and fill every section in order. Cite the closing issue with `Closes #NN` on the `Related Issue` line; add `Refs #<tracker>` only when the umbrella issue must stay open after merge. Keep the body ASCII-safe so `preflight_non_ascii.py` does not block subsequent automation that re-posts excerpts via `mcp__github__*` write tools.
6. **CI phase**: open the PR. The `verify-title-policy`, `verify-body-policy`, `verify-issue-link`, `verify-apm-drift`, `verify-apm-portability`, `scan-non-ascii`, `verify-agents` (correctly skipping), `lint-scripts` (correctly skipping), and `gate.yml` (pytest) gates run automatically. CI green means ready for merge.

## Gates exercised alongside this retrospective

| Gate | Outcome on PR #256 |
|---|---|
| `auto-retro.yml` (post-merge delivery from PR #237) | Fired post-merge at `2026-05-24T01:28:49Z` on commit `c9665cd`; opened retro issue #258 successfully. The firing was deterministic-correct under the gate state at this merge -- the zero-review-comment skip rule had not yet been deployed. |
| `verify-body-policy` (on issue #258) | Auto-opened body contains all five `_ISSUE_COMMON_REQUIRED` sections (`Scope`, `Facts`, `Proposed work`, `Verification`, `Acceptance criteria`). |
| `has_review_comments` skip rule (PR #254 fix, deployed AFTER PR #256) | Would now skip an auto-retro opening for an equivalent zero-review-comment merge. The rule's deployment lag explains why issues #258 and #259 exist; future similar PRs will be skipped at source. |
| `is_retro_pr` skip rule (PR #247 fix) | The PR closing this retro (`docs(retro): ...`) is correctly skipped by `auto_retro.py` via the `(retro) in type-scope` branch, preventing a recursive retro-on-retro filing. |
| `find_existing_retro` PR-number lookahead (PR #260 fix, deployed AFTER PR #256) | Hardens the duplicate-retro search against numeric prefix collisions. Not directly exercised here because no sibling PR number with #256 as a prefix existed at search time, but logged as a relevant subsequent harness improvement. |

## Follow-up issues

(none) -- the only deterministic gate gap surfaced by PR #256 (auto-retro firing on zero-review-comment merges) was already filed as #253 and closed by PR #254 before this retrospective was written. No new gate, instruction, or human decision is required to reproduce the no-repair path on the next similar PR.

## References

- Retro issue: [#258](https://github.com/tvna/claude-md/issues/258) (this document closes it).
- Source PR: [#256](https://github.com/tvna/claude-md/pull/256) (merge commit `c9665cd`).
- Closed issue: [#252](https://github.com/tvna/claude-md/issues/252).
- Parent tracker: [#226](https://github.com/tvna/claude-md/issues/226).
- Framework: CLAUDE.md section 3, codified in commit `daa5179` (#225).
- Sibling retrospectives: `retrospective-pr-229.md`, `retrospective-pr-235.md`, `retrospective-pr-237.md`, `retrospective-pr-248.md`.
- Auto-retrospective workflow: `.github/workflows/auto-retro.yml`, shipped by PR [#237](https://github.com/tvna/claude-md/pull/237), hardened against retro-on-retro recursion by PR [#247](https://github.com/tvna/claude-md/pull/247), gated against zero-review-comment noise by PR [#254](https://github.com/tvna/claude-md/pull/254), and PR-number-prefix-safe by PR [#261](https://github.com/tvna/claude-md/pull/261) (closes #260).
