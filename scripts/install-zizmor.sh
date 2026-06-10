#!/usr/bin/env bash
# SessionStart hook: provision the pinned zizmor (zizmorcore/zizmor) binary onto
# PATH in Claude Code on the Web (CLAUDE_CODE_REMOTE=true) sessions.
#
# Why this exists (Refs #1610):
#   zizmor is a Rust GitHub Actions static-analysis tool whose template-injection
#   and unpinned-uses audits overlap scripts/scan_workflow_injection.py and
#   scripts/scan_workflow_action_pins.py. It is being run ALONGSIDE those gates
#   during an effectiveness-measurement phase; nothing is removed. This installer
#   only makes the binary available for explicit `zizmor ...` use. zizmor is
#   deliberately NOT wired into flake.nix's devShell / sharedPackages, so this
#   web-only installer is the single provisioning path for it.
#
# Shape mirrors scripts/install-rtk.sh exactly: flake.nix is the single source
# of truth for the version, release asset, and SHA256 (zizmorVersion +
# zizmorNative.<system>); scripts/flake_pin.py reads them at runtime so there is
# exactly one place to update on a bump.

set -euo pipefail

# Only run in the Claude Code on the Web remote environment. Local dev and the
# nix devcontainer do not provision zizmor at all (web-only by design), so the
# hook is a silent no-op there (no stdout/stderr, exit 0).
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_session_path.sh
. "${SCRIPT_DIR}/_session_path.sh"

# Map this platform to the nix system double that flake.nix's zizmorNative block
# enumerates. An unsupported arch is a non-fatal skip: the binary is an
# enhancement, not a session prerequisite, so do not abort session startup.
arch="$(uname -m)"
nix_system=""
case "${arch}" in
  x86_64 | amd64) nix_system="x86_64-linux" ;;
  aarch64 | arm64) nix_system="aarch64-linux" ;;
  *)
    echo "install-zizmor: no pinned zizmor asset for arch '${arch}'; skipping." >&2
    exit 0
    ;;
esac

if ! command -v python3 >/dev/null 2>&1; then
  echo "install-zizmor: python3 is required to read the pinned zizmor coordinates; skipping." >&2
  exit 0
fi

# Resolve version, asset, and sha256-hex from flake.nix (single source of truth).
pin="$(python3 "${SCRIPT_DIR}/flake_pin.py" resolve --tool zizmor --system "${nix_system}")"
version="$(printf '%s\n' "${pin}" | sed -n '1p')"
asset="$(printf '%s\n' "${pin}" | sed -n '2p')"
sha="$(printf '%s\n' "${pin}" | sed -n '3p')"

install_dir="${HOME}/.local/bin"
dest="${install_dir}/zizmor"

# Idempotent: reuse a zizmor already on PATH at the pinned version (e.g. a prior
# session-start run).
if command -v zizmor >/dev/null 2>&1; then
  current="$(zizmor --version 2>/dev/null | awk '{print $NF}')"
  if [ "${current}" = "${version}" ]; then
    persist_session_path "${install_dir}"
    echo "install-zizmor: zizmor ${version} already present ($(command -v zizmor))" >&2
    exit 0
  fi
fi

mkdir -p "${install_dir}"

# Download the pinned release tarball into a temp dir, verify its SHA256, then
# extract the bare zizmor binary and install it atomically. rename(2) on one
# filesystem is atomic, so a concurrent reader never sees a half-written binary.
tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT
tarball="${tmpdir}/${asset}"
url="https://github.com/zizmorcore/zizmor/releases/download/v${version}/${asset}"

echo "install-zizmor: downloading pinned ${asset} v${version} ..." >&2
curl -fsSL "${url}" -o "${tarball}"
echo "${sha}  ${tarball}" | sha256sum -c - >&2

# Locate the zizmor binary inside the extracted tree (the tarball holds a bare
# binary, but a `find` keeps this robust to a future nested layout).
tar -xzf "${tarball}" -C "${tmpdir}"
binary="$(find "${tmpdir}" -name zizmor -type f | head -n 1)"
if [ -z "${binary}" ]; then
  echo "install-zizmor: ERROR: ${asset} did not contain a 'zizmor' binary." >&2
  exit 1
fi

staged="$(mktemp "${install_dir}/.zizmor.XXXXXX")"
trap 'rm -rf "${tmpdir}"; rm -f "${staged}"' EXIT
cp "${binary}" "${staged}"
chmod 0755 "${staged}"
mv -f "${staged}" "${dest}"
trap 'rm -rf "${tmpdir}"' EXIT

persist_session_path "${install_dir}"
echo "install-zizmor: zizmor v${version} ready at ${dest} ($("${dest}" --version 2>/dev/null | head -1))" >&2
