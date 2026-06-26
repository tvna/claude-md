#!/usr/bin/env bash
# SessionStart hook: provision the pinned apm (microsoft/apm) binary onto PATH
# in Claude Code on the Web (CLAUDE_CODE_REMOTE=true) sessions.
#
# Why this exists (Refs #1221, parent #1218):
#   The devcontainer provisions apm onto PATH via flake.nix (the apm-cli
#   fetchurl derivation) + `.devcontainer/scripts/configure-agent-runtime.sh`
#   (install_nix_binary apm-cli apm). That nix path never runs in the web
#   environment, so apm is absent there for explicit `apm <cmd>` use. This
#   installer reproduces only the *binary* availability; it is a sibling of
#   install-rtk.sh / install-waza.sh in the uv -> rtk -> apm -> waza
#   provisioning series.
#
# Shape (mirrors the existing precedents):
#   - install-uv.sh:  CLAUDE_CODE_REMOTE gate + $CLAUDE_ENV_FILE PATH persistence.
#   - install-rtk.sh: read the pin from flake.nix (single source of truth via
#     scripts/flake_pin.py), download the prebuilt release, and verify its
#     SHA256 with `sha256sum -c` before install -- the supply-chain guard.
#
# apm differs from rtk/waza in two ways that this script handles explicitly:
#   1. The release artifact is a `.tar.gz` whose name in flake.nix omits the
#      extension (apmNative.<sys>.archive = "apm-linux-x86_64"); flake_pin.py's
#      url_template appends ".tar.gz". The tarball unpacks to an *enclosing*
#      directory of the same name containing an `apm` ELF binary plus a sibling
#      `_internal/` (a PyInstaller onedir bundle), NOT a bare binary.
#   2. Because the bundle relies on the `_internal/` sibling, a bare symlink
#      would break it. This mirrors the flake apm-cli derivation: install the
#      whole bundle under ~/.local/libexec/apm and expose a thin wrapper at
#      ~/.local/bin/apm that execs the bundled binary.
#
# flake.nix is the single source of truth for the version, release archive, and
# SHA256 (apmVersion + apmNative.<system>); scripts/flake_pin.py reads them at
# runtime so there is exactly one place to update on a bump.

set -euo pipefail

# Only run in a recognised remote agent environment -- Claude Code on the Web
# (CLAUDE_CODE_REMOTE=true) or Codex cloud (CODEX_CODE_REMOTE=true, set by the
# operator; mirrors install-uv.sh). Local dev and the nix devcontainer provision
# apm themselves; the hook is a silent no-op there (no stdout/stderr, exit 0).
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ] && [ "${CODEX_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_session_path.sh
. "${SCRIPT_DIR}/_session_path.sh"
# shellcheck source=scripts/_retry.sh
. "${SCRIPT_DIR}/_retry.sh"

# Map this platform to the nix system double that flake.nix's apmNative block
# enumerates. An unsupported arch is a non-fatal skip: the binary is an
# enhancement, not a session prerequisite, so do not abort session startup.
arch="$(uname -m)"
nix_system=""
case "${arch}" in
  x86_64 | amd64) nix_system="x86_64-linux" ;;
  aarch64 | arm64) nix_system="aarch64-linux" ;;
  *)
    echo "install-apm: no pinned apm asset for arch '${arch}'; skipping." >&2
    exit 0
    ;;
esac

if ! command -v python3 >/dev/null 2>&1; then
  echo "install-apm: python3 is required to read the pinned apm coordinates; skipping." >&2
  exit 0
fi

# Resolve version, archive, and sha256-hex from flake.nix (single source of truth).
pin="$(python3 "${SCRIPT_DIR}/flake_pin.py" resolve --tool apm --system "${nix_system}")"
version="$(printf '%s\n' "${pin}" | sed -n '1p')"
archive="$(printf '%s\n' "${pin}" | sed -n '2p')"
sha="$(printf '%s\n' "${pin}" | sed -n '3p')"

install_dir="${HOME}/.local/bin"
libexec_dir="${HOME}/.local/libexec"
bundle_dir="${libexec_dir}/apm"
dest="${install_dir}/apm"

# Extract the bare semver from `apm --version`, which prints e.g.
#   "Agent Package Manager (APM) CLI version 0.12.1 (41ab121)"
# so the version is NOT the last whitespace token (that is the commit hash).
apm_semver() {
  "$1" --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1
}

# Idempotent: reuse an apm already on PATH at the pinned version (e.g. a prior
# session-start run, or a nix-provisioned binary).
if command -v apm >/dev/null 2>&1; then
  current="$(apm_semver "$(command -v apm)")"
  if [ "${current}" = "${version}" ]; then
    persist_session_path "${install_dir}"
    echo "install-apm: apm ${version} already present ($(command -v apm))" >&2
    exit 0
  fi
fi

mkdir -p "${install_dir}" "${libexec_dir}"

# Clean up every staging artifact on exit, whether or not the swap completed.
tmpdir=""
staged_dir=""
old_dir=""
staged_wrapper=""
cleanup() {
  if [ -n "${tmpdir}" ]; then rm -rf "${tmpdir}"; fi
  if [ -n "${staged_dir}" ]; then rm -rf "${staged_dir}"; fi
  if [ -n "${old_dir}" ]; then rm -rf "${old_dir}"; fi
  if [ -n "${staged_wrapper}" ]; then rm -f "${staged_wrapper}"; fi
}
trap cleanup EXIT

# Download the pinned release tarball into a temp dir, verify its SHA256, then
# extract the PyInstaller onedir bundle.
tmpdir="$(mktemp -d)"
tarball="${tmpdir}/${archive}.tar.gz"
url="https://github.com/microsoft/apm/releases/download/v${version}/${archive}.tar.gz"

echo "install-apm: downloading pinned ${archive}.tar.gz v${version} ..." >&2
retry_download "${url}" "${tarball}" "apm" "scripts/install-apm.sh" || exit 0
echo "${sha}  ${tarball}" | sha256sum -c - >&2

# The apm tarball unpacks to an enclosing directory of the same name holding the
# `apm` ELF binary and its sibling `_internal/` runtime bundle.
tar -xzf "${tarball}" -C "${tmpdir}"
extracted="${tmpdir}/${archive}"
if [ ! -f "${extracted}/apm" ] || [ ! -d "${extracted}/_internal" ]; then
  echo "install-apm: ERROR: ${archive}.tar.gz did not contain the expected apm bundle (apm + _internal/)." >&2
  exit 1
fi

# Stage the bundle on the same filesystem as the destination so the final move
# is an atomic rename(2). A non-empty directory cannot be atomically swapped in
# a single rename, so move any existing bundle aside first, then rename the
# staged bundle into the now-absent target -- the swap window is the two
# renames, not a half-copied tree.
staged_dir="$(mktemp -d "${libexec_dir}/.apm.XXXXXX")"
cp -R "${extracted}/." "${staged_dir}/"
chmod 0755 "${staged_dir}/apm"

if [ -e "${bundle_dir}" ]; then
  old_dir="$(mktemp -d "${libexec_dir}/.apm-old.XXXXXX")"
  mv "${bundle_dir}" "${old_dir}/apm"
fi
mv "${staged_dir}" "${bundle_dir}"
staged_dir=""

# Install the thin wrapper atomically, mirroring the flake apm-cli derivation's
# $out/bin/apm. The bundle path is embedded absolutely so the wrapper does not
# depend on HOME at call time.
staged_wrapper="$(mktemp "${install_dir}/.apm.XXXXXX")"
cat > "${staged_wrapper}" <<EOF
#!/usr/bin/env bash
exec "${bundle_dir}/apm" "\$@"
EOF
chmod 0755 "${staged_wrapper}"
mv -f "${staged_wrapper}" "${dest}"
staged_wrapper=""

persist_session_path "${install_dir}"
echo "install-apm: apm v${version} ready at ${dest} ($("${dest}" --version 2>/dev/null | head -1))" >&2
