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

Claude terminals run as user `claude`, and Codex terminals run as user
`codex`. The prebuilt images use `.devcontainer/images/features/agent-user`
to provide the matching agent name with UID 0. This is intentional for
rootless Podman on macOS: bind-mounted workspaces are writable by the
container UID mapped to the host user, while non-root UIDs cannot repair
ownership with `chown`. The local entrypoints set `remoteUser` to that
agent user with `updateRemoteUserUID` disabled so UID 0 is preserved.
Post-create workspace preparation fails fast if the workspace is not
writable before `uv sync` runs.

They also install the matching agent CLI into `/usr/local/bin` from the
Nix package outputs, and link the GitHub CLI to `/usr/local/bin/gh`:

| Agent | CLI verification |
|---|---|
| Claude | `claude --version` and `gh --version` |
| Codex | `codex --version` and `gh --version` |

Each agent entrypoint uses a mix of named volumes and host bind mounts
for login state:

| Agent | Path | Mechanism |
|---|---|---|
| Claude | `/home/claude/.claude` | named volume `claude-md-claude-session` |
| Claude | `/home/claude/.config/gh` | bind mount from `~/.config/gh` on the host |
| Codex | `/home/codex/.codex` | named volume `claude-md-codex-session` |
| Codex | `/home/codex/.config/gh` | bind mount from `~/.config/gh` on the host |

The agent session volume is scoped to the local Podman or Docker host.
The GitHub CLI login state is sourced directly from the host path
`~/.config/gh` so it survives container rebuilds and codex container
replacements without re-authentication (issue #902). Do not copy these
directories into the repository; they may contain tokens or session material.

To reset the persisted agent session, stop the affected container first,
then remove the agent-specific session volume from the container host:

```sh
podman volume rm claude-md-claude-session
podman volume rm claude-md-codex-session
```

To reset the GitHub CLI login state, run `gh auth logout` inside the
container, or delete `~/.config/gh/hosts.yml` on the host. If upgrading
from a configuration that used named gh volumes, prune the orphans:

```sh
podman volume rm claude-md-claude-gh claude-md-codex-gh 2>/dev/null || true
```

### gh config bind mount security (issue #919)

The bind mount is read-write so that token refresh inside the container
persists back to the host. A read-only variant (`type=bind,readonly`) was
evaluated but rejected: `gh auth refresh` and `gh auth login` inside the
container would silently succeed while writing to a tmpfs overlay, leaving
the host token stale on the next session. Read-write is the correct
configuration for this workflow.

Because the host's `~/.config/gh` directory is exposed to every process
in the container, its file modes must be restrictive. The host-side
`initializeCommand` runs `.devcontainer/scripts/check-gh-config-permissions.sh`
before the image and stale-container checks; it exits 1 and prints
remediation steps when modes are too permissive. The guard runs before
container startup because macOS/Podman bind mounts can report permissive
Linux modes inside the container even when the host files are already
restrictive. If the container fails to start with a permission error, fix
the modes on the host:

```sh
chmod 700 ~/.config/gh
chmod 600 ~/.config/gh/hosts.yml
```

Minimum required gh token scopes for this repository's workflows:

| Scope | Reason |
|---|---|
| `repo` | Create and update issues, PRs, and comments via `gh` or MCP tools |
| `read:org` | Read team membership when `gh api /orgs/...` calls are made |

`public_repo` is sufficient for read-only operations on a public repository.
Re-issue the token with tighter scopes if the current token has broader
access than the table above (e.g., `admin:org`, `write:packages`).

To verify the active token scopes inside the container:

```sh
gh auth status
```

### Cloud Codex sessions

Cloud-hosted Codex sessions (claude.ai/code, GitHub Actions, or other
remote environments) run on ephemeral hosts that do not share named
volumes or host bind mounts between sessions. The local bind-mount
approach above does not apply.

Instead, pass a personal access token as `GH_TOKEN` in the Codex
environment configuration:

1. Create a fine-grained PAT at `github.com/settings/tokens` with
   **Contents: read** and **Issues / Pull requests: read and write** on
   `tvna/claude-md`. Set an expiry of 90 days or less.
2. Add `GH_TOKEN=<token>` as an environment variable in the Codex
   environment settings (or the equivalent secret store for your
   integration). Do not commit the value to the repository.
3. Verify in a new session:

   ```sh
   gh auth status
   ```

   If `gh` reports `You are not logged into any GitHub hosts`, run:

   ```sh
   gh auth login --with-token <<< "$GH_TOKEN"
   ```

   Scripts that consume `GH_TOKEN` directly (such as
   `sanitize_history.py apply`) will pick up the environment variable
   without an explicit login step.

Rotate the PAT before expiry and update the Codex environment secret.
Record the next rotation date alongside the token owner.

The runtime setup writes DevContainer-local defaults into the mounted
agent home. Bash commands and GitHub MCP operations are allowed by
default inside the devcontainer so agent work can proceed without
per-command prompts. This scope is intentionally limited to the
container: the script writes only under the container user's home and
`/etc/profile.d` inside the image/container, never to host-side
`.claude`, `.codex`, or shell configuration. The same setup installs a
short prompt of the form `codex:claude-md(main)$` or
`claude:claude-md(main)$`, preserving the active agent, directory, and
git branch without the long VS Code default prefix.

For Codex, the same runtime setup also marks
`/workspaces/claude-md` with `trust_level = "trusted"` and links
`/usr/local/bin/bwrap` and `/usr/local/bin/python3`. Existing Codex
session volumes keep their old `/home/codex/.codex/config.toml` until
the post-create setup runs again.
If Codex still reports `codex_apps` MCP startup timeout, missing
`bubblewrap`, or SessionStart hook failures with exit code 127 (python3
not found), run this inside the Codex DevContainer, then restart Codex:

```sh
bash .devcontainer/scripts/configure-agent-runtime.sh codex
command -v bwrap
command -v python3
```

If Codex starts but later reports
`Falling back from WebSockets to HTTPS transport. request timed out`
followed by `Conversation interrupted`, treat that as a Codex CLI
transport failure, not a SessionStart or MCP startup failure. Do not
paste Codex logs or tokens into issues. First capture only the network
boundary checks below from inside the Codex DevContainer:

```sh
getent hosts api.openai.com auth.openai.com
curl -I --max-time 20 https://api.openai.com
curl -I --max-time 20 https://auth.openai.com
```

Interpretation:

- If `getent hosts` returns addresses for both hosts, DNS resolution is
  not the failing boundary.
- `HTTP/2 421` from `https://api.openai.com` still proves that TLS and
  HTTPS reached the OpenAI edge; it is not the same as a timeout.
- `HTTP/2 403` from `https://auth.openai.com` with
  `cf-mitigated: challenge` proves that the request reached Cloudflare
  and was challenged there. Record the status, `cf-mitigated`, and
  `cf-ray` fields only. Do not paste `Set-Cookie` values or full
  headers into issues.

If those fail, compare with the egress allowlist disabled for one
container start:

```sh
DEVCONTAINER_APPLY_EGRESS_ALLOWLIST=0
```

Then reopen the Codex DevContainer and retry the same `getent` and
`curl -I` commands. If disabling the allowlist changes the result, the
next fix belongs in `.devcontainer/network/codex.allowlist` or the
allowlist apply script. If the checks pass with and without the
allowlist, keep the issue scoped to Codex CLI transport behavior or the
upstream service path rather than changing repository network policy.

After the container opens, verify the runtime identity and workspace
write access before starting agent work:

```sh
id -un
touch .devcontainer-write-check
rm .devcontainer-write-check
which claude || which codex
gh --version
```

If VS Code fails before post-create with `unable to find user codex` or
`unable to find user claude`, it is reusing a stale container that was
created before the agent user existed, or it has a stale local copy of a
previously mutable GHCR image. That failure happens before the
repository's in-container preflight can run. The entrypoints run a
host-side `initializeCommand` that pulls the pinned image, verifies the
agent user exists in that image, rejects mutable `main` or `latest`
image tags, and removes only stale containers labelled for the same
workspace and config.

To run the same recovery manually, inspect the labelled container from
the host, then remove it only after the script reports it as stale:

```sh
.devcontainer/scripts/check-stale-agent-container.sh codex \
  --workspace /Users/tvna/Documents/GitOps/claude-md
.devcontainer/scripts/check-stale-agent-container.sh codex \
  --workspace /Users/tvna/Documents/GitOps/claude-md \
  --rm
```

Use `claude` instead of `codex` for the Claude entrypoint. Then reopen
the devcontainer so VS Code creates a fresh container from the pinned
GHCR image.

To force the full image refresh and stale-container cleanup path before
opening VS Code, run:

```sh
.devcontainer/scripts/ensure-agent-image.sh codex
```

The prebuild definitions live under `.devcontainer/images/<agent>/`.
Those files are CI inputs only; local users should open the agent
entrypoints listed above. The prebuild definitions also run the agent
CLI install script so GHCR images already contain the Nix-built CLI
symlink.

## Prebuilt images

Local devcontainers use immutable commit-SHA image tags. The currently
pinned images were published from `b417e5833394f6f04a6e9b1eefe48026c09b4089`:

| Agent | Image |
|---|---|
| Claude | `ghcr.io/tvna/claude-md-devcontainer-claude:b417e5833394f6f04a6e9b1eefe48026c09b4089` |
| Codex | `ghcr.io/tvna/claude-md-devcontainer-codex:b417e5833394f6f04a6e9b1eefe48026c09b4089` |

The `Publish devcontainer images` workflow builds both images with the
Dev Containers CLI and pushes them to GHCR on `main` changes to
`.devcontainer/**`, the workflow itself, `flake.nix`, `flake.lock`,
`pyproject.toml`, or `uv.lock`. It also supports manual
`workflow_dispatch`.

The workflow builds each agent image natively for `linux/amd64` and
`linux/arm64`, then publishes `main` and the exact source commit SHA as
multi-platform manifest tags. Apple Silicon hosts must resolve the
`linux/arm64` image variant. If VS Code Explorer or Source Control stays
in a loading state and container processes show `qemu-x86_64-static` for
VS Code Server, fileWatcher, extensionHost, or Git commands, the pinned
image SHA points at an amd64-only publish and should be updated after
the next successful multi-platform publish.

Each publish creates two runnable tags per agent:

- `main` as a moving convenience alias.
- the exact source commit SHA for local VS Code entrypoints, audit, and
  rollback.

The build job also maintains non-runnable BuildKit cache tags in GHCR:

- `buildcache-amd64`
- `buildcache-arm64`

Those cache tags are scoped per agent package and architecture, for
example `ghcr.io/tvna/claude-md-devcontainer-codex:buildcache-arm64`.
They are imported with `--cache-from` before each build and exported with
`--cache-to ... mode=max` after successful builds. They must not be used
as local devcontainer image pins. If a cache becomes suspect, delete only
the matching `buildcache-*` tag from GHCR or temporarily add
`--no-cache` while investigating; the runnable commit-SHA image tags
remain the source of truth for local users.

If a devcontainer image input changes, the publish workflow builds and
pushes the new image tag first, then opens a follow-up PR that updates
the pinned SHA tags in `.devcontainer/claude/devcontainer.json` and
`.devcontainer/codex/devcontainer.json`. Do not point local entrypoints
at `:main`; it can leave Podman and VS Code using different local
interpretations of the same mutable tag. The replacement pinned SHA must
be a successful multi-platform publish; verify it includes both
`linux/amd64` and `linux/arm64` before asking Apple Silicon users to
reopen the container. If publish fails, keep the commit-SHA tag from the
last green publish as the rollback reference while fixing the workflow.
Recurring DevContainer maintenance is tracked in
[#696](https://github.com/tvna/claude-md/issues/696). Generated image-pin
PRs reference that tracking issue instead of the resolved implementation
issue that originally introduced pin automation. The follow-up PR is
created with the `DEVCONTAINER_PIN_PR_TOKEN` environment secret because
this repository does not rely on the repository-level setting that lets
the default `GITHUB_TOKEN` create pull requests.

Issue and rotate that token as a fine-grained personal access token or a
GitHub App installation token with access limited to `tvna/claude-md`.
The minimum repository permissions are Metadata read, Contents read and
write, and Pull requests read and write. Store it only as
`DEVCONTAINER_PIN_PR_TOKEN` in the `devcontainer-image-pins` Environment,
not as a repository-wide secret. Set an expiry of 90 days or less for a
PAT, rotate it before expiry, and verify the handoff by triggering
`Publish devcontainer images` with `workflow_dispatch` and confirming
the `Update local devcontainer image pins` job opens or reuses the
generated image-pin PR without exposing the token value in logs.
Record the next rotation date with the Environment secret owner.

The `Update local devcontainer image pins` job requests GitHub
auto-merge for the generated PR immediately after `gh pr create`
succeeds. If a retry finds that the image-pin branch already exists with
an open PR, it requests auto-merge for that existing PR instead of
opening a duplicate. GitHub still waits for the repository's required
checks and rulesets before merging; the workflow only enables the
auto-merge request.

### Keeping the pin PR mergeable (`Refresh devcontainer pin PR`)

Native auto-merge stalls the moment `main` advances past the pin PR.
`main-protection` sets `strict_required_status_checks_policy: true`, so the
branch must be up to date before it can merge, while `required_linear_history`,
the `scripts/gate_update_pr_branch.py` hook, and the `non_fast_forward` rule on
`codex/*` all forbid rebasing or force-pushing the branch in place. The branch
therefore becomes `behind` and never merges on its own.

The `Refresh devcontainer pin PR` workflow (`devcontainer-pin-refresh.yml`)
closes that gap. On every push to `main` (and on `workflow_dispatch`) it runs
`python3 scripts/devcontainer_pin_pr.py refresh`: if an open pin PR is behind
`main`, it cuts a fresh branch off the latest `main`
(`codex/devcontainer-image-pins-<published-sha>-r-<main-short-sha>`), re-applies
the same pins as a single commit, opens a replacement PR with auto-merge
enabled, then comments on, closes, and deletes the stale PR/branch. The
replacement is opened before the old PR is closed, so a failure never leaves the
repository without an open pin PR. It reuses the `devcontainer-image-pins`
Environment and `DEVCONTAINER_PIN_PR_TOKEN`; no new secret is required. To merge
a stuck pin PR on demand, dispatch this workflow manually. Refs #1137.

### One-time setup for `DEVCONTAINER_PIN_PR_TOKEN`

1. Open `tvna/claude-md` -> **Settings** -> **Environments** ->
   `devcontainer-image-pins`.
2. Add the `DEVCONTAINER_PIN_PR_TOKEN` Environment secret described
   above.
3. Confirm the repository rulesets allow `github-actions[bot]` to push
   non-default generated branches such as
   `codex/devcontainer-image-pins-<sha>`.
4. Trigger `Publish devcontainer images` with `workflow_dispatch`, or
   wait for the next `main` publish, and confirm the
   `Update local devcontainer image pins` job opens or reuses the
   generated image-pin PR.
5. Confirm the generated branch commit shows `github-actions[bot]` as
   the author and the generated PR has auto-merge enabled.

The publish workflow intentionally watches only image-build inputs such
as `.devcontainer/images/**`, `.devcontainer/scripts/install-agent-cli.sh`,
`.devcontainer/scripts/configure-agent-runtime.sh`, and the Nix/uv
lockfiles. Local entrypoint pin updates do not trigger a new image
publish; that prevents an infinite loop where each automatic pin PR
creates another image tag and another pin PR.

To inspect the platforms available for a published image tag:

```sh
docker buildx imagetools inspect ghcr.io/tvna/claude-md-devcontainer-codex:<sha>
```

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

Codex also gets `bubblewrap` from nixpkgs. Its sandbox checks for `bwrap`
on `PATH`, so the Codex post-create runtime setup links the Nix-built
binary into `/usr/local/bin/bwrap` before interactive Codex use.

The Codex devcontainer sets `--security-opt=seccomp=unconfined` in
`runArgs` because Docker's default seccomp profile blocks the
`unshare(CLONE_NEWUSER)` and `mount(devpts)` syscalls that bwrap
requires to set up its sandbox. Without this flag, bwrap fails with
`Can't mount devpts on /newroot/dev/pts: Permission denied`. This flag
must live in the devcontainer definition; applying it as an interactive
workaround after container startup does not take effect. To confirm bwrap
can set up its sandbox after a container rebuild, run inside the Codex
devcontainer:

```sh
bwrap --dev /dev --proc /proc --tmpfs /tmp \
  --ro-bind /usr /usr --ro-bind /etc /etc \
  --unshare-all -- echo ok
```

Exit code 0 confirms devpts mounting succeeds without interactive fixes.

uv is pinned the same way, but its version is read from
`pyproject.toml` `[tool.uv].required-version` instead of being repeated
in `flake.nix`. This keeps the devcontainer `nix develop` shell aligned
with the repository lockfile policy and prevents older nixpkgs uv builds
from ignoring settings such as the `exclude-newer` cooldown. The
post-create runtime setup also links the pinned uv into `/usr/local/bin`
so plain terminals can run `uv` after setup.

To update pinned tool versions:

```sh
nix flake update
nix flake check
```

Then open a PR with both `flake.nix` and `flake.lock` changes when the
nixpkgs input changed. For uv bumps, update
`[tool.uv].required-version`, `uv.lock`, and the fixed-output hashes in
`flake.nix` together. If a tool cannot reasonably be managed by Nix,
document the alternate pin in this runbook before adding it to a
devcontainer command.

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
For Codex, keep both `api.openai.com` and `auth.openai.com` in
`.devcontainer/network/codex.allowlist`: the former covers API calls,
and the latter covers ChatGPT-mediated OAuth token exchange during
`codex login`.

The enforcement script resolves hostnames at container start and allows
TCP ports `22`, `80`, and `443` to those IPs, plus DNS to the container
resolver. It requires `NET_ADMIN`; the devcontainer entrypoints request
that capability through `runArgs`. The script runs directly inside the
Nix network shell. Do not wrap it in `sudo`: the agent users already run
with UID 0 for rootless Podman workspace writes, and sudo account
validation can fail before the allowlist is applied.

If startup logs show `sudo: account validation failure, is your account
locked?` or `postStartCommand from devcontainer.json failed`, do not
ignore it. The container and VS Code Server may still start, but the
egress allowlist did not apply.

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
bash -n .devcontainer/scripts/configure-agent-runtime.sh
bash -n .devcontainer/scripts/install-agent-cli.sh
bash -n .devcontainer/scripts/prepare-agent-workspace.sh
bash -n .devcontainer/scripts/check-stale-agent-container.sh
bash -n .devcontainer/scripts/ensure-agent-image.sh
sh -n .devcontainer/images/features/agent-user/install.sh
nix build .#claude-cli
nix build .#codex-cli
```
