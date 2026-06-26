#!/usr/bin/env bash
# SessionStart hook: provision the pinned actionlint (rhysd/actionlint) binary
# onto PATH in Claude Code on the Web (CLAUDE_CODE_REMOTE=true) sessions.
#
# Why this exists (Refs #1263, follow-up to #1256/#1258):
#   #1258 adopted actionlint as a workflow-lint gate. The pre-commit hook
#   soft-skips when the binary is absent; the hard gate is the nix-based
#   verify-actionlint.yml. The devcontainer gets actionlint via flake.nix
#   (sharedPackages -> agentPackages.actionlint-cli), but that nix path never
#   runs in the web environment, so actionlint is absent there and the local
#   workflow-lint hook always soft-skips during web development. This installer
#   reproduces the binary availability so the gate actually runs on the web.
#
# Shape (mirrors the two existing precedents):
#   - install-uv.sh:  CLAUDE_CODE_REMOTE gate + $CLAUDE_ENV_FILE PATH persistence.
#   - install-rtk.sh: read the pin from flake.nix (single source of truth via
#     scripts/flake_pin.py), download the prebuilt release, and verify its
#     SHA256 with `sha256sum -c` before install -- the supply-chain guard.
#
# flake.nix is the single source of truth for the version, release asset, and
# SHA256 (actionlintVersion + actionlintNative.<system>); scripts/flake_pin.py
# reads them at runtime so there is exactly one place to update on a bump.

set -euo pipefail

# Only run in a recognised remote agent environment -- Claude Code on the Web
# (CLAUDE_CODE_REMOTE=true) or Codex cloud (CODEX_CODE_REMOTE=true, set by the
# operator; mirrors install-uv.sh). Local dev and the nix devcontainer provision
# actionlint themselves; the hook is a silent no-op there (no stdout/stderr, exit 0).
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ] && [ "${CODEX_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=scripts/_session_path.sh
. "${SCRIPT_DIR}/_session_path.sh"
# shellcheck source=scripts/_retry.sh
. "${SCRIPT_DIR}/_retry.sh"

# Map this platform to the nix system double that flake.nix's actionlintNative
# block enumerates. An unsupported arch is a non-fatal skip: the binary is an
# enhancement, not a session prerequisite, so do not abort session startup.
arch="$(uname -m)"
nix_system=""
case "${arch}" in
  x86_64 | amd64) nix_system="x86_64-linux" ;;
  aarch64 | arm64) nix_system="aarch64-linux" ;;
  *)
    echo "install-actionlint: no pinned actionlint asset for arch '${arch}'; skipping." >&2
    exit 0
    ;;
esac

if ! command -v python3 >/dev/null 2>&1; then
  echo "install-actionlint: python3 is required to read the pinned actionlint coordinates; skipping." >&2
  exit 0
fi

# Resolve version, asset, and sha256-hex from flake.nix (single source of truth).
pin="$(python3 "${SCRIPT_DIR}/flake_pin.py" resolve --tool actionlint --system "${nix_system}")"
version="$(printf '%s\n' "${pin}" | sed -n '1p')"
asset="$(printf '%s\n' "${pin}" | sed -n '2p')"
sha="$(printf '%s\n' "${pin}" | sed -n '3p')"

install_dir="${HOME}/.local/bin"
dest="${install_dir}/actionlint"

# Idempotent: reuse an actionlint already on PATH at the pinned version (e.g. a
# prior session-start run, or a nix-provisioned binary).
if command -v actionlint >/dev/null 2>&1; then
  current="$(actionlint --version 2>/dev/null | head -1)"
  if [ "${current}" = "${version}" ]; then
    persist_session_path "${install_dir}"
    echo "install-actionlint: actionlint ${version} already present ($(command -v actionlint))" >&2
    exit 0
  fi
fi

mkdir -p "${install_dir}"

# Download the pinned release tarball into a temp dir, verify its SHA256, then
# extract the bare actionlint binary and install it atomically. rename(2) on one
# filesystem is atomic, so a concurrent reader never sees a half-written binary.
tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT
tarball="${tmpdir}/${asset}"
url="https://github.com/rhysd/actionlint/releases/download/v${version}/${asset}"

echo "install-actionlint: downloading pinned ${asset} v${version} ..." >&2
retry_download "${url}" "${tarball}" "actionlint" "scripts/install-actionlint.sh" || exit 0
echo "${sha}  ${tarball}" | sha256sum -c - >&2

# The actionlint tarball unpacks to a bare `actionlint` binary (plus docs) with
# no enclosing dir.
tar -xzf "${tarball}" -C "${tmpdir}"
if [ ! -f "${tmpdir}/actionlint" ]; then
  echo "install-actionlint: ERROR: ${asset} did not contain an 'actionlint' binary." >&2
  exit 1
fi

staged="$(mktemp "${install_dir}/.actionlint.XXXXXX")"
trap 'rm -rf "${tmpdir}"; rm -f "${staged}"' EXIT
cp "${tmpdir}/actionlint" "${staged}"
chmod 0755 "${staged}"
mv -f "${staged}" "${dest}"
trap 'rm -rf "${tmpdir}"' EXIT

persist_session_path "${install_dir}"
echo "install-actionlint: actionlint v${version} ready at ${dest} ($("${dest}" --version 2>/dev/null | head -1))" >&2
