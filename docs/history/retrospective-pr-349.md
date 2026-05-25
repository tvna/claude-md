# Retrospective -- PR #349 GitHub Advisory Database Direct Query Repair-Free Merge

This document is the retrospective for [#353](https://github.com/tvna/claude-md/issues/353) -- the post-merge review of PR [#349](https://github.com/tvna/claude-md/pull/349), which closed issue [#172](https://github.com/tvna/claude-md/issues/172) (`query GitHub Advisory Database directly`) and refs deferred ecosystem-mapping work [#176](https://github.com/tvna/claude-md/issues/176). The retrospective framework lives in CLAUDE.md section 3: classify each pre-merge repair, identify the earliest deterministic gate that should have prevented it, and state the no-repair reproduction path for the next similar PR. This is a positive-control entry; zero pre-merge repairs were observed on the source PR.

Sections marked `TODO(operator)` require human synthesis (gate-narrative interpretation, reproduction-path inference, framework observation, follow-up gap analysis) and are explicitly left empty by the deterministic-only first pass per the issue #353 disposition. The fact-based sections (Scope, Repair history, Gates exercised, References) are filled from PR #349's GitHub API metadata and are safe to merge as-is.

## Scope

- Target PR: [#349](https://github.com/tvna/claude-md/pull/349), merged as commit `68bcd54` on 2026-05-25T08:52:11Z by `tvna`.
- Closed issue: [#172](https://github.com/tvna/claude-md/issues/172) -- the GHSA direct-query deliverable (third source in the threat intelligence triage pipeline, alongside OSV.dev aggregation and CISA KEV correlation).
- Refs: [#176](https://github.com/tvna/claude-md/issues/176) -- broader ecosystem and GitHub Actions enumeration, deferred per the PR `## Assumptions` block.
- Source branch: `claude/github-issue-172-pr-Ft3wq` -> `main`, head sha `11c7d421`.
- Files touched (5 total, +490 / -21):
  - `.github/workflows/threat-intel-triage.yml` (+1 / -0): adds `--ghsa-live` to the `scan` invocation.
  - `docs/issue-triage.md` (+7 / -1): names GHSA as a source and documents the malware-to-`threat:response-needed` escalation rule.
  - `scripts/threat_intel_triage.py` (+278 / -19): adds `fetch_ghsa_advisories`, `merge_findings`, `request_json_any`, `_summary_sources_line`; extends `Finding` with optional `advisory_type`; extends `classify_findings` with the malware escalation rule.
  - `tests/test_threat_intel_triage.py` (+202 / -0): four new cases covering GHSA matching, malware escalation, OSV/GHSA dedupe with source attribution, and the CLI summary surface.
  - `tests/test_workflow_cli_contracts.py` (+2 / -1): contract test forwards `--ghsa-live` and uses `**kwargs` on the monkeypatched `fetch_external_findings`.
- Out of scope: substance review of the GHSA query coverage or the malware escalation rule itself; those were accepted as-merged.

## Repair history

PR #349 landed via a single commit with **zero pre-merge repairs**. No PR-level comments, no review comments, no review threads, no failed CI check runs. The PR was open for approximately 2 hours and 1 minute (opened `2026-05-25T06:50:40Z`, merged `2026-05-25T08:52:11Z`).

| # | Repair | What the reviewer caught |
|---|---|---|
| -- | (none) | (none) |

Verified metadata at retrospective time (sourced from GitHub REST API on the head sha `11c7d421` and the merge commit `68bcd54`):

| Signal | Value |
|---|---|
| Commits | 1 |
| Files changed | 5 |
| Additions / Deletions | +490 / -21 |
| PR comments (`get_comments`) | 0 |
| Review threads (`get_review_comments`) | 0 |
| Reviews (`get_reviews`) | 0 |
| Check runs (`get_check_runs`) | 12 total: 10 success, 2 correctly skipped, 0 failure |
| Force-pushes | 0 (single commit; head sha matches the only commit subject) |

The auto-retro firing on this PR is the deterministic-correct behaviour under the gate state at merge time: PR #349 had zero review comments and zero review threads, but the `has_review_comments` skip rule for auto-retro (deployed by PR [#254](https://github.com/tvna/claude-md/pull/254)) checks review-comment counts before opening a retro. The retro was nonetheless opened; whether this indicates a remaining gate gap is left for the framework observation section below.

## Classification

<!-- TODO(operator): Per CLAUDE.md section 3 taxonomy ("missing deterministic gate / unclear agent instruction / external or human decision that cannot be automated"). With the repair set empty, this section restates the framework so the next retrospective writer has a template even when the positive-control case fires again. Mirror retrospective-pr-257.md section "Classification" if the framework wording is to be reused verbatim. -->

| Repair | Classification | Reasoning |
|---|---|---|
| -- | n/a | (operator: fill once the framework observation below is resolved) |

## Earliest prevention point

Gates exercised on first try without operator intervention (machine-listed from `get_check_runs` on the head sha; narrative interpretation deferred to operator):

- `Verify title policy / gate` -- accepted the PR title `feat(security): query GitHub Advisory Database directly` on first try.
- `Verify issue link / gate` -- accepted the `Closes #172` linkage on first try.
- `Verify ruleset sync / gate` -- accepted the workflow / ruleset diff on first try.
- `Verify agent instructions / gate` -- accepted the change without an APM compile delta (no `.apm/instructions/**`, `CLAUDE.md`, or `AGENTS.md` was touched).
- `verify` (apm-portability / body-policy short-circuit family, 2 runs) -- one ran clean, one correctly skipped via `paths:` filter.
- `audit` -- correctly skipped (recorded `skipped`) because no audit-relevant paths were touched.
- `detect` -- success (change detection pass).
- `prek` -- success (pre-commit hook surface).
- `lint-scripts` -- success (ruff / lint surface against the modified scripts/tests).
- `gate` -- success (pytest matrix; the PR body cites 1206 passed, total coverage 94.19% above the 92.71% floor).
- `open-retro` -- success (fired post-merge at `2026-05-25T08:52:17Z`, opened retro issue #353 in approximately 4 seconds).

<!-- TODO(operator): Reframe each gate above as "earliest deterministic gate that already enforced the no-repair path" with per-gate one-line justification (which gate would have caught which class of repair). See retrospective-pr-257.md section "Earliest prevention point" for the established narrative shape. -->

## No-repair reproduction path

<!-- TODO(operator): For the next PR that follows the same shape as #349 (delivering a third external source to the threat intelligence triage pipeline; adding a fetch function, a merge/dedupe helper, a CLI flag, fixture-mode tests, a contract-test update, and a runbook section in a single commit), enumerate the numbered steps to land in one shot. See retrospective-pr-257.md section "No-repair reproduction path" for the established 6-step shape (Plan / Edit / Local verify / Test / Body / CI). At minimum: cite the `Closes #` line, document the rate-limit and token assumptions in `## Assumptions` with `speculation:` tags, run the full pytest + ruff + mypy + prek matrix locally before opening, and write fixture-mode tests for any new external-network code path so CI does not depend on live network access. -->

## Gates exercised alongside this retrospective

| Gate | Outcome on PR #349 |
|---|---|
| `Verify title policy / gate` | success at 2026-05-25T08:07:55Z |
| `Verify issue link / gate` | success at 2026-05-25T08:07:56Z |
| `Verify ruleset sync / gate` | success at 2026-05-25T08:07:56Z |
| `Verify agent instructions / gate` | success at 2026-05-25T08:08:14Z |
| `verify` (apm-portability / body-policy short-circuit family) | success at 2026-05-25T08:08:01Z (one run); skipped at 2026-05-25T08:07:59Z (paired short-circuit run) |
| `audit` | skipped at 2026-05-25T08:07:48Z (no audit-relevant paths touched) |
| `detect` | success at 2026-05-25T08:07:59Z |
| `prek` | success at 2026-05-25T08:08:00Z |
| `lint-scripts` | success at 2026-05-25T08:08:08Z |
| `gate` (pytest matrix) | success at 2026-05-25T08:07:58Z |
| `open-retro` (post-merge) | success at 2026-05-25T08:52:24Z; opened retro issue #353 at 2026-05-25T08:52:21Z |

## Framework observation

<!-- TODO(operator): Decide whether the auto-retro firing on this zero-review-comment / zero-review-thread merge indicates a remaining gate gap (the `has_review_comments` skip rule from PR #254 evidently did not skip this case), or whether the current skip rule scope is intentional (e.g. the rule scope is "skip only when the merge has zero comments AND additional criteria not met here"). Read `scripts/auto_retro.py` skip predicates against the PR #349 metadata to confirm. If a gap is identified, file a follow-up issue in the section below. -->

## Follow-up issues

<!-- TODO(operator): list deferred gates as `- [ ] type(scope): TITLE -- RATIONALE` or write `(none)`. The deterministic-only first pass surfaced no gate gap that can be claimed without operator judgement on the framework observation above. -->

(operator: fill `(none)` or one or more `- [ ] type(scope): TITLE -- RATIONALE` bullets after resolving the framework observation)

## References

- Retro issue: [#353](https://github.com/tvna/claude-md/issues/353) (this document closes it).
- Source PR: [#349](https://github.com/tvna/claude-md/pull/349) (merge commit `68bcd54`).
- Closed issue: [#172](https://github.com/tvna/claude-md/issues/172).
- Refs: [#176](https://github.com/tvna/claude-md/issues/176) (broader ecosystem enumeration, deferred).
- Framework: CLAUDE.md section 3 (auto-open retrospective issue after each merge; classify repairs; name earliest prevention point; state no-repair reproduction path).
- Sibling retrospectives: `retrospective-pr-229.md`, `retrospective-pr-235.md`, `retrospective-pr-237.md`, `retrospective-pr-248.md`, `retrospective-pr-249.md`, `retrospective-pr-256.md`, `retrospective-pr-257.md`.
- Auto-retrospective workflow: `.github/workflows/auto-retro.yml` (shipped by PR [#237](https://github.com/tvna/claude-md/pull/237); hardened against retro-on-retro recursion by PR [#247](https://github.com/tvna/claude-md/pull/247); gated against zero-review-comment noise by PR [#254](https://github.com/tvna/claude-md/pull/254); PR-number-prefix-safe by PR [#261](https://github.com/tvna/claude-md/pull/261); auto-fill repair history by PR [#344](https://github.com/tvna/claude-md/pull/344)).

---

_This first pass was produced by a deterministic-only sweep on issue #353: only sections that can be filled from PR #349 GitHub API metadata are populated. Sections requiring narrative synthesis (Classification, Earliest prevention point narrative, No-repair reproduction path, Framework observation, Follow-up issues) are left as `TODO(operator)` placeholders for human completion._
