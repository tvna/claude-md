#!/usr/bin/env bash
# Launch the local GitHub MCP server with a freshly minted GitHub App token.
#
# Referenced as the `command` of the `github` stdio server in `.mcp.json`
# (Refs #1063). Claude Code runs this every time the MCP server (re)starts.
# Because the installation token is minted here, at launch, it is always fresh
# without any operator handoff -- folding token refresh into the launch itself.
#
# The token is passed by *environment* (`-e NAME` with no value for Docker, or
# the inherited process env for the binary), never on the command line, so it
# never appears in `ps`/argv. The private key and the token are never echoed; on
# any missing credential the script fails loudly naming only the variable, so the
# operator sees a clear reason instead of an opaque MCP startup failure.
#
# Two launch backends, auto-selected so one wrapper serves both environments:
#   * Docker (`docker run ghcr.io/github/github-mcp-server`) on a local host.
#   * the `github-mcp-server` binary (`github-mcp-server stdio`) where there is
#     no Docker daemon, e.g. this repo's devcontainer, which installs the
#     Nix-pinned binary onto PATH (see docs/standards/github-mcp-app-auth.md).
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

: "${MCP_GITHUB_IMAGE:=ghcr.io/github/github-mcp-server}"
: "${MCP_GITHUB_DOCKER:=docker}"
: "${MCP_GITHUB_BIN:=github-mcp-server}"
: "${MCP_GITHUB_MINT:=python3 ${SCRIPT_DIR}/mint_github_app_token.py}"

require_env() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    echo "mcp_github_launch: ${name} is not set; cannot start the GitHub MCP server." >&2
    echo "See docs/standards/github-mcp-app-auth.md for the App credential setup." >&2
    exit 1
  fi
}

require_env GITHUB_APP_ID
require_env GITHUB_APP_INSTALLATION_ID
require_env GITHUB_APP_PRIVATE_KEY

# Mint the short-lived installation token. The token is captured into a
# variable (never written to a file or a log) and exported so the chosen backend
# inherits it through the environment.
if ! GITHUB_PERSONAL_ACCESS_TOKEN="$(${MCP_GITHUB_MINT})"; then
  echo "mcp_github_launch: failed to mint a GitHub App installation token." >&2
  exit 1
fi
export GITHUB_PERSONAL_ACCESS_TOKEN

if command -v "${MCP_GITHUB_DOCKER}" >/dev/null 2>&1; then
  # `-e NAME` with no value passes the token by environment, not on argv.
  exec "${MCP_GITHUB_DOCKER}" run -i --rm \
    -e GITHUB_PERSONAL_ACCESS_TOKEN \
    "${MCP_GITHUB_IMAGE}"
elif command -v "${MCP_GITHUB_BIN}" >/dev/null 2>&1; then
  # The binary reads GITHUB_PERSONAL_ACCESS_TOKEN from the inherited environment.
  exec "${MCP_GITHUB_BIN}" stdio
else
  echo "mcp_github_launch: neither Docker ('${MCP_GITHUB_DOCKER}') nor the github-mcp-server binary ('${MCP_GITHUB_BIN}') is available." >&2
  echo "Install Docker, or provide the github-mcp-server binary (the devcontainer installs the Nix-pinned one on PATH)." >&2
  exit 1
fi
