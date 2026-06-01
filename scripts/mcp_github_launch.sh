#!/usr/bin/env bash
# Launch the local GitHub MCP server with a freshly minted GitHub App token.
#
# Referenced as the `command` of the `github` stdio server in `.mcp.json`
# (Refs #1063). Claude Code runs this every time the MCP server (re)starts.
# Because the installation token is minted here, at launch, it is always fresh
# without any operator handoff -- folding token refresh into the launch itself.
#
# The token is passed to the container by *environment* (`-e NAME` with no
# value), never on the command line, so it never appears in `ps`/argv. The
# private key and the token are never echoed; on any missing credential the
# script fails loudly naming only the variable, so the operator sees a clear
# reason instead of an opaque MCP startup failure.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

: "${MCP_GITHUB_IMAGE:=ghcr.io/github/github-mcp-server}"
: "${MCP_GITHUB_DOCKER:=docker}"
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
# variable (never written to a file or a log) and exported so the container
# inherits it via `-e GITHUB_PERSONAL_ACCESS_TOKEN`.
if ! GITHUB_PERSONAL_ACCESS_TOKEN="$(${MCP_GITHUB_MINT})"; then
  echo "mcp_github_launch: failed to mint a GitHub App installation token." >&2
  exit 1
fi
export GITHUB_PERSONAL_ACCESS_TOKEN

exec "${MCP_GITHUB_DOCKER}" run -i --rm \
  -e GITHUB_PERSONAL_ACCESS_TOKEN \
  "${MCP_GITHUB_IMAGE}"
