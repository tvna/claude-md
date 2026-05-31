# Preflight runbook

`scripts/preflight_all.py` runs CI's PR-gating verification set locally, in
the same order, with the same environment contract. Refs #493 (closes the
verification-drift gap that produced 18 of 23 open retro repair lines).

## What it runs

The authoritative list of steps lives in `preflight_all.STEPS`. Print the
current manifest with:

```sh
python3 scripts/preflight_all.py --list
```

At time of writing, the steps mirror the script invocations from the
`pull_request:`-triggered workflows under `.github/workflows/`:

| step                              | source workflow                       | soft-skip?           |
| --------------------------------- | ------------------------------------- | -------------------- |
| `scan_apm_portability`            | `portable-pr-policy.yml`              | no                   |
| `verify_apm_checksums`            | `portable-pr-policy.yml`              | no                   |
| `uv_pin_drift`                    | `verify-agents.yml`                   | no                   |
| `scan_workflow_pip`               | `verify-agents.yml`                   | no                   |
| `scan_workflow_action_pins`       | `verify-agents.yml`                   | no                   |
| `scan_docs_inventory`             | `verify-agents.yml`                   | no                   |
| `scan_design_philosophy_drift`    | `verify-design-philosophy.yml`        | no                   |
| `dependabot_labels`               | `verify-dependabot-labels.yml`        | no                   |
| `verify_required_check_contexts`  | `verify-ruleset-sync.yml`             | no                   |
| `verify_ruleset_sync`             | `verify-ruleset-sync.yml`             | yes (`GH_TOKEN_API`) |
| `ruff` / `mypy` / `pytest`        | `verify-agents.yml`                   | yes (`uv`)           |
| `prek`                            | `portable-pr-policy.yml`              | yes (`uv`)           |

Steps marked "soft-skip" emit a `::warning::` annotation and continue
when their prerequisite is missing locally; the equivalent CI job
always runs them with the prerequisite available.

## What it deliberately does NOT run

Workflows whose input is the issue / PR webhook payload, not the
working tree, are out of scope -- their client-side equivalents live in
the MCP PreToolUse hooks:

| CI script             | client-side gate (PreToolUse)                          |
| --------------------- | ------------------------------------------------------ |
| `title_policy`        | `scripts/preflight_title_policy.py`                    |
| `body_policy`         | `scripts/preflight_pr_body_required_sections.py`       |
| `issue_link`          | `scripts/pr_body_close_keyword_gate.py`                |

The drift gate (`scripts/scan_preflight_drift.py`) tracks this allowlist
explicitly. Adding a new CI script without a matching preflight step
fails the drift gate at `verify-agents.yml / lint-scripts-static`.

## Local pre-push defense-in-depth

Two complementary local gates exist; which one fires depends on environment
setup. Both run on the developer's machine before a push reaches GitHub, so
failures surface within seconds rather than minutes later in CI.

| Mechanism | When active | Scope |
|---|---|---|
| `.githooks/pre-push` | `core.hooksPath=.githooks` is set | Broad: runs `preflight_all.py` (full CI mirror) |
| pre-commit `stages: [pre-push]` | `pre-commit install --hook-type pre-push` done | Targeted: branch-base + coverage |

These are **complementary, not redundant**: they serve different environments.

* **Remote sessions (Claude Code on the Web):** the SessionStart hook
  (`scripts/check_hooks_path.py`) auto-sets `core.hooksPath=.githooks`, so
  `.githooks/pre-push` fires automatically on every push. No manual setup
  required.
* **Local development clones:** `core.hooksPath` is not set by default.
  Run `pre-commit install --hook-type pre-push` once per clone to activate
  the targeted pre-commit gate. Optionally, `git config core.hooksPath
  .githooks` upgrades to the broader `.githooks/pre-push` gate instead.

When `core.hooksPath` is set, git ignores `.git/hooks/` entirely, so the two
gates never double-fire. CI (`verify-github-content.yml`) remains the final
backstop regardless of which local gate is active.

Do **not** remove the `stages: [pre-push]` hooks from `.pre-commit-config.yaml`:
they are the local gate for developers without `core.hooksPath` set and are
not dead code.

### Activation

**Remote sessions:** automatic via SessionStart hook -- no action needed.

**Local clones (targeted gate):**

```sh
pre-commit install --hook-type pre-push
```

**Local clones (broad gate):**

```sh
git config core.hooksPath .githooks
```

### Emergency bypass

When a push is genuinely urgent (e.g. a security rollback) and the
preflight blocks legitimately for an unrelated reason, set
`PREFLIGHT_SKIP=1` for the single push:

```sh
PREFLIGHT_SKIP=1 git push
```

The bypass is explicit, observable in shell history, and noted in
retrospectives. Do not configure it permanently in your shell rc.

## Wiring summary

* `scripts/preflight_all.py` -- the single entrypoint.
* `scripts/scan_preflight_drift.py` -- CI gate that diffs the local
  set against `pull_request:` workflow scripts. Fails CI when CI
  adds a gate that preflight does not mirror.
* `scripts/scan_docs_inventory.py` -- docs inventory and lane-placement
  gate mirrored from `verify-agents.yml`.
* `.githooks/pre-push` -- broad local gate, opt-in via `core.hooksPath`;
  auto-activated in remote sessions by `scripts/check_hooks_path.py`.
* `.pre-commit-config.yaml` `stages: [pre-push]` -- targeted local gate
  for environments without `core.hooksPath` set; opt-in via
  `pre-commit install --hook-type pre-push`.
* `.github/workflows/verify-agents.yml` -- runs the drift gate in
  the `lint-scripts-static` job so silent drift fails CI before it
  reaches main.
