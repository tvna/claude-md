#!/usr/bin/env bash
# SessionStart hook: align local-host uv with the repo pin so the Claude Code
# process PATH (which runs Stop hooks, including analyzing-data's `uv run`)
# resolves to a binary that matches `[tool.uv].required-version` -- not to a
# drifted package-managed uv (e.g. Homebrew). Closes the PR #1206 coverage gap
# this issue (#1207) opened.
#
# Why this exists separately from `install-uv.sh`:
#   `install-uv.sh` provisions uv for *remote* execution environments
#   (CLAUDE_CODE_REMOTE / CODEX_CODE_REMOTE) where the host has no uv. This
#   script handles the *local* developer host where uv exists but drifts
#   ahead of the pin and cannot self-update (package-managed installs
#   disable `uv self update`). PR #1206 added the workspace-local prefix
#   plumbing; this hook is what makes it reach the Claude Code process.
#
# Fast paths:
#   - In a recognised remote environment    -> exit 0 (install-uv.sh's job).
#   - Host `uv --version` already matches   -> exit 0 (no install, no PATH
#                                              edit; nix develop and aligned
#                                              hosts pay nothing).
# Slow path:
#   - Host uv missing or drifted -> bootstrap the pinned uv into the
#     workspace-local prefix (`scripts/setup_pinned_uv.sh`) and append a
#     PATH export to `$CLAUDE_ENV_FILE` so the harness sources it before the
#     first agent step (the same mechanism `install-uv.sh` uses).
#
# The host's package-managed uv is never modified.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/_session_path.sh
. "${SCRIPT_DIR}/_session_path.sh"
REPO_ROOT="${CLAUDE_PROJECT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
PYPROJECT="${REPO_ROOT}/pyproject.toml"

# Remote environments are install-uv.sh's job.
if [ "${CLAUDE_CODE_REMOTE:-}" = "true" ] || [ "${CODEX_CODE_REMOTE:-}" = "true" ]; then
  exit 0
fi

# Read the pin via the shared helper (single source of truth).
if ! UV_VERSION="$(python3 "${SCRIPT_DIR}/uv_pin.py" read "${PYPROJECT}" 2>/dev/null)"; then
  echo "session-uv-local-pin: cannot read uv pin from ${PYPROJECT}; skipping" >&2
  exit 0
fi

current=""
if command -v uv >/dev/null 2>&1; then
  current="$(uv --version 2>/dev/null | awk '{print $2}')"
fi

# Fast path: aligned uv already on PATH (e.g. nix develop, manually pinned).
if [ "${current}" = "${UV_VERSION}" ]; then
  exit 0
fi

# Slow path: bootstrap the workspace-local prefix and persist PATH.
PREFIX="${UV_PIN_DIR:-${HOME}/.uv-pins/claude-md}"
if ! "${SCRIPT_DIR}/setup_pinned_uv.sh" >&2; then
  echo "session-uv-local-pin: setup_pinned_uv.sh failed; expect Stop hook drift" >&2
  exit 0
fi

# Persist the prefix for the rest of the session. Mirrors install-uv.sh:
# `$CLAUDE_ENV_FILE` is sourced by the harness before the first agent step.
persist_session_path "${PREFIX}"

uv --version >&2
