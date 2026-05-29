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

## Activating the pre-push hook

The repo ships `.githooks/pre-push`. Activate it per clone with:

```sh
git config core.hooksPath .githooks
```

Once active, `git push` runs `scripts/preflight_all.py` and aborts the
push on failure.

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
* `.githooks/pre-push` -- invokes the entrypoint, opt-in via
  `core.hooksPath`.
* `.github/workflows/verify-agents.yml` -- runs the drift gate in
  the `lint-scripts-static` job so silent drift fails CI before it
  reaches main.
