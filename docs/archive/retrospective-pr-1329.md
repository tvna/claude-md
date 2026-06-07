# Retrospective -- PR #1329 Workflow Consolidation Repair Audit

This document closes retrospective issue
[#1339](https://github.com/tvna/claude-md/issues/1339) for source PR
[#1329](https://github.com/tvna/claude-md/pull/1329), which closed issue
[#1319](https://github.com/tvna/claude-md/issues/1319). The framework is
CLAUDE.md section 3: list every repair required between PR intent and a clean
main, identify the earliest deterministic gate that should have prevented each
repair, classify each repair, and state how the next run reproduces the
no-repair path.

## Scope

- Source PR: [#1329](https://github.com/tvna/claude-md/pull/1329)
  (`ci: consolidate workflow files by trigger class`).
- Merge: squash commit `8cf871e`, merged on 2026-06-07T02:50:20Z by `tvna`.
- Closed issue: [#1319](https://github.com/tvna/claude-md/issues/1319).
- Follow-up issue:
  [#1325](https://github.com/tvna/claude-md/issues/1325), stale non-link
  workflow filename references after the consolidation.
- Follow-up PR:
  [#1333](https://github.com/tvna/claude-md/pull/1333), merged as
  `5c09b18`, repointed stale references and added the deterministic
  doc-workflow-reference gate.
- Retro issue: [#1339](https://github.com/tvna/claude-md/issues/1339)
  (this archive entry closes it).

## Facts vs speculation

- fact: PR #1329 merged as a single squash commit `8cf871e`; `git diff --stat`
  reported 34 files changed, 510 insertions, and 647 deletions; workflow files
  went from 27 to 20.
- fact: PR #1329 in-PR CI was clean: all 31 check runs were `success` or
  `skipped`, with no failures.
- fact: the consolidation deleted 10 workflow files; about 30 path-form plus
  many bare inline-code references to those deleted filenames survived across
  PRD, standards, runbook docs, and the PR template. This was tracked as
  #1325.
- fact: no pre-merge deterministic gate caught those references.
  `scan_markdown_links` validates links and `scan_docs_inventory` validates
  index coverage; neither inspected inline-code workflow paths at the time.
- fact: at the time issue #1339 was authored, follow-up commit `b2b3151` lived
  on session branch `claude/confident-keller-6VQK0` and was not yet in main.
  It later landed through PR #1333 as merge commit `5c09b18`.
- fact: PR #1333 added `scripts/scan_doc_workflow_refs.py`, wired it into
  `verify-agents.yml` (`lint-scripts-static`) and `scripts/preflight_all.py`,
  and fixed pre-existing `verify-title-policy` / `auto-retro` reference drift
  surfaced by the new gate.
- speculation: the operator's "CI error handling" dissatisfaction theme maps
  to the gate-surfaced drift handled during the follow-up rather than to
  #1329 itself, whose CI was green.
- speculation: the "scope too large" dissatisfaction theme refers to the
  34-file consolidation PR landing as one unit.

## Repair log

| # | Repair | Earliest prevention point | Classification | Next-run no-repair path |
|---|---|---|---|---|
| 1 | Post-merge doc-reference drift: deleted workflow filenames remained referenced across non-archive docs and the PR template, pointing readers at files that no longer existed. | No gate existed pre-merge. The consolidation removed files that docs cited, but no gate validated inline-code `.github/workflows/<name>.yml` references. | missing deterministic gate | PR #1333 added `scripts/scan_doc_workflow_refs.py`, which fails when a non-archive Markdown doc cites a nonexistent `.github/workflows/<name>.yml` path. It now runs in `lint-scripts-static` and `preflight_all.py`, so future workflow rename/delete work must repoint docs before merge. |
| 2 | Scope split along the wrong boundary: file deletions landed in #1329 while the mandatory doc-reference repoint was deferred to #1325, opening a window on main where docs pointed at deleted files. | Same missing gate as row 1. A doc-ref gate would have failed #1329 itself and forced the repoint into the same PR rather than allowing the orphan boundary. | unclear agent instruction / scoping decision, with human judgment on PR size | With `scan_doc_workflow_refs.py` enforced, scope may still be split, but not in a way that leaves references orphaned across main. |
| 3 | Latent drift surfaced late: adding the new gate in the follow-up exposed older `verify-title-policy` / `auto-retro` reference drift that then had to be fixed in the same commit. | The new `scan_doc_workflow_refs.py`; the drift pre-existed undetected because no gate covered this class. | missing deterministic gate | The gate now runs continuously, so this drift class is caught on every change instead of accumulating until a consolidation exposes it. |

## Classification summary

- Missing deterministic gate: rows 1 and 3.
- Unclear agent instruction / scoping decision, plus human judgment on PR size:
  row 2.
- External or human decision that cannot be automated: none.

## No-repair reproduction path

1. Before deleting or renaming any `.github/workflows/*.yml`, confirm
   `scripts/scan_doc_workflow_refs.py` is still wired into
   `scripts/preflight_all.py` and CI.
2. Perform the rename/delete and repoint every non-archive doc reference in the
   same PR. If security source-of-truth matrices mention the workflow set,
   rebuild them in the same change.
3. Run `python3 scripts/scan_doc_workflow_refs.py verify` and the full preflight
   before pushing. A green run proves no path-form workflow references are
   orphaned, so no post-merge follow-up PR is needed for that drift class.

## Follow-up status

- [x] `ci(harness): fold scan_doc_workflow_refs.py enforcement permanently into
  the pre-push gate set so the row-1 gate cannot regress` -- satisfied by
  PR #1333, which wired the gate into `scripts/preflight_all.py` and CI.
- [x] #1325 stale-doc-reference follow-up -- satisfied by PR #1333.

## References

- Retro issue: [#1339](https://github.com/tvna/claude-md/issues/1339).
- Source PR: [#1329](https://github.com/tvna/claude-md/pull/1329).
- Parent issue: [#1319](https://github.com/tvna/claude-md/issues/1319).
- Follow-up issue: [#1325](https://github.com/tvna/claude-md/issues/1325).
- Follow-up PR: [#1333](https://github.com/tvna/claude-md/pull/1333).
- Follow-up merge commit:
  [5c09b18](https://github.com/tvna/claude-md/commit/5c09b18dc02c8eebec9988f6f01a1a0e7ae62053).
- Framework: CLAUDE.md section 3.
