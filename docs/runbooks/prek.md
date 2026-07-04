# Pre-commit hooks (prek); runbook

Operator-facing companion to [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml) and the `Run prek` step in the `portable-pr-policy` job of [`.github/workflows/verify-pr.yml`](../../.github/workflows/verify-pr.yml). Tracking issue: [#408](https://github.com/tvna/claude-md/issues/408).

## Scope

Installing and running [`j178/prek`](https://github.com/j178/prek), the git
hook runner this repository uses locally and in CI, and provisioning it
automatically in remote agent sessions. Reach for this runbook when a commit
or push is blocked by a `prek`-related failure, or when setting up a new
environment (local machine, devcontainer, or remote agent container) to run
the same hooks CI enforces.

## Why

This repository uses `j178/prek`, a Rust-based runner fully compatible with
`.pre-commit-config.yaml`. CI runs `uv tool run prek run --all-files
--show-diff-on-failure` on every PR via `verify-pr.yml`; installing it locally
catches the same violations before committing, instead of discovering them
only after a push.

## Why not

`prek` was chosen over the original `pre-commit/pre-commit` tool for lower
per-hook token overhead in agent sessions (concise Rust binary output,
parallel execution, no Python runtime preamble); see
[ADR-0001](../adr/0001-hook-manager-prek.md) for the full comparison and
rationale. There is no supported alternative hook runner for this repository's
`.pre-commit-config.yaml`.

## Procedure

### Local install

```bash
# Install once (recommended)
uv tool install prek
prek install

# Or run ad-hoc without installing
uvx prek run --all-files
```

### Remote-session bootstrap

`scripts/install-prek.sh` runs as a SessionStart hook in remote agent
containers (Claude Code on the Web `CLAUDE_CODE_REMOTE=true`, Codex cloud
`CODEX_CODE_REMOTE=true`) so `prek` is on `PATH` before the first commit --
this repo sets `core.hooksPath=.githooks`, and `.githooks/pre-commit` execs
`prek hook-impl`, which otherwise fails with `exec: prek: not found` on a
fresh clone. It is a no-op outside those two environments (local dev and the
nix devcontainer manage `prek` themselves), idempotent when `prek` is already
on `PATH`, and installs it unpinned via `uv tool install prek`, matching CI's
unpinned `uv tool run prek`. It fails open: a missing `uv` or a failed install
logs to stderr and exits `0` rather than blocking session startup, with CI's
`Run prek` step as the backstop. Registered in
`scripts/agent_hooks_source.json` and regenerated into `.claude/settings.json`,
`.codex/hooks.json`, and `.devin/hooks.v1.json` by
`scripts/gen_agent_hooks.py`. Refs [#2073](https://github.com/tvna/claude-md/issues/2073).

## Verification

- Local install: `prek --version` prints a version, and `uvx prek run
  --all-files` runs to completion (all hooks `Passed` or `Skipped`).
- Remote-session bootstrap: after a fresh remote session starts,
  `command -v prek` resolves, and `tests/test_install_prek_hook.py` covers the
  off-remote no-op, idempotent skip, and SessionStart registration behavior.

## Pause / Resume

Not applicable; this is a one-shot install/verify procedure with no
long-running state to pause or resume.

## Rollback

`uv tool uninstall prek` removes the local install; there is no other state to
undo. Skipping `prek install` (or deleting `.git/hooks/pre-commit` if
`core.hooksPath` is not set) reverts to running checks manually via CI only.

## References

- [ADR-0001: prek over pre-commit as the git hook manager](../adr/0001-hook-manager-prek.md)
- [`docs/standards/pre-push-gate-performance.md`](../standards/pre-push-gate-performance.md)
- Tracking issues: [#408](https://github.com/tvna/claude-md/issues/408), [#2073](https://github.com/tvna/claude-md/issues/2073)

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
