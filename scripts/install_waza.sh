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
# flake.nix is the single source of truth for the pinned version, release
# asset, and SHA256 (wazaVersion + wazaNative.<system>). scripts/waza_pin.py
# reads them at runtime so there is exactly one place to update on a bump --
# no hardcoded copy here to drift (#1150). The SHA256 check below is the
# supply-chain guard: any mismatched or truncated download fails loud.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# 1. Prefer an already-provisioned waza (nix devcontainer flake, or a prior
#    install). Version pinning for this path is enforced declaratively by
#    flake.nix (container) and by scan_devcontainer_tool_drift.py.
if command -v waza >/dev/null 2>&1; then
  echo "install_waza: using waza on PATH: $(command -v waza) ($(waza --version 2>/dev/null | head -1))" >&2
  exit 0
fi

# Past step 1, the pinned coordinates are resolved from flake.nix via
# scripts/waza_pin.py, which needs python3.
if ! command -v python3 >/dev/null 2>&1; then
  echo "install_waza: ERROR: python3 is required to read the pinned waza coordinates from flake.nix." >&2
  exit 1
fi

# Map this platform to the nix system double that flake.nix's wazaNative
# block enumerates. Empty for platforms with no pinned prebuilt asset.
os="$(uname -s)"
arch="$(uname -m)"
nix_system=""
case "${os}:${arch}" in
  Linux:x86_64 | Linux:amd64) nix_system="x86_64-linux" ;;
  Linux:aarch64 | Linux:arm64) nix_system="aarch64-linux" ;;
esac

# 2. Download the pinned prebuilt binary resolved from flake.nix.
if [ -n "${nix_system}" ]; then
  # waza_pin.py prints three lines: version, asset, sha256-hex.
  pin="$(python3 "${SCRIPT_DIR}/waza_pin.py" resolve --system "${nix_system}")"
  version="$(printf '%s\n' "${pin}" | sed -n '1p')"
  asset="$(printf '%s\n' "${pin}" | sed -n '2p')"
  sha="$(printf '%s\n' "${pin}" | sed -n '3p')"

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
  url="https://github.com/microsoft/waza/releases/download/v${version}/${asset}"
  echo "install_waza: downloading pinned prebuilt ${asset} v${version} ..." >&2
  curl -fsSL "${url}" -o "${tmp}"
  echo "${sha}  ${tmp}" | sha256sum -c - >&2
  chmod 0755 "${tmp}"
  mv -f "${tmp}" "${dest}"
  trap - EXIT
  add_to_path
  echo "install_waza: waza v${version} ready at ${dest} ($("${dest}" --version 2>/dev/null | head -1))" >&2
  exit 0
fi

# 3. Portability backstop: no pinned prebuilt for this platform. Fall back to a
#    pinned `go install` (compiles from source) when Go is available.
version="$(python3 "${SCRIPT_DIR}/waza_pin.py" version)"
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

echo "install_waza: no pinned prebuilt for ${os}/${arch}; compiling v${version} via the Go toolchain ..." >&2
# Backstop only -- reached solely on a platform with no pinned prebuilt asset
# in flake.nix. The CI/devcontainer hot path never compiles (it uses the
# prebuilt download / on-PATH waza), so this never costs CI wall time.
go install "github.com/microsoft/waza/cmd/waza@v${version}" # compile-source-ack: portability backstop, no prebuilt for this platform (#1154)

# Verify the install produced an invocable binary. Fail loudly rather than
# letting the gate run against nothing.
if ! command -v waza >/dev/null 2>&1; then
  echo "install_waza: ERROR: waza not found on PATH after install (looked in ${GOBIN})." >&2
  exit 1
fi
echo "install_waza: waza v${version} ready at ${GOBIN}/waza" >&2
