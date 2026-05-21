#!/usr/bin/env bash
# Pin `uv` to the CI UV_VERSION at session start.
#
# Invoked by the SessionStart hook registered in `.claude/settings.json`.
# Keep UV_VERSION below in lockstep with `.github/workflows/generate-agents.yml`
# (and `.github/workflows/verify-apm-drift.yml`). See `docs/remote-environment.md`
# for the update procedure and rationale.

set -euo pipefail

# Only run in the Claude Code on the Web remote environment.
# Local dev sessions manage their own uv; the hook is a no-op there.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

UV_VERSION="0.11.11"
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
  curl -fLsS "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/${ARCHIVE_NAME}.tar.gz" \
    -o "$tmpdir/uv.tar.gz"
  tar -xzf "$tmpdir/uv.tar.gz" -C "$tmpdir"
  mkdir -p "${INSTALL_DIR}"
  install -m 0755 "$tmpdir/${ARCHIVE_NAME}/uv" "${INSTALL_DIR}/uv"
fi

# Persist PATH for the rest of the session via $CLAUDE_ENV_FILE
# (the harness sources it before the first agent step).
case ":${PATH}:" in
  *":${INSTALL_DIR}:"*) ;;
  *)
    if [ -n "${CLAUDE_ENV_FILE:-}" ]; then
      echo "export PATH=\"${INSTALL_DIR}:\$PATH\"" >> "$CLAUDE_ENV_FILE"
    fi
    export PATH="${INSTALL_DIR}:$PATH"
    ;;
esac

uv --version >&2
uv sync --locked
