# Adding A Workflow

When you land a new `.github/workflows/*.yml`, two deterministic pre-push
gates fail unless you also produce the artifacts they expect, and any
multi-step or LLM-backed verification you run alongside it should disclose
its token/compute cost up front. This runbook captures that no-surprise,
repair-free path so the next workflow addition reproduces it (issue #1101,
retrospective of PR #1100 / issue #1099).

## Pre-push two-step for a new workflow

Run both steps before pushing. They mirror the gates in
`scripts/preflight_all.py` and the `pull_request:` CI jobs, so a local
miss surfaces in CI minutes later.

### 1. Generate the if-branch diagram and register it in `docs/INDEX.md`

`scripts/scan_docs_inventory.py verify` fails when a workflow has no
generated `docs/generated/workflows/<stem>-if-branches.md` listed in
`docs/INDEX.md`.

```sh
# Render the diagram doc for the new workflow (or omit the path to
# regenerate every workflow diagram at once).
python3 scripts/workflow_diagram.py diagram-doc .github/workflows/<new>.yml
```

Then add a row to the `generated/workflows/` table in `docs/INDEX.md`.
Each row links the new `<stem>-if-branches.md` diagram (first column,
relative to `docs/`) to the source `<new>.yml` workflow in backticks
(second column). Match the shape of the existing rows there -- for a
worked example, see the `skill-quality-if-branches.md` entry PR #1100
added. Keep the table in the same alphabetical order as the surrounding
rows.

### 2. Add a CLI contract test for each workflow-invoked script

`tests/test_workflow_cli_contracts.py` parses every workflow `run:` block
and fails when a `python3 scripts/foo.py bar` (or
`uv run python scripts/foo.py bar`) invocation has no entry in
`CONTRACT_REGISTRY`. This guards against a script-level unit test passing
while the Actions invocation drifts (issue #193).

For each new `(script, subcommand)` pair the workflow calls:

1. Write a contract test that pins the argv/env/file shape the workflow
   uses, e.g. `test_<script>_<subcommand>_matches_workflow_args`.
2. Register it:
   ```py
   CONTRACT_REGISTRY: dict[tuple[str, str | None], str] = {
       # ...
       ("<script>.py", "<subcommand>"): "<test_function_name>",
   }
   ```

`test_contract_registry_has_no_stale_entries` rejects orphan rows, so
remove the entry if you delete the invocation.

## Token-cost disclosure

Before running multi-step verification or LLM-backed tooling, state the
expected token/compute footprint up front -- especially anything that
sends content to an external service. This is the primary driver of the
PR #1100 retrospective: implementation and verification began without any
upfront statement of the token cost, raising a token-waste concern.

- Name the cost before you spend it: how many verification passes, which
  tools, and whether any of them call an external model.
- Treat external-model paths as opt-in, never auto-run. The skill-quality
  gate is the worked example: `scripts/skill_quality_gate.py` runs
  `waza check` (deterministic, local) but never `waza quality`, because
  the LLM-as-Judge path sends `SKILL.md` content externally via Copilot.
  See the `Refs #1099` invocation in `.github/workflows/skill-quality.yml`.
- If a gate must call an external service to do its job, say so where the
  operator can see it before the run, and keep secret values out of any
  log or comment.

## Verification

For a documentation-only or workflow-shape change, run the two gates this
runbook is about:

```sh
python3 scripts/scan_docs_inventory.py verify
uv run python -m pytest tests/test_workflow_cli_contracts.py -q
```

For full local parity with the PR gates, run:

```sh
python3 scripts/preflight_all.py
```
