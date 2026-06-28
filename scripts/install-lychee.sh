#!/usr/bin/env bash
# SessionStart hook: provision the pinned lychee (lycheeverse/lychee) binary onto
# PATH in Claude Code on the Web (CLAUDE_CODE_REMOTE=true) sessions.
#
# Why this exists (Refs #1610):
#   lychee is a Rust link checker whose offline local-link + heading-fragment
#   checking overlaps scripts/scan_markdown_links.py. It is being run ALONGSIDE
#   that gate during an effectiveness-measurement phase; nothing is removed. This
#   installer only makes the binary available for explicit `lychee ...` use.
#   lychee is deliberately NOT wired into flake.nix's devShell / sharedPackages,
#   so this web-only installer is the single provisioning path for it.
#
# Shape mirrors scripts/install-rtk.sh exactly: flake.nix is the single source
# of truth for the version, release asset, and SHA256 (lycheeVersion +
# lycheeNative.<system>); scripts/flake_pin.py reads them at runtime so there is
# exactly one place to update on a bump. NOTE: lychee's release tag is
# ``lychee-v<version>`` (not ``v<version>``); the URL prefix below mirrors the
# flake_pin.py url_template for this tool.

set -euo pipefail

# Only run in a recognised remote agent environment -- Claude Code on the Web
# (CLAUDE_CODE_REMOTE=true) or Codex cloud (CODEX_CODE_REMOTE=true, set by the
# operator; mirrors install-uv.sh). Local dev and the nix devcontainer do not
# provision lychee at all (remote-agent-only by design), so the hook is a silent
# no-op there (no stdout/stderr, exit 0).
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ] && [ "${CODEX_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_session_path.sh
. "${SCRIPT_DIR}/_session_path.sh"
# shellcheck source=scripts/_retry.sh
. "${SCRIPT_DIR}/_retry.sh"

# Map this platform to the nix system double that flake.nix's lycheeNative block
# enumerates. An unsupported arch is a non-fatal skip: the binary is an
# enhancement, not a session prerequisite, so do not abort session startup.
arch="$(uname -m)"
nix_system=""
case "${arch}" in
  x86_64 | amd64) nix_system="x86_64-linux" ;;
  aarch64 | arm64) nix_system="aarch64-linux" ;;
  *)
    echo "install-lychee: no pinned lychee asset for arch '${arch}'; skipping." >&2
    exit 0
    ;;
esac

if ! command -v python3 >/dev/null 2>&1; then
  echo "install-lychee: python3 is required to read the pinned lychee coordinates; skipping." >&2
  exit 0
fi

# Resolve version, asset, and sha256-hex from flake.nix (single source of truth).
pin="$(python3 "${SCRIPT_DIR}/flake_pin.py" resolve --tool lychee --system "${nix_system}")"
version="$(printf '%s\n' "${pin}" | sed -n '1p')"
asset="$(printf '%s\n' "${pin}" | sed -n '2p')"
sha="$(printf '%s\n' "${pin}" | sed -n '3p')"

install_dir="${HOME}/.local/bin"
dest="${install_dir}/lychee"

# Idempotent: reuse a lychee already on PATH at the pinned version (e.g. a prior
# session-start run).
if command -v lychee >/dev/null 2>&1; then
  current="$(lychee --version 2>/dev/null | awk '{print $NF}')"
  if [ "${current}" = "${version}" ]; then
    persist_session_path "${install_dir}"
    echo "install-lychee: lychee ${version} already present ($(command -v lychee))" >&2
    exit 0
  fi
fi

mkdir -p "${install_dir}"

# Download the pinned release tarball into a temp dir, verify its SHA256, then
# extract the lychee binary and install it atomically. rename(2) on one
# filesystem is atomic, so a concurrent reader never sees a half-written binary.
tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT
tarball="${tmpdir}/${asset}"
url="https://github.com/lycheeverse/lychee/releases/download/lychee-v${version}/${asset}"

echo "install-lychee: downloading pinned ${asset} v${version} ..." >&2
retry_download "${url}" "${tarball}" "lychee" "scripts/install-lychee.sh" || exit 0
echo "${sha}  ${tarball}" | sha256sum -c - >&2

# lychee's tarball unpacks to ``lychee-<target>/lychee`` (a nested dir), so
# locate the binary by name rather than assuming a bare layout.
tar -xzf "${tarball}" -C "${tmpdir}"
binary="$(find "${tmpdir}" -name lychee -type f | head -n 1)"
if [ -z "${binary}" ]; then
  echo "install-lychee: ERROR: ${asset} did not contain a 'lychee' binary." >&2
  exit 1
fi

staged="$(mktemp "${install_dir}/.lychee.XXXXXX")"
trap 'rm -rf "${tmpdir}"; rm -f "${staged}"' EXIT
cp "${binary}" "${staged}"
chmod 0755 "${staged}"
mv -f "${staged}" "${dest}"
trap 'rm -rf "${tmpdir}"' EXIT

persist_session_path "${install_dir}"
echo "install-lychee: lychee v${version} ready at ${dest} ($("${dest}" --version 2>/dev/null | head -1))" >&2
