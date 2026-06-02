#!/usr/bin/env bash
# Install microsoft/waza at a pinned version for the skill quality gate.
#
# waza (https://github.com/microsoft/waza) is a Go CLI that validates agent
# skills. We use only `waza check` (spec-compliance + token budget), which is
# fully local with no external data send. The `waza quality` LLM-as-Judge
# path is intentionally NOT used by any gate: it routes SKILL.md content
# through the embedded GitHub Copilot CLI to a judge model (external send,
# non-deterministic). See issue #1099.
#
# Acquisition is pinned to WAZA_VERSION for supply-chain hardening (#1099):
# an unpinned `@latest` would silently pull new releases into the gate.
# Idempotent: if the pinned binary is already on PATH, this is a no-op.
# Fails loudly (exit != 0) on any install failure -- never swallowed.

set -euo pipefail

# Pinned waza release. Update deliberately, in a reviewed change, alongside a
# re-run of scripts/skill_quality_gate.py verify against all skills.
WAZA_VERSION="v0.33.0"

# `go install` drops the binary in $(go env GOBIN) or $(go env GOPATH)/bin.
GOBIN="$(go env GOBIN 2>/dev/null || true)"
if [ -z "${GOBIN}" ]; then
  GOBIN="$(go env GOPATH)/bin"
fi

# Expose the Go bin dir for the rest of this process/session.
case ":${PATH}:" in
  *":${GOBIN}:"*) ;;
  *) export PATH="${GOBIN}:${PATH}" ;;
esac

# Resolve the module version embedded in a waza binary. `waza --version`
# reports "dev" for `go install`-built binaries, so we read the build info
# (`go version -m`), where the module pseudo/release version is reliable.
waza_mod_version() {
  go version -m "$1" 2>/dev/null \
    | awk '$1 == "mod" && $2 == "github.com/microsoft/waza" { print $3; exit }'
}

# If the pinned version is already installed, skip the network round-trip.
if command -v waza >/dev/null 2>&1; then
  current="$(waza_mod_version "$(command -v waza)")"
  if [ "${current}" = "${WAZA_VERSION}" ]; then
    echo "install_waza: waza ${WAZA_VERSION} already present at ${GOBIN}/waza" >&2
    exit 0
  fi
  echo "install_waza: replacing waza ${current:-unknown} with ${WAZA_VERSION}" >&2
fi

if ! command -v go >/dev/null 2>&1; then
  echo "install_waza: ERROR: 'go' toolchain not found on PATH; cannot install waza." >&2
  exit 1
fi

echo "install_waza: installing waza ${WAZA_VERSION} via go install ..." >&2
go install "github.com/microsoft/waza/cmd/waza@${WAZA_VERSION}"

# Verify the install actually produced an invocable binary at the pinned
# version. Fail loudly rather than letting the gate run against nothing.
if ! command -v waza >/dev/null 2>&1; then
  echo "install_waza: ERROR: waza not found on PATH after install (looked in ${GOBIN})." >&2
  exit 1
fi
installed="$(waza_mod_version "$(command -v waza)")"
if [ "${installed}" != "${WAZA_VERSION}" ]; then
  echo "install_waza: ERROR: expected waza ${WAZA_VERSION} but got '${installed:-none}'." >&2
  exit 1
fi
echo "install_waza: waza ${WAZA_VERSION} ready at ${GOBIN}/waza" >&2
