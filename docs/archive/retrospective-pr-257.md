# Retrospective -- PR #257 Workflow Permissions Audit Repair-Free Merge

This document is the retrospective for [#259](https://github.com/tvna/claude-md/issues/259) -- the post-merge review of PR [#257](https://github.com/tvna/claude-md/pull/257), which closed issue [#181](https://github.com/tvna/claude-md/issues/181) (`workflow permissions and PAT audit (least privilege matrix)`) and Refs the parent tracker [#178](https://github.com/tvna/claude-md/issues/178) (MITRE ATT&CK coverage tracking) and [#56](https://github.com/tvna/claude-md/issues/56) (PAT handling). The retrospective framework lives in CLAUDE.md section 3: classify each pre-merge repair, identify the earliest deterministic gate that should have prevented it, and state the no-repair reproduction path for the next similar PR. This is a positive-control entry; zero repairs were observed, so the classification and prevention sections explain the no-repair path that the existing harness already delivers. One framework-level observation about the auto-retro firing itself is recorded below.

## Scope

- Target PR: [#257](https://github.com/tvna/claude-md/pull/257), merged as commit `7a00f68` on 2026-05-24T01:29:34Z.
- Closed issue: [#181](https://github.com/tvna/claude-md/issues/181) -- the workflow permissions audit deliverable (least privilege matrix across every `.github/workflows/*.yml`).
- Refs: [#178](https://github.com/tvna/claude-md/issues/178) (MITRE ATT&CK coverage parent tracker) and [#56](https://github.com/tvna/claude-md/issues/56) (PAT handling).
- Companion doc referenced by the audit: `docs/security-control-inventory.md` (the #179 surface inventory baseline).
- Out of scope: the substance of the new permission matrix in `docs/workflow-permissions-audit.md` (+134/-0) -- the audit table was accepted as-merged. Applying the narrowing fixes the matrix flags (over-grants on `generate-agents.yml`, `verify-agents.yml`, `threat-intel-triage.yml`, `verify-issue-link.yml`) is tracked back to #181 as the open work item per the PR body, and is not the subject of this retrospective.

## Repair history

PR #257 landed via a single commit on branch `claude/github-issue-181-pr-ifRHt` with **zero pre-merge repairs**. No reviewer comments, no PR-level comments, no review threads, and no failed CI check runs. The PR was open for approximately 53 seconds (opened `2026-05-24T01:28:41Z`, merged `2026-05-24T01:29:34Z`).

| # | Repair | What the reviewer caught |
|---|---|---|
| -- | (none) | (none) |

Observed CI surface at merge time: ten check runs across the open and merge events, all reporting `success` except two that correctly reported `skipped` (`verify` and `audit` short-circuited because the diff did not touch APM source or `dependabot[bot]` paths). The `open-retro` check fired on the merge commit at `2026-05-24T01:29:38Z` and produced retrospective issue #259 in 5 seconds.

Framework observation: the `open-retro` firing on a zero-review-comment merge was the deterministic-correct behaviour under the harness state at PR #257's merge time. The zero-review-comment skip rule shipped by PR [#254](https://github.com/tvna/claude-md/pull/254) merged at `2026-05-24T02:01:39Z`, approximately 32 minutes after PR #257 -- so the gate that would have prevented #259 from being filed did not yet exist on `main`. The same lag also produced sibling retro issue #258 for PR #256. Both are pre-#254 artifacts and are not classified as repairs to PR #257 itself.

## Classification

Per CLAUDE.md section 3 taxonomy ("missing deterministic gate / unclear agent instruction / external or human decision that cannot be automated"):

| Repair | Classification | Reasoning |
|---|---|---|
| -- | n/a | The repair set is empty, so no entry maps into any of the three categories. The classification framework is restated here so the next retrospective writer has a template even when the positive-control case fires again. The framework-level observation above (auto-retro firing on a zero-comment merge) is not a repair to PR #257; the missing gate was already filed as #253 and closed by PR #254, so it requires no fresh classification entry. |

## Earliest prevention point

Reframed for the positive-control case as "earliest deterministic gates that already enforced the no-repair path." Each gate fired on first try with no operator intervention:

- **`verify-title-policy.yml`** accepted the title `docs(security): audit workflow permissions` against its conventional-commit regex on first try.
- **`verify-body-policy.yml`** accepted the PR body section structure (Summary, Related Issue, Facts, Assumptions, Risk & blast radius, Rollback, Verification, Checklist) on first try. The body explicitly distinguished Facts from Assumptions (four lines tagged `speculation:` in the Assumptions block: rg-coverage absorption, audit-only scope, follow-up-issue reuse, and companion-inventory deferral), satisfying the section 2 facts-vs-speculation split that PR #220 codified.
- **`verify-issue-link.yml`** resolved `Closes #181` on the `Related Issue` line and pinned the close-on-merge linkage on first try. `Refs #178, #56` were also recognised on the same line without breaking the close-keyword parse.
- **`verify-apm-drift.yml`** confirmed source-output equivalence: the diff did not touch `.apm/instructions/master.instructions.md`, so the compiled `CLAUDE.md` / `AGENTS.md` artifacts stayed in sync without a regeneration step. The workflow `verify` job correctly short-circuited via its `paths:` filter.
- **`verify-apm-portability.yml`** ran clean: the one new file did not modify universal APM source, so the standalone-downstream-consumer surface was unchanged.
- **`scan-non-ascii.yml`** raised no advisory because the PR body and the single touched file stayed within the ASCII boundary the policy enforces.
- **`verify-agents.yml`** `audit` job correctly short-circuited (recorded `skipped`) because no `.apm/instructions/**` or `scripts/**` path was touched, avoiding an unnecessary compile-and-diff pass.
- **`lint-scripts.yml`** had no Python source to lint in this diff and short-circuited cleanly.
- **`gate.yml`** (pytest matrix) ran with zero regressions, as quoted in the PR `## Verification` block.

## No-repair reproduction path

For the next PR that follows the same shape as #257 (delivering a documentation-only security audit by adding a single new file under `docs/`, with no touch to `.apm/**`, `scripts/**`, `.github/workflows/**`, `CLAUDE.md`, or `AGENTS.md`, and reusing existing follow-up issues rather than opening new ones), the path to a repair-free merge is:

1. **Plan phase**: enumerate the specific `Deliverable` section of the closing issue in the PR `## Summary` (e.g. "the seven columns required by #181's Deliverable section"); for each column, point to the inference rule or evidence source that populates it so reviewers can refute it row by row. Tag every line that is a guess with `speculation:` in `## Assumptions` (CLAUDE.md section 2) -- this PR landed with four explicit speculations on coverage absorption, audit-only scope, follow-up reuse, and companion-doc deferral.
2. **Edit phase**: write the audit table with all required columns stated up front and the inference rules stated above the table (so reviewers can challenge a single classification without rereading the whole doc). Reuse existing follow-up issue numbers from the parent tracker -- the audit cites them but does not open new ones, per the #178 "reuse instead of duplicate" rule. Keep the diff to a single new file; do not refactor or extend sibling docs (e.g. `docs/security-control-inventory.md`) in the same PR even when the audit surfaces a delta -- defer the inventory resync to its own PR.
3. **Local verify phase**: run `LC_ALL=C grep -nP "[^\x00-\x7F]" docs/<new-audit-file>.md` to confirm ASCII-only; run `git diff --stat origin/main..HEAD` to confirm the file list matches intent (exactly one new file under `docs/`); run `uv sync --locked && uv run --with "apm-cli==<pinned-version>" apm compile` to confirm zero-diff against `CLAUDE.md` and `AGENTS.md`; run `python3 scripts/scan_apm_portability.py verify --path .apm/instructions/master.instructions.md --path CLAUDE.md --path AGENTS.md` and confirm exit 0.
4. **Test phase**: run `uv run pytest -q` and quote the pass count in the PR body's `## Verification` block.
5. **Body phase**: copy `.github/PULL_REQUEST_TEMPLATE.md` and fill every section in order. Cite the closing issue with `Closes #NN` on the `Related Issue` line; add `Refs #<parent-tracker>, #<related-tracker>` only when the umbrella issues must stay open after merge. For audits that surface gaps tracked by sibling issues (e.g. #56, #170, #178, #182, #183), list them in the audit's own `## Gap summary` table inside the doc rather than re-listing them in the PR body -- this keeps the doc self-describing for downstream consumers. Keep the body ASCII-safe so `preflight_non_ascii.py` does not block subsequent automation that re-posts excerpts via `mcp__github__*` write tools.
6. **CI phase**: open the PR. The `verify-title-policy`, `verify-body-policy`, `verify-issue-link`, `verify-apm-drift`, `verify-apm-portability`, `scan-non-ascii`, `verify-agents` (correctly skipping), `lint-scripts` (correctly skipping), and `gate.yml` (pytest) gates run automatically. CI green means ready for merge.

## Gates exercised alongside this retrospective

| Gate | Outcome on PR #257 |
|---|---|
| `auto-retro.yml` (post-merge delivery from PR #237) | Fired post-merge at `2026-05-24T01:29:38Z` on commit `7a00f68`; opened retro issue #259 successfully. The firing was deterministic-correct under the gate state at this merge -- the zero-review-comment skip rule had not yet been deployed. |
| `verify-body-policy` (on issue #259) | Auto-opened body contains all five `_ISSUE_COMMON_REQUIRED` sections (`Scope`, `Facts`, `Proposed work`, `Verification`, `Acceptance criteria`). |
| `has_review_comments` skip rule (PR #254 fix, deployed AFTER PR #257) | Would now skip an auto-retro opening for an equivalent zero-review-comment merge. The rule's deployment lag explains why issues #258 and #259 exist; future similar PRs will be skipped at source. |
| `is_retro_pr` skip rule (PR #247 fix) | The PR closing this retro (`docs(retro): ...`) is correctly skipped by `auto_retro.py` via the `(retro) in type-scope` branch, preventing a recursive retro-on-retro filing. |
| `find_existing_retro` PR-number lookahead (PR #261 fix, deployed AFTER PR #257) | Hardens the duplicate-retro search against numeric prefix collisions. Not directly exercised here because no sibling PR number with #257 as a prefix existed at search time, but logged as a relevant subsequent harness improvement. |

## Follow-up issues

(none) -- the only deterministic gate gap surfaced by PR #257 (auto-retro firing on zero-review-comment merges) was already filed as #253 and closed by PR #254 before this retrospective was written. The over-grant rows surfaced by the audit itself (rows for `generate-agents.yml`, `verify-agents.yml`, `threat-intel-triage.yml`, `verify-issue-link.yml`) are already tracked under the closing issue #181 by intent (the audit is the deliverable for #181; remediation work was scoped out by design and remains under #181's own follow-up). No new gate, instruction, or human decision is required to reproduce the no-repair path on the next similar audit-only PR.

## References

- Retro issue: [#259](https://github.com/tvna/claude-md/issues/259) (this document closes it).
- Source PR: [#257](https://github.com/tvna/claude-md/pull/257) (merge commit `7a00f68`).
- Closed issue: [#181](https://github.com/tvna/claude-md/issues/181).
- Refs: [#178](https://github.com/tvna/claude-md/issues/178), [#56](https://github.com/tvna/claude-md/issues/56).
- Companion doc cited by the audit: `docs/security-control-inventory.md` (#179 surface inventory baseline).
- Framework: CLAUDE.md section 3, codified in commit `daa5179` (#225).
- Sibling retrospectives: `retrospective-pr-229.md`, `retrospective-pr-235.md`, `retrospective-pr-237.md`, `retrospective-pr-248.md`, `retrospective-pr-249.md`, `retrospective-pr-256.md`.
- Auto-retrospective workflow: `.github/workflows/auto-retro.yml`, shipped by PR [#237](https://github.com/tvna/claude-md/pull/237), hardened against retro-on-retro recursion by PR [#247](https://github.com/tvna/claude-md/pull/247), gated against zero-review-comment noise by PR [#254](https://github.com/tvna/claude-md/pull/254), and PR-number-prefix-safe by PR [#261](https://github.com/tvna/claude-md/pull/261) (closes #260).
