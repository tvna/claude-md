#!/usr/bin/env bash
# Install the repo-pinned `uv` into a workspace-local prefix so a host that
# manages uv through a package manager (e.g. Homebrew) does not need to match
# `[tool.uv].required-version`. Brew-independent workaround for #1205.
#
# Intended to be invoked by the `folderOpen` task in `claude-md.code-workspace`
# (also runnable by hand). The version is read at runtime via the shared helper
# `scripts/uv_pin.py read` (no version literal lives here -- see the uv pin
# drift gate in `.github/workflows/verify-agents.yml`). The pinned binary is
# downloaded from the official Astral installer at astral.sh, the same trust
# origin `flake.nix` fetches the Nix-pinned uv from.
#
# The install prefix is intentionally version-agnostic so the matching PATH
# entry in the `.code-workspace` never has to name a version; this script
# self-heals the prefix when the pin moves.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PYPROJECT="${SCRIPT_DIR}/../pyproject.toml"
VERSION="$(python3 "${SCRIPT_DIR}/uv_pin.py" read "${PYPROJECT}")"

# Version-agnostic prefix: `UV_UNMANAGED_INSTALL` drops `uv`/`uvx` here and
# disables self-update, so the host's package-managed uv stays untouched.
PREFIX="${UV_PIN_DIR:-${HOME}/.uv-pins/claude-md}"
UV_BIN="${PREFIX}/uv"

current=""
if [ -x "${UV_BIN}" ]; then
  current="$("${UV_BIN}" --version 2>/dev/null | awk '{print $2}')"
fi

if [ "${current}" = "${VERSION}" ]; then
  echo "setup-pinned-uv: ${UV_BIN} already at ${VERSION}" >&2
  exit 0
fi

echo "setup-pinned-uv: installing uv ${VERSION} into ${PREFIX} (was: ${current:-none})" >&2
curl -LsSf "https://astral.sh/uv/${VERSION}/install.sh" | env UV_UNMANAGED_INSTALL="${PREFIX}" sh

installed="$("${UV_BIN}" --version 2>/dev/null | awk '{print $2}')"
if [ "${installed}" != "${VERSION}" ]; then
  echo "setup-pinned-uv: ERROR expected uv ${VERSION}, got '${installed:-none}' at ${UV_BIN}" >&2
  exit 1
fi

echo "setup-pinned-uv: ${UV_BIN} -> ${installed}" >&2
echo "setup-pinned-uv: ensure ${PREFIX} precedes the host uv on PATH (the .code-workspace does this for integrated terminals)" >&2
