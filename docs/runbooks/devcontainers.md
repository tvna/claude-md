# VS Code devcontainers

Issue [#643](https://github.com/tvna/claude-md/issues/643) tracks the
move from Codex Desktop-only local development toward VS Code
devcontainers. The repository keeps two entrypoints so Claude and Codex
agent workflows can diverge without mutating the other environment.

## Entrypoints

| Agent | VS Code entrypoint | Nix shell |
|---|---|---|
| Claude | `.devcontainer/claude/devcontainer.json` | `nix develop .#claude` |
| Codex | `.devcontainer/codex/devcontainer.json` | `nix develop .#codex` |

Open either entrypoint with VS Code's "Dev Containers: Reopen in
Container..." flow. Both entrypoints pull a prebuilt GHCR image, enter
the matching Nix shell, and run:

```sh
uv sync --locked --group local
```

They also install the matching agent CLI into `/usr/local/bin` from the
Nix package outputs:

| Agent | CLI verification |
|---|---|
| Claude | `claude --version` |
| Codex | `codex --version` |

The prebuild definitions live under `.devcontainer/images/<agent>/`.
Those files are CI inputs only; local users should open the agent
entrypoints listed above. The prebuild definitions also run the agent
CLI install script so GHCR images already contain the Nix-built CLI
symlink.

## Prebuilt images

Local devcontainers use these images:

| Agent | Image |
|---|---|
| Claude | `ghcr.io/tvna/claude-md-devcontainer-claude:main` |
| Codex | `ghcr.io/tvna/claude-md-devcontainer-codex:main` |

The `Publish devcontainer images` workflow builds both images with the
Dev Containers CLI and pushes them to GHCR on `main` changes to
`.devcontainer/**`, the workflow itself, `flake.nix`, `flake.lock`,
`pyproject.toml`, or `uv.lock`. It also supports manual
`workflow_dispatch`.

Each publish creates two tags per agent:

- `main` for local VS Code entrypoints.
- the exact source commit SHA for audit and rollback.

If a devcontainer change merges before the publish workflow completes,
wait for that workflow to finish and then rebuild/reopen the local
container so Podman pulls the updated `:main` image. If publish fails,
use the commit-SHA tag from the last green publish as the rollback
reference while fixing the workflow.

If Podman cannot pull from GHCR with an authorization error after the
first publish, confirm that both GHCR packages are public. Private
packages require an explicit host login before VS Code can pull them:

```sh
/opt/podman/bin/podman login ghcr.io
```

## Runtime

Podman is the supported local runtime for these devcontainers. VS Code's
Dev Containers extension still names the compatibility setting
`dev.containers.dockerPath`; this repository sets that workspace value to
`podman` in `claude-md.code-workspace`.

Use the checked-in workspace file when opening the repository:

```sh
code claude-md.code-workspace
```

On macOS, VS Code launched from the Dock or Finder can miss Podman's CLI
directory even when it is present in an interactive shell. The workspace
prepends `/opt/podman/bin` to the macOS integrated terminal PATH so the
Podman CLI is visible to workspace tasks and diagnostics.

If you open the folder directly instead of the workspace file, set the
same value in VS Code user or workspace settings:

```json
{
  "dev.containers.dockerPath": "podman",
  "terminal.integrated.env.osx": {
    "PATH": "/opt/podman/bin:${env:PATH}"
  }
}
```

The Dev Containers extension talks to container engines through a CLI
compatibility surface. The VS Code documentation calls out Podman 5+ as
mostly compatible with Docker CLI commands and instructs users to set
`dev.containers.dockerPath` to `podman` for Linux, Windows, or macOS:
<https://code.visualstudio.com/remote/advancedcontainers/docker-options#_podman>.

On macOS or Windows, start the Podman VM before opening the container:

```sh
podman machine start
podman info
```

If Dev Containers can run `/opt/podman/bin/podman` but fails with
`unable to connect to Podman socket` or `connect: connection refused`,
the PATH is already resolved and the Podman VM or connection is the
remaining problem. Check the host state before retrying VS Code:

```sh
/opt/podman/bin/podman machine list
/opt/podman/bin/podman system connection list
/opt/podman/bin/podman machine start
/opt/podman/bin/podman info
```

If no machine exists, initialize one first:

```sh
/opt/podman/bin/podman machine init
/opt/podman/bin/podman machine start
```

If `machine list` is empty but `system connection list` still shows
`podman-machine-default` entries, the connection metadata is stale. That
state blocks `machine init` with `system connection "podman-machine-default"
already exists` while `machine start` still reports `VM does not exist`.
Remove each stale connection by name, then initialize the machine again.
`podman system connection rm` requires the connection name; running it
without an argument only prints `accepts 1 arg(s), received 0`.

```sh
/opt/podman/bin/podman system connection rm podman-machine-default
/opt/podman/bin/podman system connection rm podman-machine-default-root
/opt/podman/bin/podman machine init
/opt/podman/bin/podman machine start
/opt/podman/bin/podman info
```

Do not depend on Docker Desktop for this repository's devcontainer
workflow. If VS Code reports Docker-oriented wording, treat it as Dev
Containers compatibility terminology, not a Docker runtime requirement.

## Nix version management

`flake.nix` is the source of truth for container-visible tools. Shared
tools live in the common package set, while Claude-only and Codex-only
tools live in their own shell definitions. `flake.lock` pins the
resolved nixpkgs revision.

The Claude and Codex CLIs are pinned in `flake.nix` as Nix packages that
fetch the Linux x64 and arm64 npm release tarballs by hash. The
devcontainer post-create step links those Nix-built binaries into
`/usr/local/bin` so they are available in ordinary VS Code terminals as
well as inside `nix develop`.

To update pinned tool versions:

```sh
nix flake update
nix flake check
```

Then open a PR with both `flake.nix` and `flake.lock` changes. If a
tool cannot reasonably be managed by Nix, document the alternate pin in
this runbook before adding it to a devcontainer command.

Nix follows the same adoption cooldown as uv. The value in
`[tool.uv].exclude-newer` is the single source of truth, and
`scripts/nixpkgs_cooldown.py verify` fails if the locked nixpkgs
revision in `flake.lock` is newer than that window.

The Nix choice here is intentionally scoped to devcontainers. It does
not change the remote-session `uv` hook decision in
[`docs/standards/remote-environment.md`](../standards/remote-environment.md):
that hook installs one binary in a pre-existing remote environment,
while devcontainers provision a full reproducible workspace.

## Egress allowlist

The target network posture is denied by default with explicit outbound
destinations. Each agent entrypoint runs:

```sh
.devcontainer/scripts/apply-egress-allowlist.sh .devcontainer/network/<agent>.allowlist
```

The agent allowlist may include `.devcontainer/network/shared.allowlist`
with `@include shared.allowlist`, then append agent-specific endpoints.
Claude and Codex can therefore carry different service requirements.

The enforcement script resolves hostnames at container start and allows
TCP ports `22`, `80`, and `443` to those IPs, plus DNS to the container
resolver. It requires `NET_ADMIN`; the devcontainer entrypoints request
that capability through `runArgs`.

Rootless Podman can vary by host OS and Podman machine settings. If
allowlist application fails with a capability, iptables, or netfilter
error, first confirm that the Podman machine grants the requested
`NET_ADMIN` capability. Use `DEVCONTAINER_APPLY_EGRESS_ALLOWLIST=0` only
for diagnosis, then update the allowlist or runtime notes in a reviewed
PR with the observed failure mode.

Set `DEVCONTAINER_APPLY_EGRESS_ALLOWLIST=0` before container start only
for diagnosis. Any persistent broad exception needs a reviewed update to
the allowlist file with rationale.

## Verification

Run the same repository checks inside each container:

```sh
uv sync --locked
uv run ruff check scripts tests
uv run mypy
uv run pytest
uv run python scripts/preflight_all.py
```

For local/devcontainer-only test acceleration, the Nix shells and uv's
`local` dependency group include `pytest-xdist`. Use it only for local
feedback loops:

```sh
uv run --group local pytest -n auto
```

Do not change CI to xdist unless the sharding and coverage gates are
updated in the same PR.

When Podman or the Dev Containers extension is unavailable, run the
static checks on the host:

```sh
nix flake check
python3 -m json.tool .devcontainer/claude/devcontainer.json
python3 -m json.tool .devcontainer/codex/devcontainer.json
python3 -m json.tool claude-md.code-workspace
bash -n .devcontainer/scripts/apply-egress-allowlist.sh
bash -n .devcontainer/scripts/install-agent-cli.sh
nix build .#claude-cli
nix build .#codex-cli
```
