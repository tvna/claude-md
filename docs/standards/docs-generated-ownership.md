# docs/generated/ ownership constraint

## Design decision

`docs/generated/` is a **single-producer surface** owned exclusively by the
post-merge automation workflow (`post-merge.yml`). No agent, contributor, or
pre-push gate may write to it directly.

### Rationale

Before the single-producer rule was established, doc-generator scripts were run
in the pre-push lane. This left perpetually-untracked files in `docs/generated/`
that triggered the untracked-file Stop hook on every session. Issues #1764 and
#1771 removed the generators from the pre-push lane.

### Enforcing gate

`tests/test_preflight_steps.py::TestStepsRegistry::test_no_step_generates_docs_generated`
explicitly blocks the five generator scripts from being added to
`preflight_steps.STEPS`:

| Generator | Write subcommand |
|---|---|
| `scripts/script_ast_graph.py` | `all-doc` |
| `scripts/script_dependency_graph.py` | `all-doc` |
| `scripts/script_trigger_map.py` | `all-doc` |
| `scripts/workflow_diagram.py` | `diagram-doc` |
| `scripts/doc_graph_viz.py` | `all-doc` |

Any attempt to add these to preflight fails the test. Refs #1771, #1764.

### Post-merge automation path

When `docs/generated/` drifts (e.g. a new script was added in a PR without
updating the generated AST docs), the CI job `verify-generated-docs-drift`
inside `post-merge.yml` detects the drift and triggers the decision-tree, which
opens a `chore/update-generated-docs` branch PR automatically.

### Agent workflow implication

When a `verify-generated-docs-drift` CI failure is reported:

1. **First**: run `git fetch origin main` and check current main HEAD.
2. If a `chore/update-generated-docs` PR has already been merged, the
   failure is resolved; do **not** open a duplicate issue.
3. Only open an issue if the failure is confirmed to be still present on the
   current main HEAD.

Refs #1943 (duplicate issue opened before main was checked), #1944 (gate
proposal superseded by this doc after the pre-push generator constraint was
discovered).
