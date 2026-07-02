# docs/ index

This file enumerates every document under `docs/` by the lane that owns
it. Lanes are the buckets that `ls docs/` already shows:
`proposals/` (pre-decision evaluations with open questions), `prd/`
(design-stage rationale and decision records), `standards/`
(adopted rules, schemas, and contracts), `runbooks/` (operator
procedures), `uml/` (UML diagram artifacts), `generated/` (checked-in
generated views), `archive/` (frozen historical evidence),
`next-session/` (session handoff prompt templates).

The small lanes (`proposals/`, `adr/`, `uml/`, `archive/`,
`next-session/`) keep their full document table inline below. The large
lanes (`prd/`, `standards/`, `runbooks/`) keep only a description here and
carry their full table in their own `README.md`; follow the lane link to
reach every document. In a table, scan the `Territory` column for the
domain you care about and follow the `Companion` column to the workflow or
script that implements it.

Lane README files define the detailed placement rules:
[`proposals/README.md`](proposals/README.md), [`prd/README.md`](prd/README.md),
[`standards/README.md`](standards/README.md),
and [`runbooks/README.md`](runbooks/README.md). The append-only policy
for `archive/` is documented separately in
[`archive/RETENTION.md`](archive/RETENTION.md).

## proposals/; pre-decision evaluations with open questions

| File | Territory | Tracking issues | Companion |
|---|---|---|---|
| [README.md](proposals/README.md) | Placement rules for pre-decision evaluations whose requirements are not yet decidable, and their graduation path into `prd/` / `standards/` / `runbooks/`. | #1001 | `docs/INDEX.md`; `docs/prd/README.md` |
| [instruction-distribution-mechanism.md](proposals/instruction-distribution-mechanism.md) | Decision (A+C: shipped sync template plus tagged release artifacts pinned by tag+sha256) for how downstream projects import the compiled instructions as committed real files; retraction of the submodule+symlink method; deferred reusable-workflow option B and its re-open condition. | #1678 | `.github/workflows/publish-instructions-release.yml`; `scripts/publish_instruction_release.py`; `docs/runbooks/consumer-instruction-sync.md` |
| [config-ssot-duplicate-fact-inventory.md](proposals/config-ssot-duplicate-fact-inventory.md) | Inventory of facts duplicated across config files (toml/yaml/md) inside and outside `docs/`, classified by whether a single source or a drift gate already governs them; recommends single-source vs add-gate vs keep per candidate. Open questions block the remediation decision. | #1984 | `scripts/scan_maintainability_metrics.py`; `scripts/scan_module_size_distribution.py`; `.github/title-policy.toml` |

## prd/; design-stage rationale and decision records

Design-stage rationale, decision records, and judgment aids that have
not become an adopted rule. The full table lives in
[`prd/README.md`](prd/README.md).

## adr/; architecture decision records

Confirmed, owner-approved decisions recorded in MADR format. Each file
captures context, the decision, the rationale, rejected alternatives, and
consequences. This lane was established as part of the decision-capture
mechanism designed in [#1049](https://github.com/tvna/claude-md/issues/1049).

| File | Territory | Tracking issues | Companion |
|---|---|---|---|
| [TEMPLATE.md](adr/TEMPLATE.md) | MADR-style authoring skeleton for new ADRs. | #2000 | `docs/adr/0001-hook-manager-prek.md`; `docs/next-session/TEMPLATE.md` |
| [0001-hook-manager-prek.md](adr/0001-hook-manager-prek.md) | Decision to use prek over pre-commit as the git hook manager: token-efficiency rationale, performance comparison, and rejected alternative. | #408, #1049 | `.pre-commit-config.yaml`; `docs/runbooks/prek.md`; `docs/standards/pre-push-gate-performance.md` |
| [0002-index-merge-budget.md](adr/0002-index-merge-budget.md) | Merge-time INDEX budget gate; in-repo per-lane split (#2005), not extraction. | #2012 | `scripts/preflight_merge_index_budget.py` |
| [0003-ruff-check-only.md](adr/0003-ruff-check-only.md) | Decision to enforce ruff as check-only and keep `ruff format` off all gate surfaces: rationale, consequences, and the future-adoption path. | #2224, #2143, #2141 | `scripts/scan_ruff_format.py`; `scripts/preflight_steps.py`; `tests/test_scan_ruff_format.py` |

## uml/; UML diagram artifacts

| File | Territory | Tracking issues | Companion |
|---|---|---|---|
| [branch-local-remote.state.md](uml/branch-local-remote.state.md) | Two state diagrams (local working branch in the ephemeral container; remote branch on GitHub) of the branch lifecycle the agent drives in one session, with a grounded gap analysis of state divergence across the container boundary (unrecorded-session fail-open; no HEAD-vs-remote-tip gate; ephemeral unpushed loss; no remote merged-branch delete path). | #1627, #785, #1513, #31 | `scripts/preflight_push_session_branch.py`; `scripts/preflight_branch_base.py`; `scripts/branch_cleanup.py`; `scripts/gate_update_pr_branch.py` |
| [branch-local-remote.state.ja.md](uml/branch-local-remote.state.ja.md) | Japanese translation of `branch-local-remote.state.md` (owner-language reading copy of the local/remote branch state diagrams and gap analysis). | #1627, #785, #1513, #31 | `docs/uml/branch-local-remote.state.md` |
| [doc-dependency-graph-governance.gap.md](uml/doc-dependency-graph-governance.gap.md) | Gap analysis for the typed document dependency graph gate (PR #1755): before/after enforcement map (1 edge -> 8 blocking + 8 advisory), CI gate sequence diagram, and class diagram of the graph data model. Residual gaps: undeclared edges still rely on reviewer memory; gate is advisory in Phase 1; waivers are per-PR with no cross-PR persistence. | #1754 | `scripts/gate_doc_graph_pr.py`; `scripts/doc_graph.py`; `docs/graph/doc-dependencies.toml`; `.github/workflows/validate-doc-graph.yml` |
| [doc-dependency-graph-governance.gap.ja.md](uml/doc-dependency-graph-governance.gap.ja.md) | Japanese translation of `doc-dependency-graph-governance.gap.md` (owner-language reading copy of the gap analysis, gate sequence, and data model). | #1754 | `docs/uml/doc-dependency-graph-governance.gap.md` |

## standards/; adopted rules, schemas, and contracts

Adopted repository rules, contracts, schemas, and the criteria behind
deterministic gates. The full table lives in
[`standards/README.md`](standards/README.md).

## runbooks/; operator procedures

Operator procedures: how to perform, verify, pause, roll back, or
investigate a repository operation. The full table lives in
[`runbooks/README.md`](runbooks/README.md).

## generated/; checked-in generated views

### generated/scripts/; per-script AST graphs

`generated/scripts/ast/<stem>.md` holds one Mermaid AST control-flow doc per
`scripts/*.py` file, `generated/scripts/dependency-graph.md` holds the
sibling-import dependency graph across those scripts,
`generated/scripts/trigger-map.md` reverse-maps where each script is launched
from (workflow `run:` steps, pre-commit, `preflight_all.py` Step argv, agent
hooks) and lists dead-script candidates, plus
`generated/scripts/auto-retro-triage-report.md`, the live retro-issue snapshot.
This folder is owned by the post-merge automation
(the `decision-tree` job in `.github/workflows/post-merge.yml`); it is not
hand-editable and is exempt from per-file INDEX linking (a non-bot edit fails
`scripts/gate_generated_scripts_manual_edit.py`). Sources:
`python3 scripts/script_ast_graph.py all-doc` (per-script AST),
`python3 scripts/script_dependency_graph.py all-doc` (dependency graph),
`python3 scripts/script_trigger_map.py all-doc` (trigger reverse-map), and
`python3 scripts/auto_retro.py triage-report` (triage snapshot).
Tracking issues: #598, #605, #960, #1540, #1543, #1546.

### generated/graph/; document dependency diagram

`generated/graph/doc-dependency-graph.md` holds the Mermaid flowchart of the
typed document dependency graph declared in `docs/graph/doc-dependencies.toml`.
This folder is owned by the post-merge automation
(the `decision-tree` job in `.github/workflows/post-merge.yml`); it is not
hand-editable and is exempt from per-file INDEX linking. The diagram is
regenerated whenever the graph TOML or its generator script changes.
Source: `python3 scripts/doc_graph_viz.py all-doc`.
Tracking issue: #1754.

### generated/workflows/; workflow if-branch diagrams

`generated/workflows/<name>-if-branches.md` holds one Mermaid if-branch diagram
per `.github/workflows/<name>.yml`. Each diagram shows job-level `if:`
conditions, `needs:` dependency edges, and step-level `if:` branches.
This folder is owned by the post-merge automation
(the `decision-tree` job in `.github/workflows/post-merge.yml`); it is not
hand-editable and is exempt from per-file INDEX linking (a non-bot edit fails
`scripts/gate_generated_scripts_manual_edit.py`). Listing each file here would
drift as workflows are added or removed, so the directory is described once and
skipped by `scripts/scan_docs_inventory.py`.
Source: `python3 scripts/workflow_diagram.py diagram-doc`.
Tracking issues: #960, #1613.

## archive/; frozen historical evidence

These files are append-only. Their narrative references to pre-restructure
paths reflect the state at PR-merge time and are preserved as historical
fidelity. See [`archive/RETENTION.md`](archive/RETENTION.md) for the
naming convention and the per-30-entries year-folder cutover.

| File | Subject |
|---|---|
| [decision-tree-replay.md](archive/decision-tree-replay.md) | Calibration evidence that the decision tree in `prd/agent-rules-design-philosophy.md` section 4 reproduces historical lane assignments. Append-only; not normative. |
| [issue-pr-body-examples.md](archive/issue-pr-body-examples.md) | Worked example bodies, one per `type:*` label plus one PR. Calibration material for `standards/issue-pr-body-standard.md`. |
| [label-migration-2026-05-26.md](archive/label-migration-2026-05-26.md) | Append-only operation log for the 2026-05-26 label backfill and prune preparation. |
| [renovate-evaluation.md](archive/renovate-evaluation.md) | DECLINED (#1014) evaluation of switching Dependabot to Mend Renovate, with the one-shot cutover migration sketch and phased sub-issue chain (#280-#284, superseded). Retained as the record of the evaluation; references the pre-consolidation workflow names in its migration sketch as historical state. |
| [renovate-poc-279.md](archive/renovate-poc-279.md) | Renovate migration PoC primary-source evidence for issue #279 (Q2/Q3/Q4 answered from Renovate docs; Q1 pending human Mend Renovate App install). Two documentary candidate ruleset shapes captured against the post-PR-#454 SoT. |
| [retrospective-pr-229.md](archive/retrospective-pr-229.md) | Retrospective for PR #229 (layer responsibility boundary repair loops). |
| [retrospective-pr-235.md](archive/retrospective-pr-235.md) | Retrospective for PR #235 (security control inventory, repair-free). |
| [retrospective-pr-237.md](archive/retrospective-pr-237.md) | Retrospective for PR #237 (auto-retro workflow, repair-free). |
| [retrospective-pr-248.md](archive/retrospective-pr-248.md) | Retrospective for PR #248 (agent-rules design philosophy, repair-free). |
| [retrospective-pr-249.md](archive/retrospective-pr-249.md) | Retrospective for PR #249 (security-drift aggregator, repair-free). |
| [retrospective-pr-256.md](archive/retrospective-pr-256.md) | Retrospective for PR #256 (agent-rules checklist follow-up, repair-free). |
| [retrospective-pr-257.md](archive/retrospective-pr-257.md) | Retrospective for PR #257 (workflow permissions audit, repair-free). |
| [retrospective-pr-337.md](archive/retrospective-pr-337.md) | Retrospective for PR #337 (no-override rule, repair-free). |
| [retrospective-pr-349.md](archive/retrospective-pr-349.md) | Retrospective for PR #349 (GitHub Advisory Database direct query, repair-free). |
| [retrospective-pr-1822.md](archive/retrospective-pr-1822.md) | Retrospective close-out for PR #1822 / retro #1824 (ADR-0001 prek hook manager selection); true-positive triage, durable fixes R1-R3 landed in #2100. |

## next-session/; session handoff prompt templates

| File | Territory | Tracking issues | Companion |
|---|---|---|---|
| [TEMPLATE.md](next-session/TEMPLATE.md) | Reusable template for session handoff prompts. Uses 4-space-indented code blocks (no fenced blocks) to prevent Markdown renderers from breaking the outer fence when prompts are pasted into a new session. | #1884 | `docs/next-session/` |

## Navigation aids

- [archive/RETENTION.md](archive/RETENTION.md); append-only policy and auto-retro placement convention for `archive/`.
- [agent-provenance.md](agent-provenance.md); compatibility pointer to `runbooks/agent-provenance.md` for the original #312 target path.
- This INDEX is reviewed whenever a file is added, removed, or moved across lanes. Treat it as a self-describing supplement to `ls docs/`, not a replacement for the folder layout: the lane is visible at the filesystem level; this index just names what each file owns.
