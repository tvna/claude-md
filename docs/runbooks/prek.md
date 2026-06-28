# Pre-commit hooks (prek); runbook

Operator-facing companion to [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml) and the `Run prek` step in the `portable-pr-policy` job of [`.github/workflows/verify-pr.yml`](../../.github/workflows/verify-pr.yml). Tracking issue: [#408](https://github.com/tvna/claude-md/issues/408).

## Overview

This repository uses [`j178/prek`](https://github.com/j178/prek), a Rust-based runner fully compatible with `.pre-commit-config.yaml`. CI runs `uv tool run prek run --all-files --show-diff-on-failure` on every PR via `verify-pr.yml`; install it locally to catch the same violations before committing.

## Local install

```bash
# Install once (recommended)
uv tool install prek
prek install

# Or run ad-hoc without installing
uvx prek run --all-files
```

## Configured hooks

Generic hygiene hooks from `pre-commit/pre-commit-hooks v5.0.0`, wired as
`repo: local` `language: python` hooks that install the pinned
`pre-commit-hooks==5.0.0` package from PyPI via `additional_dependencies`
(Refs [#1967](https://github.com/tvna/claude-md/issues/1967)). The remote Claude
(web) session git proxy returns `403` for any `github.com` clone outside the
session repo scope, so a `repo: https://github.com/...` entry could not init and
forced `--no-verify` / `PREFLIGHT_SKIP=1`. PyPI installs bypass that proxy, so
the gate now runs in every environment with the exact upstream code:

- `trailing-whitespace` (entry `trailing-whitespace-fixer`)
- `end-of-file-fixer` (entry `end-of-file-fixer`)
- `check-yaml` (entry `check-yaml`, with `--unsafe`, excludes `^\.github/workflows/`)
- `check-merge-conflict` (entry `check-merge-conflict`)

Repo-local hooks (`language: system`, run via `uv run python`):

- `uv-pin-drift`; wraps `scripts/uv_pin.py drift`; triggers on `pyproject.toml`.
- `scan-workflow-pip`; wraps `scripts/scan_workflow_pip.py verify`; triggers on `^\.github/workflows/.*\.ya?ml$`.
- `preflight-branch-base`; pre-push hook wrapping `scripts/preflight_branch_base.py verify`; fetches `origin/main` and blocks pushes when `HEAD` does not contain the current base branch.
- `preflight-coverage`; pre-push hook wrapping `scripts/preflight_coverage.py`; checks that every changed `scripts/*.py` file meets the 90% per-file line-coverage floor. Reuses `coverage.json` if present; otherwise runs `pytest --cov --cov-report=json`. Blocks pushes when any file is absent from the coverage report or falls below the floor. Refs #952.

## CI gate

The `Run prek` step in `.github/workflows/verify-pr.yml` is part of the required `Portable PR policy / gate` context. A non-zero `prek` exit fails that gate and blocks protected-branch merges.
