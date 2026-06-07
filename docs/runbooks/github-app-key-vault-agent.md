# Source the GitHub App key from a Vault Agent sink (local host)

Operator procedure for keeping the GitHub App private key off the environment on
a developer local host by letting a HashiCorp **Vault Agent** render it to a
`0600` sink file that the MCP launcher reads via `GITHUB_APP_PRIVATE_KEY_FILE`
(Refs #1428). The App ID and Installation ID are not secret and stay in `env`.

This targets a local host with **HCP Vault** and Vault Agent **auto-auth**
(AppRole). The remote execution environment and the devcontainer keep the
existing `GITHUB_APP_PRIVATE_KEY` environment-variable injection documented in
[`../standards/github-mcp-app-auth.md`](../standards/github-mcp-app-auth.md).

## How it fits together

`mint_github_app_token.py` reads the PEM from `GITHUB_APP_PRIVATE_KEY` when set,
otherwise from the file named by `GITHUB_APP_PRIVATE_KEY_FILE`. `mcp_github_launch.sh`
accepts either before launch. Vault Agent owns the file: it auto-auths to HCP
Vault, renders the PEM through a `template` stanza, and refreshes it on lease
renewal. The only on-host credential is the Agent's AppRole identity
(`role_id` / `secret_id` files, `0600`) -- not the PEM, and not a long-lived
env secret.

## 1. Store the key in HCP Vault

```sh
export VAULT_ADDR="https://<cluster>.vault.<region>.hashicorp.cloud:8200"
export VAULT_NAMESPACE="admin"          # HCP default namespace
vault login                              # HCP admin token, one-time setup
vault kv put secret/github-app private_key=@app-private-key.pem
```

## 2. Read policy and AppRole (the Agent identity)

`github-app-read.hcl`:

```hcl
path "secret/data/github-app" { capabilities = ["read"] }
```

```sh
vault policy write github-app-read github-app-read.hcl
vault auth enable approle    # if not already enabled
vault write auth/approle/role/github-app \
  token_policies="github-app-read" token_ttl=20m token_max_ttl=1h secret_id_ttl=24h

install -m 0700 -d /etc/github-app
vault read  -field=role_id      auth/approle/role/github-app/role-id   > /etc/github-app/role_id
vault write -f -field=secret_id auth/approle/role/github-app/secret-id > /etc/github-app/secret_id
chmod 0600 /etc/github-app/role_id /etc/github-app/secret_id
```

## 3. Vault Agent config

`agent.hcl`:

```hcl
vault {
  address   = "https://<cluster>.vault.<region>.hashicorp.cloud:8200"
  namespace = "admin"
}
auto_auth {
  method "approle" {
    mount_path = "auth/approle"
    config = {
      role_id_file_path                   = "/etc/github-app/role_id"
      secret_id_file_path                 = "/etc/github-app/secret_id"
      remove_secret_id_file_after_reading = false
    }
  }
  sink "file" { config = { path = "/run/github-app/agent-token" } }
}
template {
  destination = "/home/<user>/.config/github-app/private-key.pem"
  perms       = "0600"
  contents    = "{{ with secret \"secret/data/github-app\" }}{{ .Data.data.private_key }}{{ end }}"
}
```

```sh
install -m 0700 -d "$HOME/.config/github-app" /run/github-app
vault agent -config=agent.hcl    # run as a daemon, e.g. systemd --user
```

The `sink` holds the Agent's own token, not the PEM. The `template` renders the
PEM to the `0600` destination and re-renders it on renewal.

## 4. Point the launcher at the sink

```sh
export GITHUB_APP_ID=123456
export GITHUB_APP_INSTALLATION_ID=7891011
export GITHUB_APP_PRIVATE_KEY_FILE="$HOME/.config/github-app/private-key.pem"
# Do NOT set GITHUB_APP_PRIVATE_KEY -- the file source is used when it is unset.
```

## 5. Verify without exposing the value

```sh
tok="$(python3 scripts/mint_github_app_token.py)" || echo "mint failed"
curl -s -o /dev/null -w '%{http_code}\n' \
  -H "Authorization: token ${tok}" \
  -H "Accept: application/vnd.github+json" \
  "${GITHUB_API_URL:-https://api.github.com}/installation/repositories"
unset tok
```

A `200` confirms the sink file, App ID, and Installation ID are wired correctly.

## Networking

The local host must reach the HCP Vault cluster address and `api.github.com`.
No repository egress allowlist change is needed -- the allowlist files under
`.devcontainer/network/` govern the devcontainer, not a local host.

## Rotation

- The PEM rotates at the App (see the standard doc); Vault Agent re-renders the
  sink on the next lease renewal once the new value is stored with `vault kv put`.
- The AppRole `secret_id` is short-lived (`secret_id_ttl`); reissue it and update
  `/etc/github-app/secret_id` on its cadence.
