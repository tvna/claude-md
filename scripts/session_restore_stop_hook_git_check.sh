#!/usr/bin/env bash
# SessionStart hook: restore the corrected stop-hook-git-check.sh into the
# Claude Code on the Web container.
#
# Why this exists (Refs #2159):
#   ~/.claude/stop-hook-git-check.sh is provisioned by the remote environment
#   and is periodically restored to the upstream version, which silently
#   reverts any in-place fix (observed mid-session: the file was rewritten back
#   to the buggy variant alongside the other environment-managed hooks).
#   tests/fixtures/stop-hook-git-check.sh is the repo-owned source of truth for
#   the corrected hook, whose behaviour is validated by
#   tests/test_stop_hook_git_check.py. This script copies that fixture into
#   place at session start so the deployed hook matches the reviewed, tested
#   version instead of the reverted one.
#
#   The fixture is the single source: the smoke test validates its behaviour and
#   tests/test_session_restore_stop_hook_git_check.py pins that this script
#   deploys exactly those bytes, so the deployed hook cannot drift from the
#   tested source.
#
#   Named session_* (not install-*) on purpose: this is a Claude-only hook
#   restore, not a cross-agent toolchain provisioner, so it is intentionally
#   outside the install-*.sh three-way parity contract (see
#   scripts/scan_hook_coverage_drift.py / tests/test_installer_cross_agent_parity.py),
#   mirroring scripts/session_uv_local_pin.sh.
#
# Idempotent and fail-open: only copies when the destination is missing or
# differs, and never aborts session startup.

set -euo pipefail

# Only act in the Claude Code on the Web environment, where the ~/.claude hooks
# are environment-managed (and reverted). Local dev and the devcontainer ship
# no such hook; this script is a silent no-op there.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
src="${REPO_ROOT}/tests/fixtures/stop-hook-git-check.sh"
dest="${HOME}/.claude/stop-hook-git-check.sh"

if [ ! -f "${src}" ]; then
  echo "session_restore_stop_hook_git_check: source ${src} missing; skipping." >&2
  exit 0
fi

# Already in sync: nothing to do.
if [ -f "${dest}" ] && cmp -s "${src}" "${dest}"; then
  exit 0
fi

if ! mkdir -p "$(dirname "${dest}")"; then
  echo "session_restore_stop_hook_git_check: cannot create $(dirname "${dest}"); skipping." >&2
  exit 0
fi

# Install via a temp file in the destination directory, then rename(2) into
# place so a concurrent hook never observes a half-written file.
tmp="$(mktemp "${dest}.XXXXXX")" || {
  echo "session_restore_stop_hook_git_check: mktemp failed; skipping." >&2
  exit 0
}
if cp "${src}" "${tmp}" && chmod 0755 "${tmp}" && mv -f "${tmp}" "${dest}"; then
  echo "session_restore_stop_hook_git_check: deployed corrected hook to ${dest}" >&2
else
  rm -f "${tmp}"
  echo "session_restore_stop_hook_git_check: deploy failed; leaving existing hook in place." >&2
fi
