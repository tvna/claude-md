#!/usr/bin/env bash
# SessionStart hook: provision the pinned betterleaks (betterleaks/betterleaks)
# binary onto PATH in Claude Code on the Web (CLAUDE_CODE_REMOTE=true) sessions.
#
# Why this exists (Refs #1610):
#   betterleaks is a Go secrets scanner (the gitleaks successor) whose
#   tracked-file scanning overlaps scripts/scan_secrets.py. It is being run
#   ALONGSIDE that gate during an effectiveness-measurement phase; nothing is
#   removed. This installer only makes the binary available for explicit
#   `betterleaks ...` use. betterleaks is deliberately NOT wired into flake.nix's
#   devShell / sharedPackages, so this web-only installer is the single
#   provisioning path for it.
#
# Shape mirrors scripts/install-rtk.sh exactly: flake.nix is the single source
# of truth for the version, release asset, and SHA256 (betterleaksVersion +
# betterleaksNative.<system>); scripts/flake_pin.py reads them at runtime so
# there is exactly one place to update on a bump. NOTE: betterleaks asset
# filenames embed the version, kept static in flake.nix (actionlint precedent).

set -euo pipefail

# Only run in a recognised remote agent environment -- Claude Code on the Web
# (CLAUDE_CODE_REMOTE=true) or Codex cloud (CODEX_CODE_REMOTE=true, set by the
# operator; mirrors install-uv.sh). Local dev and the nix devcontainer do not
# provision betterleaks at all (remote-agent-only by design), so the hook is a
# silent no-op there (no stdout/stderr, exit 0).
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ] && [ "${CODEX_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_session_path.sh
. "${SCRIPT_DIR}/_session_path.sh"
# shellcheck source=scripts/_retry.sh
. "${SCRIPT_DIR}/_retry.sh"

# Map this platform to the nix system double that flake.nix's betterleaksNative
# block enumerates. An unsupported arch is a non-fatal skip: the binary is an
# enhancement, not a session prerequisite, so do not abort session startup.
arch="$(uname -m)"
nix_system=""
case "${arch}" in
  x86_64 | amd64) nix_system="x86_64-linux" ;;
  aarch64 | arm64) nix_system="aarch64-linux" ;;
  *)
    echo "install-betterleaks: no pinned betterleaks asset for arch '${arch}'; skipping." >&2
    exit 0
    ;;
esac

if ! command -v python3 >/dev/null 2>&1; then
  echo "install-betterleaks: python3 is required to read the pinned betterleaks coordinates; skipping." >&2
  exit 0
fi

# Resolve version, asset, and sha256-hex from flake.nix (single source of truth).
pin="$(python3 "${SCRIPT_DIR}/flake_pin.py" resolve --tool betterleaks --system "${nix_system}")"
version="$(printf '%s\n' "${pin}" | sed -n '1p')"
asset="$(printf '%s\n' "${pin}" | sed -n '2p')"
sha="$(printf '%s\n' "${pin}" | sed -n '3p')"

install_dir="${HOME}/.local/bin"
dest="${install_dir}/betterleaks"

# Idempotent: reuse a betterleaks already on PATH at the pinned version (e.g. a
# prior session-start run).
if command -v betterleaks >/dev/null 2>&1; then
  current="$(betterleaks --version 2>/dev/null | awk '{print $NF}')"
  if [ "${current}" = "${version}" ]; then
    persist_session_path "${install_dir}"
    echo "install-betterleaks: betterleaks ${version} already present ($(command -v betterleaks))" >&2
    exit 0
  fi
fi

mkdir -p "${install_dir}"

# Download the pinned release tarball into a temp dir, verify its SHA256, then
# extract the betterleaks binary and install it atomically. rename(2) on one
# filesystem is atomic, so a concurrent reader never sees a half-written binary.
tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT
tarball="${tmpdir}/${asset}"
url="https://github.com/betterleaks/betterleaks/releases/download/v${version}/${asset}"

echo "install-betterleaks: downloading pinned ${asset} v${version} ..." >&2
retry_download "${url}" "${tarball}" "betterleaks" "scripts/install-betterleaks.sh" || exit 0
echo "${sha}  ${tarball}" | sha256sum -c - >&2

# The betterleaks tarball holds a bare ``betterleaks`` binary alongside
# LICENSE/README; locate it by name so a future layout change does not break us.
tar -xzf "${tarball}" -C "${tmpdir}"
binary="$(find "${tmpdir}" -name betterleaks -type f | head -n 1)"
if [ -z "${binary}" ]; then
  echo "install-betterleaks: ERROR: ${asset} did not contain a 'betterleaks' binary." >&2
  exit 1
fi

staged="$(mktemp "${install_dir}/.betterleaks.XXXXXX")"
trap 'rm -rf "${tmpdir}"; rm -f "${staged}"' EXIT
cp "${binary}" "${staged}"
chmod 0755 "${staged}"
mv -f "${staged}" "${dest}"
trap 'rm -rf "${tmpdir}"' EXIT

persist_session_path "${install_dir}"
echo "install-betterleaks: betterleaks v${version} ready at ${dest} ($("${dest}" --version 2>/dev/null | head -1))" >&2
