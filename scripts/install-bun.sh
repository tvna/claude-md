#!/usr/bin/env bash
# SessionStart hook: provision the pinned bun runtime onto PATH and materialise
# the Mermaid-gate dependencies in Claude Code on the Web sessions.
#
# Why this exists (Refs #1597):
#   The deterministic Mermaid syntax gate (scripts/scan_mermaid_syntax.py) runs
#   the official Mermaid parser via bun (scripts/mermaid_parse.mjs). The nix dev
#   shell and the devcontainer already provide bun (flake.nix), but that nix
#   path never runs in the web environment, so this installer is the
#   web-environment counterpart of install-uv.sh / install-rtk.sh / install-waza.sh.
#   It (1) ensures the pinned bun binary is on PATH and (2) runs
#   `bun install --frozen-lockfile` so node_modules (mermaid + jsdom, pinned by
#   package.json + bun.lock) exists for the local pre-commit gate. The hard CI
#   gate is verify-mermaid.yml, which provisions bun via nix instead.
#
# Supply-chain guard (mirrors install-rtk.sh): the pinned bun release zip is
# downloaded from GitHub Releases and its SHA256 is verified with `sha256sum -c`
# before install. BUN_VERSION + the per-arch SHA256 below are the single source
# of truth for the pin; bump all three together.
#
# This installer is idempotent and never aborts session startup: a bun already
# on PATH at the pinned version is reused without a download, and any failure in
# the (best-effort) dependency materialisation is a warning, not a hard error --
# the binary availability is what the session needs, and CI enforces the gate.

set -euo pipefail

# Only run in the Claude Code on the Web remote environment. Local dev and the
# nix devcontainer provision bun themselves; the hook is a silent no-op there.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
# shellcheck source=scripts/_session_path.sh
. "${SCRIPT_DIR}/_session_path.sh"

# Pinned bun release. Keep BUN_VERSION and the per-arch SHA256 in lockstep.
BUN_VERSION="1.3.11"

arch="$(uname -m)"
bun_arch=""
bun_sha=""
case "${arch}" in
  x86_64 | amd64)
    bun_arch="x64"
    bun_sha="8611ba935af886f05a6f38740a15160326c15e5d5d07adef966130b4493607ed"
    ;;
  aarch64 | arm64)
    bun_arch="aarch64"
    bun_sha="d13944da12a53ecc74bf6a720bd1d04c4555c038dfe422365356a7be47691fdf"
    ;;
  *)
    echo "install-bun: no pinned bun asset for arch '${arch}'; skipping." >&2
    exit 0
    ;;
esac

install_dir="${HOME}/.local/bin"
dest="${install_dir}/bun"

# Best-effort materialisation of the pinned mermaid + jsdom tree so the local
# gate (scripts/scan_mermaid_syntax.py) works in-session. Network failure here
# is a warning, not a session-aborting error.
materialise_deps() {
  if [ ! -f "${REPO_ROOT}/package.json" ] || [ ! -f "${REPO_ROOT}/bun.lock" ]; then
    return 0
  fi
  echo "install-bun: materialising Mermaid-gate deps (bun install --frozen-lockfile) ..." >&2
  if ! (cd "${REPO_ROOT}" && bun install --frozen-lockfile >&2); then
    echo "install-bun: warning: bun install failed; the Mermaid gate will soft-skip locally until deps are present." >&2
  fi
}

# Idempotent: reuse a bun already on PATH at the pinned version (e.g. the
# nix-provisioned binary or a prior session-start run).
if command -v bun >/dev/null 2>&1; then
  current="$(bun --version 2>/dev/null || true)"
  if [ "${current}" = "${BUN_VERSION}" ]; then
    echo "install-bun: bun ${BUN_VERSION} already present ($(command -v bun))" >&2
    materialise_deps
    exit 0
  fi
fi

if ! command -v unzip >/dev/null 2>&1; then
  echo "install-bun: unzip is required to install bun; skipping binary install." >&2
  exit 0
fi

mkdir -p "${install_dir}"

# Download the pinned release zip into a temp dir, verify its SHA256, extract,
# then install the binary atomically (rename(2) on one filesystem).
tmpdir="$(mktemp -d)"
trap 'rm -rf "${tmpdir}"' EXIT
asset="bun-linux-${bun_arch}.zip"
download="${tmpdir}/${asset}"
url="https://github.com/oven-sh/bun/releases/download/bun-v${BUN_VERSION}/${asset}"

echo "install-bun: downloading pinned ${asset} v${BUN_VERSION} ..." >&2
curl -fsSL "${url}" -o "${download}"
echo "${bun_sha}  ${download}" | sha256sum -c - >&2

unzip -q -o "${download}" -d "${tmpdir}"
extracted="${tmpdir}/bun-linux-${bun_arch}/bun"
if [ ! -f "${extracted}" ]; then
  echo "install-bun: expected binary not found at ${extracted}; skipping." >&2
  exit 0
fi

staged="$(mktemp "${install_dir}/.bun.XXXXXX")"
trap 'rm -rf "${tmpdir}"; rm -f "${staged}"' EXIT
cp "${extracted}" "${staged}"
chmod 0755 "${staged}"
mv -f "${staged}" "${dest}"
trap 'rm -rf "${tmpdir}"' EXIT

persist_session_path "${install_dir}"
echo "install-bun: bun v${BUN_VERSION} ready at ${dest} ($("${dest}" --version 2>/dev/null | head -1))" >&2
materialise_deps
