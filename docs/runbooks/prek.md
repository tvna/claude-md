# Pre-commit hooks (prek) — runbook

Operator-facing companion to [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml) and the `prek` job in [`.github/workflows/verify-agents.yml`](../../.github/workflows/verify-agents.yml). Tracking issue: [#408](https://github.com/tvna/claude-md/issues/408).

## Overview

This repository uses [`j178/prek`](https://github.com/j178/prek), a Rust-based runner fully compatible with `.pre-commit-config.yaml`. CI runs `uv tool run prek run --all-files --show-diff-on-failure` on every PR via the `prek` job in `verify-agents.yml`; install it locally to catch the same violations before committing.

## Local install

```bash
# Install once (recommended)
uv tool install prek
prek install

# Or run ad-hoc without installing
uvx prek run --all-files
```

## Configured hooks

Generic hygiene hooks from `pre-commit/pre-commit-hooks v5.0.0`:

- `trailing-whitespace`
- `end-of-file-fixer`
- `check-yaml` (with `--unsafe`, excludes `^\.github/workflows/`)
- `check-merge-conflict`

Repo-local hooks (`language: system`, run via `uv run python`):

- `uv-pin-drift` — wraps `scripts/uv_pin.py drift`; triggers on `pyproject.toml`.
- `scan-workflow-pip` — wraps `scripts/scan_workflow_pip.py verify`; triggers on `^\.github/workflows/.*\.ya?ml$`.

## CI gate

The `prek` job in `.github/workflows/verify-agents.yml` is one of three inputs aggregated by the `gate` job (alongside `verify` and `lint-scripts`). A non-`success` result fails the gate with `::error::prek gate result=... (expected 'success').`, blocking merge on protected branches.
