#!/usr/bin/env bash
# Ensure microsoft/waza is available for the skill quality gate.
#
# waza (https://github.com/microsoft/waza) is a Go CLI that validates agent
# skills. We use only `waza check` (spec-compliance + token budget), which is
# fully local with no external data send. The `waza quality` LLM-as-Judge
# path is intentionally NOT used by any gate: it routes SKILL.md content
# through the embedded GitHub Copilot CLI to a judge model (external send,
# non-deterministic). See issue #1099.
#
# Provisioning order (refs #1103, #1150):
#   1. If waza is already on PATH, use it. The devcontainer flake.nix pins
#      waza as a fetchurl derivation, so inside the container this is a no-op
#      and no download is required.
#   2. Otherwise download the pinned prebuilt release binary for this platform
#      and verify its SHA256 -- no Go toolchain and no source compile. This is
#      the CI path and the dominant fast path; it mirrors how flake.nix and
#      the uv installer already fetch pinned release artifacts.
#   3. Last resort: for a platform with no pinned prebuilt asset, fall back to
#      a pinned `go install` (compiles from source) when a Go toolchain is
#      present. Before #1150 this was the CI path and cost ~2 minutes per run
#      (Go toolchain fetch + compile); it is now only a portability backstop.
#
# Acquisition is pinned to WAZA_VERSION and a per-asset SHA256 for
# supply-chain hardening: an unpinned `@latest` or unverified download would
# silently pull arbitrary bytes into the gate. Fails loudly (exit != 0) on any
# download or checksum failure -- never swallowed.

set -euo pipefail

# Pinned waza release. Keep in sync with wazaVersion in flake.nix. Update
# deliberately, in a reviewed change, alongside a re-run of
# scripts/skill_quality_gate.py verify against all skills.
WAZA_VERSION="v0.33.0"

# Pinned SHA256 (hex) of each prebuilt release asset. These MUST stay in sync
# with flake.nix `wazaNative.<system>.hash`, which pins the SAME bytes as SRI
# base64 (sha256-...). The runtime `sha256sum -c` below is the supply-chain
# guard; a mismatch fails loud.
WAZA_SHA256_linux_amd64="c1a31a15d959d2cd536feb41cf7b20f94b0434a8e86949d3de3d21c1e3fb6ff3"
WAZA_SHA256_linux_arm64="552ba4f45e5f73e3e9c0c93429e2c59e21f1a4de8b9895f98f54deea7f03dfa8"

# 1. Prefer an already-provisioned waza (nix devcontainer flake, or a prior
#    install). Version pinning for this path is enforced declaratively by
#    flake.nix (container) and by scan_devcontainer_tool_drift.py.
if command -v waza >/dev/null 2>&1; then
  echo "install_waza: using waza on PATH: $(command -v waza) ($(waza --version 2>/dev/null | head -1))" >&2
  exit 0
fi

# 2. Download the pinned prebuilt binary for this platform.
os="$(uname -s)"
arch="$(uname -m)"
asset=""
sha=""
case "${os}:${arch}" in
  Linux:x86_64 | Linux:amd64)
    asset="waza-linux-amd64"
    sha="${WAZA_SHA256_linux_amd64}"
    ;;
  Linux:aarch64 | Linux:arm64)
    asset="waza-linux-arm64"
    sha="${WAZA_SHA256_linux_arm64}"
    ;;
esac

if [ -n "${asset}" ]; then
  install_dir="${HOME}/.local/bin"
  dest="${install_dir}/waza"

  add_to_path() {
    case ":${PATH}:" in
      *":${install_dir}:"*) ;;
      *) export PATH="${install_dir}:${PATH}" ;;
    esac
  }

  # Idempotent: reuse an already-installed binary. prek runs the
  # skill-quality-gate hook in PARALLEL across SKILL.md batches, so several
  # install_waza.sh processes can run at once; skipping the re-download when a
  # complete binary already exists avoids redundant fetches.
  if [ -x "${dest}" ]; then
    add_to_path
    echo "install_waza: reusing ${dest} ($("${dest}" --version 2>/dev/null | head -1))" >&2
    exit 0
  fi

  mkdir -p "${install_dir}"
  # Download + verify into a temp file in the SAME directory, then atomically
  # rename into place. A non-atomic `install` (open + truncate + write + chmod)
  # exposed a half-written, not-yet-executable binary to a concurrent exec
  # under prek's parallel hook execution -> PermissionError [Errno 13] (#1150).
  # rename(2) is atomic on one filesystem, so a concurrent reader always sees
  # either the old binary or the fully written, executable one -- never a
  # partial file.
  tmp="$(mktemp "${install_dir}/.waza.XXXXXX")"
  trap 'rm -f "${tmp}"' EXIT
  url="https://github.com/microsoft/waza/releases/download/${WAZA_VERSION}/${asset}"
  echo "install_waza: downloading pinned prebuilt ${asset} ${WAZA_VERSION} ..." >&2
  curl -fsSL "${url}" -o "${tmp}"
  echo "${sha}  ${tmp}" | sha256sum -c - >&2
  chmod 0755 "${tmp}"
  mv -f "${tmp}" "${dest}"
  trap - EXIT
  add_to_path
  echo "install_waza: waza ${WAZA_VERSION} ready at ${dest} ($("${dest}" --version 2>/dev/null | head -1))" >&2
  exit 0
fi

# 3. Portability backstop: no pinned prebuilt for this platform. Fall back to a
#    pinned `go install` (compiles from source) when Go is available.
if ! command -v go >/dev/null 2>&1; then
  echo "install_waza: ERROR: no pinned prebuilt asset for ${os}/${arch} and no 'go' toolchain to compile waza." >&2
  echo "install_waza: install waza manually, or use the devcontainer (flake.nix provides it)." >&2
  exit 1
fi

GOBIN="$(go env GOBIN 2>/dev/null || true)"
if [ -z "${GOBIN}" ]; then
  GOBIN="$(go env GOPATH)/bin"
fi
case ":${PATH}:" in
  *":${GOBIN}:"*) ;;
  *) export PATH="${GOBIN}:${PATH}" ;;
esac

echo "install_waza: no pinned prebuilt for ${os}/${arch}; installing ${WAZA_VERSION} via go install ..." >&2
go install "github.com/microsoft/waza/cmd/waza@${WAZA_VERSION}"

# Verify the install produced an invocable binary. Fail loudly rather than
# letting the gate run against nothing.
if ! command -v waza >/dev/null 2>&1; then
  echo "install_waza: ERROR: waza not found on PATH after install (looked in ${GOBIN})." >&2
  exit 1
fi
echo "install_waza: waza ${WAZA_VERSION} ready at ${GOBIN}/waza" >&2
