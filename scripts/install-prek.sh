#!/usr/bin/env bash
# SessionStart hook: provision the prek (j178/prek) git-hook runner onto PATH in
# remote agent sessions so the first `git commit` is never blocked on a missing
# runner.
#
# Why this exists (Refs #2098):
#   This repo sets core.hooksPath=.githooks, and .githooks/pre-commit execs
#   `prek hook-impl` (ADR-0001 selected prek over pre-commit). On a fresh remote
#   clone prek is absent, so the very first commit fails until prek is installed
#   by hand -- the friction recorded in retro #2098, where `uv tool install prek`
#   had to be run manually. This installer reproduces that step at session start.
#
# Unlike the GitHub-release installers (install-rtk/apm/zizmor/...), prek is a
# uv-managed tool: `uv tool install prek` resolves and installs it, mirroring how
# CI runs it (`uv tool run prek` in the portable-pr-policy job and
# scripts/preflight_push_prek.py). It is intentionally NOT version-pinned here so
# the installed runner matches CI's unpinned `uv tool run prek`; a single shared
# pin for both surfaces is a broader, separable change. Because there is no
# release download, this script has no curl/sha256 path (and so is outside the
# scan_install_curl_retry_drift gate's scope by construction).
#
# Fail-open by design (CLAUDE.md section 4): a missing uv or a failed install
# logs to stderr and exits 0 rather than wedging session startup; CI's `Run prek`
# step is the backstop in that case.

set -euo pipefail

# Only run in a recognised remote agent environment -- Claude Code on the Web
# (CLAUDE_CODE_REMOTE=true) or Codex cloud (CODEX_CODE_REMOTE=true). Local dev and
# the nix devcontainer manage prek themselves, so the hook is a silent no-op
# there (no stdout/stderr, exit 0). Mirrors the install-uv.sh dual-signal gate.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ] && [ "${CODEX_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_session_path.sh
. "${SCRIPT_DIR}/_session_path.sh"

# uv tool installs executables into ~/.local/bin by default.
install_dir="${HOME}/.local/bin"

# Idempotent: reuse a prek already on PATH (a prior session-start run or a
# nix-provisioned binary). prek is unpinned, so presence alone is the skip key.
if command -v prek >/dev/null 2>&1; then
  persist_session_path "${install_dir}"
  echo "install-prek: prek already present ($(command -v prek))" >&2
  exit 0
fi

# uv is the install vehicle. install-uv.sh runs earlier in the SessionStart
# chain; if it has not provisioned uv yet, skip rather than abort -- CI runs prek
# as the backstop.
if ! command -v uv >/dev/null 2>&1; then
  echo "install-prek: uv not on PATH yet; skipping (CI runs prek as the backstop)." >&2
  exit 0
fi

echo "install-prek: installing prek via 'uv tool install prek' ..." >&2
if ! uv tool install prek >&2; then
  echo "install-prek: 'uv tool install prek' failed; skipping (CI runs prek as the backstop)." >&2
  exit 0
fi

persist_session_path "${install_dir}"
echo "install-prek: prek ready ($(command -v prek 2>/dev/null || echo "${install_dir}/prek"))" >&2
