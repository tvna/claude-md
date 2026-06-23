# Document Dependency Graph

This document is the design rationale and operational contract for the typed
document dependency graph that gates PRs via
`scripts/gate_doc_graph_pr.py`. It is the deliverable for
[#1754](https://github.com/tvna/claude-md/issues/1754).

## 1. Problem statement

PR#1737 merged with required fixes missing because `master.instructions.md`
(universal text) was updated standalone, without updating the PRDs and
runbooks that it governs. The only machine-enforced document dependency at
the time was one directed relationship:

```
scan_design_philosophy_drift.py verify-coupling
  master.instructions.md -> agent-rules-design-philosophy.md
```

All other relationships lived only in reviewer memory. When reviewer memory
fails, the merge guard fails.

The underlying pattern: the four-lane ownership model
(`docs/prd/agent-rules-design-philosophy.md` section 2) defines which
documents govern which, but this matrix existed only in human-readable prose.
There was no machine-readable representation that a gate could query at PR
time.

## 2. Solution: typed document dependency graph

A TOML file (`docs/graph/doc-dependencies.toml`) declares all document
dependency relationships as a typed, directed graph. Nodes are documents,
compiled artifacts, scripts, and workflows. Edges are typed, directed
relationships between them.

When a PR changes a node, `scripts/gate_doc_graph_pr.py` queries the graph
and requires that all blocking-severity dependent nodes are also present in
the PR diff (or explicitly waived in the PR body).

This design draws on graph database thinking: relationships are first-class
objects, not implicit prose. Adding a new dependency is a one-line TOML edit,
which is code-reviewed and CODEOWNERS-protected.

## 3. Graph schema

### 3.1 Node types

| Type | Lane | Examples |
|---|---|---|
| `universal_text` | Universal | `.apm/instructions/master.instructions.md` |
| `compiled_artifact` | Universal (output) | `CLAUDE.md`, `AGENTS.md` |
| `prd` | Repo-local doc | `docs/prd/agent-rules-design-philosophy.md` |
| `standard` | Repo-local doc | `docs/standards/workflow-script-quality.md` |
| `runbook` | Repo-local doc | `docs/runbooks/*.md` |
| `harness_script` | Harness | `scripts/*.py` |
| `harness_workflow` | Harness | `.github/workflows/*.yml` |
| `archive` | Repo-local doc | `docs/archive/*.md` |

### 3.2 Edge types and severity

| Edge type | Default severity | Meaning |
|---|---|---|
| `governs` | blocking | Upstream principles define/constrain downstream; downstream must track upstream. |
| `compiled_to` | blocking | Upstream compiles deterministically into downstream. (Already gated by APM; included for completeness.) |
| `derives_from` | blocking | Downstream design was derived from upstream; upstream change requires downstream review. |
| `enforced_by` | advisory | Downstream script enforces upstream rule. |
| `implements` | advisory | Downstream is the concrete harness implementation of upstream policy. |
| `references` | advisory | Upstream cites downstream; informational. |

Severity can be overridden per edge with an explicit `severity` field.

### 3.3 Enforcement

- **blocking** edges: the gate fails when the upstream node is changed in a PR
  but the downstream node is absent from the PR diff. The error message names
  the required co-change and the waiver syntax.
- **advisory** edges: the gate emits a note but does not fail.

### 3.4 Waiver mechanism

Add a plain-text line to the PR body (MCP-safe; mirrors the
`philosophy-matrix-ack` pattern):

```
doc-graph-waiver: NODE_ID; reason for skipping co-change
```

Multiple waivers are supported (one per line). A waived node is reported as
"waived" and does not cause a failure. The waiver becomes part of the PR body
and is preserved as an audit record in the repository's PR history.

## 4. Complementary relationship with existing gates

This gate is **complementary** to `scan_design_philosophy_drift.py
verify-coupling`, not a replacement:

| Gate | Depth | Breadth |
|---|---|---|
| `scan_design_philosophy_drift.py verify-coupling` | High: checks semantic content (label parity, glossary, matrix rows) for master->philosophy | Narrow: covers one specific relationship |
| `gate_doc_graph_pr.py` | Low: checks file-presence co-change only | Wide: covers all declared relationships in the graph |

Both gates remain active. The graph gate adds breadth; the coupling gate adds
semantic depth for the critical master->philosophy relationship.

## 5. Rollout strategy

New gates in this repository follow the selection mechanism documented in
`docs/prd/agent-rules-design-philosophy.md` section 6.4:

1. **Phase 1 (this PR):** Gate script + advisory CI (`continue-on-error: true`
   in `.github/workflows/validate-doc-graph.yml`). The gate runs on every PR
   but cannot block merges. False positives are tracked in auto-retro issues.

2. **Phase 2 (follow-up PR):** Promote to required check in
   `.github/rulesets/main.json` when the false-positive rate is below 5%
   across two consecutive sprints. The promotion PR cites the retro evidence.

3. **Phase 3 (ongoing):** Expand the initial node/edge set as new document
   relationships are identified. Each addition is a one-line TOML change,
   code-reviewed and CODEOWNERS-protected.

## 6. Key files

| File | Role |
|---|---|
| `docs/graph/doc-dependencies.toml` | Graph declaration (harness-lane data file) |
| `scripts/doc_graph.py` | Core library: load, query, render |
| `scripts/gate_doc_graph_pr.py` | CI gate runner |
| `scripts/doc_graph_viz.py` | Mermaid diagram generator |
| `tests/test_doc_graph.py` | Unit tests for core library |
| `tests/test_gate_doc_graph_pr.py` | Integration tests for gate |
| `tests/test_doc_graph_viz.py` | Tests for viz generator |
| `.github/workflows/validate-doc-graph.yml` | Advisory CI workflow |
| `docs/generated/graph/doc-dependency-graph.md` | Auto-generated Mermaid diagram (post-merge) |

## 7. Validation strategy

- `uv run pytest tests/test_doc_graph.py tests/test_gate_doc_graph_pr.py tests/test_doc_graph_viz.py -v` passes.
- `python3 scripts/gate_doc_graph_pr.py` on a branch changing only `.apm/instructions/master.instructions.md` exits 1 and lists required co-changes.
- `python3 scripts/doc_graph_viz.py preview` produces a valid Mermaid diagram verified by `scripts/scan_mermaid_syntax.py`.
- `validate-doc-graph.yml` passes on a PR that changes `master.instructions.md` alongside all its blocking dependents.

## 8. Update procedure

To add a new document relationship:

1. Open a sub-issue of [#1754](https://github.com/tvna/claude-md/issues/1754)
   describing the new edge (from, to, type, severity, rationale).
2. Add the TOML `[[edges]]` block to `docs/graph/doc-dependencies.toml`.
3. If the source or target node is not yet declared, add its `[[nodes]]` block.
4. Run `python3 scripts/gate_doc_graph_pr.py` locally to confirm the new edge
   behaves as expected.
5. Cite the sub-issue on the PR body.

To remove a relationship: open a sub-issue explaining why the dependency no
longer holds, then remove the `[[edges]]` block. A node with no edges may
also be removed if it serves no informational purpose.

## 9. References

- [#1754](https://github.com/tvna/claude-md/issues/1754) - tracking issue
- `docs/prd/agent-rules-design-philosophy.md` - four-lane model (section 2); P3 harness row (section 3)
- `scripts/scan_design_philosophy_drift.py` - complementary semantic-depth gate
- `docs/standards/workflow-script-quality.md` - quality gates M1-M9 for harness scripts
