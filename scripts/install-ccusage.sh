#!/usr/bin/env bash
# SessionStart hook: provision the pinned ccusage (ryoppippi/ccusage) binary
# onto PATH in Claude Code on the Web (CLAUDE_CODE_REMOTE=true) sessions.
#
# Why this exists (Refs #1404):
#   The devcontainer provisions ccusage onto PATH via flake.nix (the ccusage-cli
#   fetchurl derivation) + `.devcontainer/scripts/configure-agent-runtime.sh`
#   (install_nix_binary ccusage-cli ccusage). That nix path never runs in the web
#   environment, so ccusage is absent there for explicit `ccusage <cmd>` use.
#   This installer reproduces only the *binary* availability; it is a sibling of
#   install-rtk.sh / install-waza.sh / install-apm.sh in the
#   uv -> rtk -> apm -> actionlint -> waza -> ccusage provisioning series.
#
# Shape (mirrors the existing precedents):
#   - install-uv.sh:  CLAUDE_CODE_REMOTE gate + $CLAUDE_ENV_FILE PATH persistence.
#   - install-waza.sh: read the pin from flake.nix (single source of truth via
#     scripts/ccusage_pin.py), download the prebuilt release, and verify its
#     SHA256 with `sha256sum -c` before install -- the supply-chain guard.
#
# ccusage differs from the GitHub-Releases tools in its source: it ships
# per-system native binaries as npm scoped packages
# (@ccusage/ccusage-linux-<arch>). The tarball unpacks to the standard npm
# `package/` root holding `bin/ccusage`, a self-contained static-pie ELF (no
# Node runtime needed). ccusage_pin.py yields version + pkg + sha256-hex; this
# script builds the registry URL from pkg + version.
#
# flake.nix is the single source of truth for the version, scoped-package name,
# and SHA256 (ccusageVersion + ccusageNative.<system>); scripts/ccusage_pin.py
# reads them at runtime so there is exactly one place to update on a bump.

set -euo pipefail

# Only run in the Claude Code on the Web remote environment. Local dev and the
# nix devcontainer provision ccusage themselves; the hook is a silent no-op there
# (no stdout/stderr, exit 0) so aligned hosts pay nothing.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_session_path.sh
. "${SCRIPT_DIR}/_session_path.sh"

# Map this platform to the nix system double that flake.nix's ccusageNative block
# enumerates. An unsupported arch is a non-fatal skip: the binary is an
# enhancement, not a session prerequisite, so do not abort session startup.
arch="$(uname -m)"
nix_system=""
case "${arch}" in
  x86_64 | amd64) nix_system="x86_64-linux" ;;
  aarch64 | arm64) nix_system="aarch64-linux" ;;
  *)
    echo "install-ccusage: no pinned ccusage asset for arch '${arch}'; skipping." >&2
    exit 0
    ;;
esac

if ! command -v python3 >/dev/null 2>&1; then
  echo "install-ccusage: python3 is required to read the pinned ccusage coordinates; skipping." >&2
  exit 0
fi

# Resolve version, scoped-package name, and sha256-hex from flake.nix (SoT).
pin="$(python3 "${SCRIPT_DIR}/ccusage_pin.py" resolve --system "${nix_system}")"
version="$(printf '%s\n' "${pin}" | sed -n '1p')"
pkg="$(printf '%s\n' "${pin}" | sed -n '2p')"
sha="$(printf '%s\n' "${pin}" | sed -n '3p')"

install_dir="${HOME}/.local/bin"
dest="${install_dir}/ccusage"

# Idempotent: reuse a ccusage already on PATH at the pinned version (e.g. a prior
# session-start run, or a nix-provisioned binary).
if command -v ccusage >/dev/null 2>&1; then
  current="$(ccusage --version 2>/dev/null | awk '{print $NF}')"
  if [ "${current}" = "${version}" ]; then
    persist_session_path "${install_dir}"
    echo "install-ccusage: ccusage ${version} already present ($(command -v ccusage))" >&2
    exit 0
  fi
fi

mkdir -p "${install_dir}"

# Download the pinned npm tarball into a temp dir, verify its SHA256, then
# extract the bare ccusage binary and install it atomically. rename(2) on one
# filesystem is atomic, so a concurrent reader never sees a half-written binary.
tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT
tarball="${tmpdir}/${pkg}-${version}.tgz"
url="https://registry.npmjs.org/@ccusage/${pkg}/-/${pkg}-${version}.tgz"

echo "install-ccusage: downloading pinned @ccusage/${pkg} v${version} ..." >&2
curl -fsSL "${url}" -o "${tarball}"
echo "${sha}  ${tarball}" | sha256sum -c - >&2

# The npm tarball unpacks to a `package/` root holding `bin/ccusage`.
tar -xzf "${tarball}" -C "${tmpdir}"
if [ ! -f "${tmpdir}/package/bin/ccusage" ]; then
  echo "install-ccusage: ERROR: ${pkg}-${version}.tgz did not contain package/bin/ccusage." >&2
  exit 1
fi

staged="$(mktemp "${install_dir}/.ccusage.XXXXXX")"
trap 'rm -rf "${tmpdir}"; rm -f "${staged}"' EXIT
cp "${tmpdir}/package/bin/ccusage" "${staged}"
chmod 0755 "${staged}"
mv -f "${staged}" "${dest}"
trap 'rm -rf "${tmpdir}"' EXIT

persist_session_path "${install_dir}"
echo "install-ccusage: ccusage v${version} ready at ${dest} ($("${dest}" --version 2>/dev/null | head -1))" >&2
