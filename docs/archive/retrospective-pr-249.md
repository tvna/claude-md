# Retrospective -- PR #249 Security-Drift Aggregator Repair-Free Merge

This document is the retrospective for [#251](https://github.com/tvna/claude-md/issues/251) -- the post-merge review of PR [#249](https://github.com/tvna/claude-md/pull/249), which closed issue [#180](https://github.com/tvna/claude-md/issues/180) ("ci(security): report security-control drift across families") and refs the parent tracker [#178](https://github.com/tvna/claude-md/issues/178). The retrospective framework lives in CLAUDE.md section 3: classify each pre-merge repair, identify the earliest deterministic gate that should have prevented it, and state the no-repair reproduction path for the next similar PR. This is a positive-control entry; zero repairs were observed, so the classification and prevention sections explain the no-repair path that the existing harness already delivers.

## Scope

- Target PR: [#249](https://github.com/tvna/claude-md/pull/249), merged as commit `c12c744` on 2026-05-24T01:12:32Z.
- Closed issue: [#180](https://github.com/tvna/claude-md/issues/180) -- ship a single aggregator that wires the existing per-family drift detectors (`ruleset_drift.py detect`, `labels_apply.py plan`, `apm compile` + `git diff`, `uv_pin.py drift` / `stale`) into the #178 MITRE ATT&CK coverage evidence without duplicating any detector.
- Parent tracker: [#178](https://github.com/tvna/claude-md/issues/178) -- umbrella issue for MITRE ATT&CK control coverage; the aggregator posts a single rolling comment on this issue.
- Out of scope: the substance of the merged `scripts/security_drift_report.py` / `.github/workflows/security-control-drift-report.yml` / `tests/test_security_drift_report.py` / `docs/security-control-drift-report.md` / `docs/security-control-inventory.md` edits -- those were accepted as-merged. The two `[ ]` post-merge verification items on PR #249's body (manual `dry_run=true` dispatch; first scheduled run) are operational follow-ups tracked on PR #249 itself, not framework gaps for this retrospective.

## Repair history

PR #249 landed via a single commit on branch `claude/github-issue-180-pr-q8itv` with **zero pre-merge repairs**. No reviewer comments, no PR-level comments, no review threads, and no failed CI check runs. The PR was open for 23 minutes 43 seconds (opened `2026-05-24T00:48:49Z`, merged `01:12:32Z` by `tvna`).

| # | Repair | What the reviewer caught |
|---|---|---|
| -- | (none) | (none) |

Diff at merge time: 5 files changed, +1502 / -7. Four new files (`scripts/security_drift_report.py`, `.github/workflows/security-control-drift-report.yml`, `tests/test_security_drift_report.py`, `docs/security-control-drift-report.md`) plus one modified inventory cross-link (`docs/security-control-inventory.md`). The merge into `main` is itself the strongest evidence that all required checks listed in `.github/rulesets/main.json` reported green on first try, since the ruleset blocks merges on red required checks. The `auto-retro.yml` workflow fired post-merge and opened this retrospective's source issue (#251) 8 seconds after merge.

## Classification

Per CLAUDE.md section 3 taxonomy ("missing deterministic gate / unclear agent instruction / external or human decision that cannot be automated"):

| Repair | Classification | Reasoning |
|---|---|---|
| -- | n/a | The repair set is empty, so no entry maps into any of the three categories. The classification framework is restated here so the next retrospective writer has a template even when the positive-control case fires again. |

## Earliest prevention point

Reframed for the positive-control case as "earliest deterministic gates that already enforced the no-repair path." Each gate fired on first try with no operator intervention:

- **`verify-title-policy.yml`** accepted the title `ci(security): report security-control drift across families` against its conventional-commit regex on first try.
- **`verify-body-policy.yml`** accepted the PR body section structure (Summary, Related Issue, Facts, Assumptions, Risk & blast radius, Rollback, Verification, Checklist) on first try. This gate was paid down by PR #220 and remains the most likely place a future similar PR would regress.
- **`verify-issue-link.yml`** resolved `Closes #180` (and `Refs #178`) and pinned the close-on-merge linkage on first try. The `Refs #178` line correctly did NOT trigger an auto-close on the umbrella tracker, because `#178` carries the `type:tracking` label.
- **`verify-apm-drift.yml`** confirmed source-output equivalence: the diff did not touch `.apm/instructions/master.instructions.md`, so the compiled `CLAUDE.md` / `AGENTS.md` artifacts stayed in sync without a regeneration step. The PR body explicitly recorded the verification command `uv run --with "apm-cli==0.12.1" --exclude-newer "14 days" apm compile && git diff --exit-code -- CLAUDE.md AGENTS.md`.
- **`verify-apm-portability.yml`** ran clean: the new aggregator, workflow, tests, runbook, and the cross-link edits in `docs/security-control-inventory.md` introduced no agent-rule paths that would leak repo-local references into a standalone downstream consumer.
- **`scan-non-ascii.yml`** raised no advisory: the PR body and the four new files were ASCII-only, and the modified `docs/security-control-inventory.md` only retained pre-existing em-dashes already consistent with the rest of that file. The PR body recorded this explicitly under `## Verification` (`All five touched files reviewed for non-ASCII`).
- **`verify-agents.yml`** detect job correctly short-circuited because no `.apm/instructions/**` path was touched, avoiding an unnecessary compile-and-diff pass.
- **`lint-scripts.yml`** ran ruff + mypy against the new `scripts/security_drift_report.py` and the new `tests/test_security_drift_report.py` and reported clean on first try.
- **`gate.yml`** (pytest matrix) ran the 754-test suite (699 pre-existing + 55 net-new for the aggregator across pure / IO / CLI layers) with zero regressions.

## No-repair reproduction path

For the next PR that follows the same shape as #249 (net-new aggregator script + scheduled workflow + tests + runbook, plus a single minimal cross-link edit in one inventory doc, with no touch to agent rules or compiled artifacts), the path to a repair-free merge is:

1. **Plan phase**: enumerate facts and assumptions in the PR body before writing code; tag every line that is a guess with `speculation:` so reviewers see the surface area immediately (CLAUDE.md section 2). When reusing an existing secret (`RULESETS_PAT`) for a new caller, record the reuse rationale up front and link the existing workflow that already requires the same secret for the same call -- this prevents reviewers from asking "why does this aggregator need a PAT?".
2. **Edit phase**: keep the aggregator read-only across all callers (`ruleset_drift.py detect`, `labels_apply.py plan`, `apm compile`, `uv_pin.py drift`, `uv_pin.py stale`). State the write-surface boundary in the runbook as "single GitHub issue comment on the parent tracker; no `POST /repos/.../issues` code path" so reviewers can verify by `grep`. Touch sibling docs only with minimal cross-link edits on the inventory rows the new aggregator now covers; do not refactor adjacent rows.
3. **Cron offset phase**: when adding a scheduled workflow that reuses existing detectors invoked by other crons, pick a cron slot that does not collide on the shared detector calls. PR #249 chose `0 23 * * 0`, offset +2h from `ruleset-drift.yml` (`0 21 * * 0`) and +3h from `branch-cleanup.yml` (`0 20 * * 0`). Record the offsets in the PR body's `## Facts` block so the reviewer does not have to compute them.
4. **Local verify phase**: run `LC_ALL=C grep -P "[^\x00-\x7F]" <new-files>` to confirm ASCII-only on the net-new files; run `git diff --stat origin/main..HEAD` to confirm no APM artifact drift; run `python3 scripts/uv_pin.py drift` to confirm no dependency drift.
5. **Test phase**: run `uv run --group dev pytest -q tests/test_<new_module>.py` (targeted) AND `uv run --group dev pytest -q` (full); report both numbers in the PR body's `## Verification` block (PR #249 reported `55 passed` and `754 passed`).
6. **Workflow input phase**: default any `workflow_dispatch` input that controls a write to the reversible side (PR #249 set `dry_run=true` as the default, so a manual run never posts a comment unless the operator opts in). State this in the runbook and the PR body so the reviewer does not need to read the workflow yaml to verify.
7. **Body phase**: copy `.github/PULL_REQUEST_TEMPLATE.md` and fill every section in order. Cite the closing issue with `Closes #NN` and the parent tracker with `Refs #<tracker>`. Keep the body ASCII-safe so `preflight_non_ascii.py` does not block subsequent automation that re-posts excerpts via `mcp__github__*` write tools.
8. **CI phase**: open the PR. The `verify-title-policy`, `verify-body-policy`, `verify-issue-link`, `verify-apm-drift`, `verify-apm-portability`, `scan-non-ascii`, `verify-agents` (correctly skipping), `lint-scripts`, and `gate.yml` (pytest) gates run automatically. CI green means ready for merge.

## Gates exercised alongside this retrospective

| Gate | Outcome on PR #249 |
|---|---|
| `auto-retro.yml` (post-merge delivery from PR #237, hardened by PR #247) | Fired post-merge at `2026-05-24T01:12:40Z` on commit `c12c744`; opened retro issue #251 successfully 8 seconds after merge. This single observation confirms the auto-retro path stays green for the "aggregator + scheduled workflow + tests + runbook + inventory cross-link" PR shape. |
| `verify-body-policy` (on issue #251) | Auto-opened body contains all five `_ISSUE_COMMON_REQUIRED` sections (`Scope`, `Facts`, `Proposed work`, `Verification`, `Acceptance criteria`). |
| `is_retro_pr` skip rule (from PR #247) | The PR closing this retro (`docs(retro): ...`) is correctly skipped by `auto_retro.py` via the `(retro) in type-scope` branch, preventing a recursive retro-on-retro filing. |
| `aggregator never opens issues` invariant (the PR's own delivery) | Encoded as a unit-test assertion in `tests/test_security_drift_report.py` and as a runbook statement in `docs/security-control-drift-report.md`; reviewable by `grep -n "POST /repos" scripts/security_drift_report.py` returning only the single comment-create call on the parent tracker. |

## Follow-up issues

(none) -- no missing deterministic gate, unclear agent instruction, or external/human decision was surfaced by PR #249. The no-repair outcome is the artifact.

The two `[ ]` post-merge verification items on PR #249's body (manual `dry_run=true` dispatch confirming the step summary renders the family table; first scheduled run on Mon 08:00 JST confirming the rolling comment posts on #178 and the second run patches in place) remain operational confirmations on PR #249 itself. They are tracked there and do not require a separate issue; the next scheduled cron run is the natural verification trigger.

## References

- Retro issue: [#251](https://github.com/tvna/claude-md/issues/251) (this document closes it).
- Source PR: [#249](https://github.com/tvna/claude-md/pull/249) (merge commit `c12c744`).
- Closed issue: [#180](https://github.com/tvna/claude-md/issues/180).
- Parent tracker: [#178](https://github.com/tvna/claude-md/issues/178).
- Framework: CLAUDE.md section 3, codified in commit `daa5179` (#225).
- Sibling retrospectives: `retrospective-pr-229.md`, `retrospective-pr-235.md`, `retrospective-pr-237.md`, `retrospective-pr-248.md`.
- Auto-retrospective workflow: `.github/workflows/auto-retro.yml`, shipped by PR [#237](https://github.com/tvna/claude-md/pull/237) and hardened against retro-on-retro recursion by PR [#247](https://github.com/tvna/claude-md/pull/247); skip rule tightened further by PR [#254](https://github.com/tvna/claude-md/pull/254) and PR-number matcher tightened by PR [#260](https://github.com/tvna/claude-md/pull/260) (delivered via PR [#261](https://github.com/tvna/claude-md/pull/261)).
