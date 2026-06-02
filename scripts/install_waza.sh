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
# Provisioning order (refs #1103):
#   1. If waza is already on PATH, use it. The devcontainer flake.nix pins
#      waza as a fetchurl derivation, so inside the container this is a no-op
#      and no Go toolchain or network round-trip is required.
#   2. Otherwise fall back to a pinned `go install` -- the CI path, where
#      actions/setup-go provides Go but waza is not preinstalled.
#
# Acquisition is pinned to WAZA_VERSION for supply-chain hardening: an
# unpinned `@latest` would silently pull new releases into the gate. Fails
# loudly (exit != 0) on any install failure -- never swallowed.

set -euo pipefail

# Pinned waza release. Keep in sync with wazaVersion in flake.nix. Update
# deliberately, in a reviewed change, alongside a re-run of
# scripts/skill_quality_gate.py verify against all skills.
WAZA_VERSION="v0.33.0"

# 1. Prefer an already-provisioned waza (nix devcontainer flake, or a prior
#    install). Version pinning for this path is enforced declaratively by
#    flake.nix (container) and by scan_devcontainer_tool_drift.py.
if command -v waza >/dev/null 2>&1; then
  echo "install_waza: using waza on PATH: $(command -v waza) ($(waza --version 2>/dev/null | head -1))" >&2
  exit 0
fi

# 2. Fall back to a pinned `go install` (CI path).
if ! command -v go >/dev/null 2>&1; then
  echo "install_waza: ERROR: waza is not on PATH and no 'go' toolchain is available to install it." >&2
  echo "install_waza: inside the devcontainer waza is provided by flake.nix; elsewhere install Go first." >&2
  exit 1
fi

# `go install` drops the binary in $(go env GOBIN) or $(go env GOPATH)/bin.
GOBIN="$(go env GOBIN 2>/dev/null || true)"
if [ -z "${GOBIN}" ]; then
  GOBIN="$(go env GOPATH)/bin"
fi
case ":${PATH}:" in
  *":${GOBIN}:"*) ;;
  *) export PATH="${GOBIN}:${PATH}" ;;
esac

echo "install_waza: installing waza ${WAZA_VERSION} via go install ..." >&2
go install "github.com/microsoft/waza/cmd/waza@${WAZA_VERSION}"

# Verify the install produced an invocable binary. Fail loudly rather than
# letting the gate run against nothing.
if ! command -v waza >/dev/null 2>&1; then
  echo "install_waza: ERROR: waza not found on PATH after install (looked in ${GOBIN})." >&2
  exit 1
fi
echo "install_waza: waza ${WAZA_VERSION} ready at ${GOBIN}/waza" >&2
