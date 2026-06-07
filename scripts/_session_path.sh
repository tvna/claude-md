#!/usr/bin/env bash
# Shared helper sourced by the SessionStart provisioning scripts
# (install-uv.sh, install-rtk.sh, session_uv_local_pin.sh). It holds the one
# PATH-persistence routine those three scripts previously each reimplemented --
# byte-identical logic that only differed by the directory variable name.
#
# persist_session_path <dir>
#   Put <dir> on PATH for the current process and persist it for the rest of
#   the session. A no-op when <dir> is already on PATH. Otherwise it appends an
#   `export PATH="<dir>:$PATH"` line to $CLAUDE_ENV_FILE (when the harness set
#   one -- it is sourced before the first agent step) and exports the prefixed
#   PATH into the current process.
#
# This file is meant to be sourced, not executed: it only defines a function
# and has no side effects at source time, so it deliberately does not set shell
# options -- the sourcing script owns `set -euo pipefail`.

persist_session_path() {
  local dir="$1"
  # An empty dir would prepend an empty PATH element (== cwd); refuse loudly
  # rather than silently widening PATH (CLAUDE.md section 4).
  if [ -z "${dir}" ]; then
    echo "persist_session_path: refusing to add an empty directory to PATH" >&2
    return 2
  fi
  case ":${PATH}:" in
    *":${dir}:"*) return 0 ;;
  esac
  if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
    echo "export PATH=\"${dir}:\$PATH\"" >> "${CLAUDE_ENV_FILE}"
  fi
  export PATH="${dir}:${PATH}"
}
