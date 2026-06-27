#!/usr/bin/env bash
# Pin `uv` at session start to the version declared in pyproject.toml.
#
# Invoked by the SessionStart hooks registered in `.claude/settings.json` and
# `.codex/hooks.json`; the install path remains gated to Claude remote sessions
# until Codex documents a stable remote-only signal.
# Reads `[tool.uv].required-version` (an exact `==X.Y.Z` pin per #112) from
# `$CLAUDE_PROJECT_DIR/pyproject.toml`. See `docs/standards/remote-environment.md`
# for the rationale and update procedure.

set -euo pipefail

# Only run in a recognised remote environment.
# CLAUDE_CODE_REMOTE=true  -- Claude Code on the Web (set by the platform).
# CODEX_CODE_REMOTE=true   -- Codex cloud (set by the operator in the Codex
#                            cloud environment configuration; no built-in
#                            platform signal exists as of 2026-05-30,
#                            confirmed via openai/codex#13416).
# Local dev sessions manage their own uv; the hook is a no-op there.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ] && [ "${CODEX_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

# Read the pin via the shared helper (scripts/uv_pin.py). The helper
# enforces an exact `==X.Y.Z` PEP440 spec and is unit-tested by
# tests/test_uv_pin.py. tomllib is stdlib on Python 3.11+; the remote env
# ships 3.11+.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=scripts/_session_path.sh
. "${SCRIPT_DIR}/_session_path.sh"
# shellcheck source=scripts/_retry.sh
. "${SCRIPT_DIR}/_retry.sh"
PYPROJECT="${CLAUDE_PROJECT_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}/pyproject.toml"
UV_VERSION="$(python3 "$SCRIPT_DIR/uv_pin.py" read "$PYPROJECT")"
INSTALL_DIR="$HOME/.local/bin"
ARCHIVE_NAME="uv-x86_64-unknown-linux-gnu"

current=""
if command -v uv >/dev/null 2>&1; then
  current="$(uv --version | awk '{print $2}')"
fi

if [ "${current}" != "${UV_VERSION}" ]; then
  echo "install-uv: installing uv ${UV_VERSION} (was: ${current:-none})" >&2
  tmpdir="$(mktemp -d)"
  trap 'rm -rf "$tmpdir"' EXIT
  url="https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/${ARCHIVE_NAME}.tar.gz"
  retry_download "$url" "$tmpdir/uv.tar.gz" "uv" "scripts/install-uv.sh" || exit 0
  tar -xzf "$tmpdir/uv.tar.gz" -C "$tmpdir"
  mkdir -p "${INSTALL_DIR}"
  install -m 0755 "$tmpdir/${ARCHIVE_NAME}/uv" "${INSTALL_DIR}/uv"
fi

# Persist PATH for the rest of the session via $CLAUDE_ENV_FILE
# (the harness sources it before the first agent step).
persist_session_path "${INSTALL_DIR}"

uv --version >&2
uv sync --locked
