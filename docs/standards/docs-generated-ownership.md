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

### Retirement path

`scripts/verify_generated_docs_ownership.py` holds the `OWNERSHIP` registry:
the single source of truth mapping every `docs/generated/` path pattern to the
producer script that owns it. Retiring a generator never needs a per-case
negotiation; the deterministic path is:

1. The retiring PR deletes the generator script AND drops its `OWNERSHIP`
   entry in the same change. The read-only `verify` subcommand (wired into
   `preflight_steps.py` and the `lint-scripts-static` job of
   `verify-agents.yml`) fails whenever a registered producer is missing, so
   the two edits cannot land separately.
2. The retiring PR does NOT touch the generated outputs;
   `gate_generated_scripts_manual_edit.py` forbids that on non-bot branches.
3. On the next post-merge run, the `retire` subcommand (wired into the
   `decision-tree` job after all generators) deletes every file under
   `docs/generated/` that no registry pattern owns and prunes emptied
   directories; the existing drift detection publishes the deletions through
   the `chore/update-generated-docs` bot PR.

The same registry makes registration mandatory in the other direction: a new
generator added to `post-merge.yml` without an `OWNERSHIP` entry will see its
outputs deleted by the sweep on the next run, loudly (`retired orphaned doc:`
lines in the job log). Add the registry entry in the PR that wires the
generator. `tests/test_verify_generated_docs_ownership.py` pins the sweep
semantics, the registry-to-`post-merge.yml` wiring, and keeps the write-lane
`retire` subcommand banned from preflight. Refs #2226.

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
