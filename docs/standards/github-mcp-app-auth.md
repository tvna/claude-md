# GitHub MCP server: automated GitHub App token auth

Adopted contract for the local GitHub MCP server added by special exception for
CLI use (Refs #1063). It removes the manual personal access token (PAT) handoff:
the server is launched by a wrapper that mints a short-lived GitHub App
*installation* token at every start, so the credential is always fresh and no
secret is ever written to a tracked file.

## Components

| Artifact | Role |
|---|---|
| [`apm.yml`](../../apm.yml) | **Source of truth.** Declares the `github` stdio server (under `dependencies.mcp`) whose `command` is the launch wrapper. The `github` name keeps the server's tools under `mcp__github__*`, so the existing PreToolUse gates in [`.claude/settings.json`](../../.claude/settings.json) continue to cover them. |
| `.mcp.json` | The project-scope mirror that [`scripts/gen_mcp_json.py`](../../scripts/gen_mcp_json.py) renders from `apm.yml` at `SessionStart` (wired in `.claude/settings.json`). It is gitignored and never committed (prohibited per [`repo-scope.md`](repo-scope.md), #1067); it is regenerated locally, not committed. |
| [`scripts/mcp_github_launch.sh`](../../scripts/mcp_github_launch.sh) | Validates credentials, mints a token, and launches the server passing the token by environment (never on argv). Auto-selects a backend: Docker on a local host, the `github-mcp-server` binary where there is no Docker daemon. Fails loudly naming any missing variable or backend. |
| [`scripts/mint_github_app_token.py`](../../scripts/mint_github_app_token.py) | Builds an RS256 JWT (signed via `openssl`), exchanges it for an installation token, and prints the token to stdout only. |

## Runtime backends (local host and devcontainer)

The wrapper serves both environments from one launch path, selecting a backend at
runtime so the credential model is identical everywhere:

| Environment | Backend | How the binary/daemon is provided |
|---|---|---|
| Local host | `docker run ghcr.io/github/github-mcp-server` | Docker Desktop / Engine on the host |
| Devcontainer | `github-mcp-server stdio` | The `mcr.microsoft.com/devcontainers/base:ubuntu-24.04` devcontainer has no Docker daemon, so [`flake.nix`](../../flake.nix) pins `pkgs.github-mcp-server` (nixpkgs `nixos-25.05`, v0.3.0) and [`.devcontainer/scripts/configure-agent-runtime.sh`](../../.devcontainer/scripts/configure-agent-runtime.sh) installs it onto `/usr/local/bin` via `install_nix_binary`. |

`openssl` (for JWT signing) is present in the Ubuntu 24.04 base image; the
devcontainer egress allowlist already permits `api.github.com`, so token minting
and the server's API calls work without an allowlist change. Selection is
overridable for tests and edge cases via `MCP_GITHUB_DOCKER`, `MCP_GITHUB_BIN`,
`MCP_GITHUB_IMAGE`, and `MCP_GITHUB_MINT`.

## Why a launch wrapper, not a SessionStart hook

Claude Code resolves `${VAR}` in `.mcp.json` stdio `env` blocks at MCP launch
time, but does not load a secret file just before that expansion
(anthropics/claude-code#28942). A SessionStart hook runs in a child process and
cannot export a freshly minted token into the parent process environment.
Minting inside the launch wrapper folds the refresh into the launch itself, so
token currency is enforced by the harness on every (re)start rather than
remembered by the agent.

## Credential issuance path

The GitHub App private key is the only root secret. It is never committed; it is
injected as an environment variable in the CLI execution environment.

1. **Create a GitHub App** (Settings -> Developer settings -> GitHub Apps -> New).
   Disable Webhook (not needed for token minting).
2. **Grant minimal repository permissions** for the work the MCP server performs.
   Recommended least-privilege baseline:
   - Contents: Read and write
   - Issues: Read and write
   - Pull requests: Read and write
   - Metadata: Read-only (mandatory)
   Add others only when a concrete task needs them. Least privilege is enforced
   here, at the App, because the minted token inherits exactly the installation's
   granted permissions.
3. **Install the App** on the target account/org and, where possible, restrict it
   to only the repositories the MCP server should touch.
4. **Generate a private key** (PEM). Download it once; GitHub does not show it again.
5. **Record the identifiers**: the App ID (App settings page) and the Installation
   ID (the numeric id in the installation settings URL).

## Environment variables

Set these in the CLI execution environment (the remote execution environment's
secret mechanism, or your shell). Only `GITHUB_APP_PRIVATE_KEY` is secret.

| Variable | Secret | Value |
|---|---|---|
| `GITHUB_APP_ID` | no | numeric App ID |
| `GITHUB_APP_INSTALLATION_ID` | no | numeric Installation ID |
| `GITHUB_APP_PRIVATE_KEY` | **yes** | full PEM text of the App private key |
| `GITHUB_API_URL` | no | optional; GitHub Enterprise Server API base (default `https://api.github.com`) |

The private key value MUST NOT be pasted into chat, issues, PRs, commits, logs,
or screenshots. Store it only in the secret mechanism.

## Rotation

- Installation tokens expire automatically (about one hour) and are re-minted on
  every server start; there is nothing to rotate by hand.
- Rotate the App private key on a fixed cadence (suggested: every 90 days) and
  immediately on any suspected exposure: generate a new key, update the
  `GITHUB_APP_PRIVATE_KEY` secret, then delete the old key in the App settings.

## Verification (without exposing the value)

Run the minter in the configured environment and confirm a token comes back,
without printing it, then confirm the token is accepted by the API:

```sh
# Capture into a variable; never echo it.
tok="$(python3 scripts/mint_github_app_token.py)" || echo "mint failed"
# Expect HTTP 200; lists repositories visible to the installation.
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: token ${tok}" \
  -H "Accept: application/vnd.github+json" \
  "${GITHUB_API_URL:-https://api.github.com}/installation/repositories"
unset tok
```

A `200` confirms the App ID, installation ID, and private key are wired
correctly. Then start a CLI session: the `github` MCP server should connect with
no PAT prompt.

## Verification limits in CI

CI cannot mint a real token (no App credentials) or start the Docker server end
to end. The unit tests under `tests/` cover the minting logic with a real
`openssl`-signed JWT and a mocked HTTP exchange, assert the token never appears
in any log, and assert the wrapper passes the token by environment rather than
argv. The end-to-end launch above is an operator step.
