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

| step                              | source workflow (job)                              | soft-skip?           |
| --------------------------------- | -------------------------------------------------- | -------------------- |
| `scan_apm_portability`            | `verify-pr.yml` (`portable-pr-policy`)             | no                   |
| `verify_apm_checksums`            | `verify-pr.yml` (`portable-pr-policy`)             | no                   |
| `uv_pin_drift`                    | `verify-agents.yml`                                | no                   |
| `scan_workflow_pip`               | `verify-agents.yml`                                | no                   |
| `scan_workflow_action_pins`       | `verify-agents.yml`                                | no                   |
| `scan_docs_inventory`             | `verify-agents.yml`                                | no                   |
| `scan_doc_workflow_refs`          | `verify-agents.yml`                                | no                   |
| `scan_design_philosophy_drift`    | `verify-pr.yml` (`verify-design-philosophy`)      | no                   |
| `dependabot_labels`               | `verify-pr.yml` (`verify-dependabot-labels`)      | no                   |
| `verify_required_check_contexts`  | `verify-pr.yml` (`verify-ruleset-sync`)           | no                   |
| `verify_ruleset_sync`             | `verify-pr.yml` (`verify-ruleset-sync`)           | yes (`GH_TOKEN_API`) |
| `ruff` / `mypy` / `pytest`        | `verify-agents.yml`                                | yes (`uv`)           |
| `prek`                            | `verify-pr.yml` (`portable-pr-policy`)            | yes (`uv`)           |

Steps marked "soft-skip" emit a `::warning::` annotation and continue
when their prerequisite is missing locally; the equivalent CI job
always runs them with the prerequisite available.

## What it deliberately does NOT run

Workflows whose input is the issue / PR webhook payload, not the
working tree, are out of scope; their client-side equivalents live in
the MCP PreToolUse hooks:

| CI script             | client-side gate (PreToolUse)                          |
| --------------------- | ------------------------------------------------------ |
| `title_policy`        | `scripts/preflight_title_policy.py`                    |
| `body_policy`         | `scripts/preflight_pr_body_required_sections.py`       |
| `issue_link`          | `scripts/pr_body_close_keyword_gate.py`                |

The drift gate (`scripts/scan_ssot_drift.py`) tracks this allowlist
explicitly. Adding a new CI script without a matching preflight step
fails the drift gate at `verify-pr.yml`'s `scan_ssot_drift.py verify` step.

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

**Remote sessions:** automatic via SessionStart hook; no action needed.

**Local clones (targeted gate):**

```sh
pre-commit install --hook-type pre-push
```

**Local clones (broad gate):**

```sh
git config core.hooksPath .githooks
```

### Emergency bypass

Two tiers (narrowed in issue #2133 so the routine bypass stops dropping the
cheap deterministic gates and `preflight_coverage`):

* **`PREFLIGHT_SKIP=1`**; skips ONLY the `prek` step. Every cheap gate AND
  `preflight_coverage` still run. This is the routine "prek is not provisioned
  in this session" lever, not a full bypass.

  ```sh
  PREFLIGHT_SKIP=1 git push
  ```

* **`PREFLIGHT_SKIP_ALL=1`**; skips the whole `scripts/preflight_all.py` run.
  Reserve this for a genuinely urgent push (e.g. a security rollback) that the
  preflight blocks for an unrelated reason.

  ```sh
  PREFLIGHT_SKIP_ALL=1 git push
  ```

You can also skip a single named step with `PREFLIGHT_SKIP_STEPS=<name>` (the
mechanism `PREFLIGHT_SKIP=1` uses for `prek`). Both bypasses are explicit,
observable in shell history, and noted in retrospectives. Do not configure
either permanently in your shell rc.

## Wiring summary

* `scripts/preflight_all.py`; the single entrypoint.
* `scripts/scan_ssot_drift.py`; gate that diffs the local STEPS set
  against `pull_request:` workflow scripts (folded in from the former
  `scan_preflight_drift.py`, refs #2301), alongside its registry-vs-manifest
  reconciliation. Fails when CI adds a gate that preflight does not mirror.
* `scripts/scan_docs_inventory.py`; docs inventory and lane-placement
  gate mirrored from `verify-agents.yml`.
* `.githooks/pre-push`; broad local gate, opt-in via `core.hooksPath`;
  auto-activated in remote sessions by `scripts/check_hooks_path.py`.
* `.pre-commit-config.yaml` `stages: [pre-push]`; targeted local gate
  for environments without `core.hooksPath` set; opt-in via
  `pre-commit install --hook-type pre-push`.
* `.github/workflows/verify-pr.yml`; runs the drift gate so silent
  drift fails CI before it reaches main.
