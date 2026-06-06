#!/usr/bin/env bash
# SessionStart hook: provision the pinned waza (microsoft/waza) binary onto PATH
# in Claude Code on the Web (CLAUDE_CODE_REMOTE=true) sessions.
#
# Why this exists (Refs #1223):
#   The devcontainer provisions waza onto PATH via flake.nix (the waza-cli
#   fetchurl derivation) + `.devcontainer/scripts/configure-agent-runtime.sh`.
#   That nix path never runs in the web environment, so waza is absent there for
#   explicit `waza <cmd>` use. This installer reproduces only the *binary*
#   availability; it is the web-environment counterpart of install-rtk.sh /
#   install-actionlint.sh, completing the uv -> rtk -> apm -> waza provisioning
#   series.
#
#   NOTE: the separate scripts/install_waza.sh (skill-quality-gate / prek
#   installer, backed by waza_pin.py, no remote gate) is intentionally left
#   untouched -- it serves a different purpose and flake_pin.py documents that
#   waza_pin.py is deliberately not migrated.
#
# Shape (mirrors the existing precedents):
#   - install-uv.sh:  CLAUDE_CODE_REMOTE gate + $CLAUDE_ENV_FILE PATH persistence.
#   - install-rtk.sh: read the pin from flake.nix (single source of truth via
#     scripts/flake_pin.py), download the prebuilt release, and verify its
#     SHA256 with `sha256sum -c` before install -- the supply-chain guard.
#     waza ships a single bare release binary (no tarball), so the rtk template
#     applies minus the tar-extraction step: the asset is installed verbatim.
#
# flake.nix is the single source of truth for the version, release asset, and
# SHA256 (wazaVersion + wazaNative.<system>); scripts/flake_pin.py reads them at
# runtime so there is exactly one place to update on a bump.

set -euo pipefail

# Only run in the Claude Code on the Web remote environment. Local dev and the
# nix devcontainer provision waza themselves; the hook is a silent no-op there
# (no stdout/stderr, exit 0) so aligned hosts pay nothing.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_session_path.sh
. "${SCRIPT_DIR}/_session_path.sh"

# Map this platform to the nix system double that flake.nix's wazaNative block
# enumerates. An unsupported arch is a non-fatal skip: the binary is an
# enhancement, not a session prerequisite, so do not abort session startup.
arch="$(uname -m)"
nix_system=""
case "${arch}" in
  x86_64 | amd64) nix_system="x86_64-linux" ;;
  aarch64 | arm64) nix_system="aarch64-linux" ;;
  *)
    echo "install-waza: no pinned waza asset for arch '${arch}'; skipping." >&2
    exit 0
    ;;
esac

if ! command -v python3 >/dev/null 2>&1; then
  echo "install-waza: python3 is required to read the pinned waza coordinates; skipping." >&2
  exit 0
fi

# Resolve version, asset, and sha256-hex from flake.nix (single source of truth).
pin="$(python3 "${SCRIPT_DIR}/flake_pin.py" resolve --tool waza --system "${nix_system}")"
version="$(printf '%s\n' "${pin}" | sed -n '1p')"
asset="$(printf '%s\n' "${pin}" | sed -n '2p')"
sha="$(printf '%s\n' "${pin}" | sed -n '3p')"

install_dir="${HOME}/.local/bin"
dest="${install_dir}/waza"

# Idempotent: reuse a waza already on PATH at the pinned version (e.g. a prior
# session-start run, or a nix-provisioned binary).
if command -v waza >/dev/null 2>&1; then
  current="$(waza --version 2>/dev/null | awk '{print $NF}')"
  if [ "${current}" = "${version}" ]; then
    persist_session_path "${install_dir}"
    echo "install-waza: waza ${version} already present ($(command -v waza))" >&2
    exit 0
  fi
fi

mkdir -p "${install_dir}"

# Download the pinned release binary into a temp dir, verify its SHA256, then
# install it atomically. waza ships a single bare binary (no tarball), so there
# is no extraction step -- the downloaded asset IS the binary. rename(2) on one
# filesystem is atomic, so a concurrent reader never sees a half-written binary.
tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT
download="${tmpdir}/${asset}"
url="https://github.com/microsoft/waza/releases/download/v${version}/${asset}"

echo "install-waza: downloading pinned ${asset} v${version} ..." >&2
curl -fsSL "${url}" -o "${download}"
echo "${sha}  ${download}" | sha256sum -c - >&2

staged="$(mktemp "${install_dir}/.waza.XXXXXX")"
trap 'rm -rf "${tmpdir}"; rm -f "${staged}"' EXIT
cp "${download}" "${staged}"
chmod 0755 "${staged}"
mv -f "${staged}" "${dest}"
trap 'rm -rf "${tmpdir}"' EXIT

persist_session_path "${install_dir}"
echo "install-waza: waza v${version} ready at ${dest} ($("${dest}" --version 2>/dev/null | head -1))" >&2
