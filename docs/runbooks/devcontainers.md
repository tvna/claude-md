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

### Per-architecture entrypoint overlays

The base entrypoints above reference a single commit-SHA image tag that is
a multi-platform manifest, so `podman pull` auto-resolves the host CPU
architecture. That is the everyday path and needs no architecture choice.

For cases that need an explicit architecture, generated overlay entrypoints
pin one platform:

| Entrypoint | Pins |
|---|---|
| `.devcontainer/claude-amd64/devcontainer.json` | `--platform=linux/amd64` |
| `.devcontainer/claude-arm64/devcontainer.json` | `--platform=linux/arm64` |
| `.devcontainer/codex-amd64/devcontainer.json` | `--platform=linux/amd64` |
| `.devcontainer/codex-arm64/devcontainer.json` | `--platform=linux/arm64` |

VS Code lists every `.devcontainer/<name>/devcontainer.json` subfolder in
its "Reopen in Container" and "Switch Container" pickers, so these overlays
appear as selectable choices alongside the base entrypoints. Each overlay
adds `--platform=linux/<arch>` to `runArgs` and passes `--platform` to the
host-side image check, so `podman pull` loud-fails when the requested
architecture is absent from the manifest (the amd64-only-publish hazard
described under [Prebuilt images](#prebuilt-images)).

These overlays are **generated, not hand-edited**. The base
`.devcontainer/<agent>/devcontainer.json` image SHA is the single source of
truth; the pin automation regenerates the overlays after each bump, and the
`generate_devcontainer_arch_overlays` preflight gate fails CI on drift. To
regenerate after editing a base config:

```sh
python3 scripts/generate_devcontainer_arch_overlays.py generate
python3 scripts/generate_devcontainer_arch_overlays.py verify
```

Running a non-host architecture goes through qemu emulation, so eBPF egress
correlation, the egress allowlist's netfilter path, and performance differ
from a native container. Treat the cross-architecture overlays as a
diagnostic / verification path, not a daily driver. If a stale-container
recovery is needed for an overlay, pass its config path explicitly:

```sh
.devcontainer/scripts/check-stale-agent-container.sh claude \
  --config .devcontainer/claude-amd64/devcontainer.json
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

### Codex CLI prompt-response triage

Use this procedure when Codex starts in the Codex DevContainer, accepts a
prompt, and then produces no model response or reports
`Falling back from WebSockets to HTTPS transport. request timed out`
followed by `Conversation interrupted`. The pasted terminal symptom often
contains several unrelated-looking failures in one startup: missing
`bubblewrap`, `codex_apps` MCP timeout, `SessionStart` / `UserPromptSubmit`
hook failures, and the final transport timeout. Treat those as separate
boundaries and prove which one blocks the prompt response before changing
repo policy.

Safety boundary: record only command names, exit codes, status lines, and
redacted network headers. Do not paste Codex logs, full HTTP headers, tokens,
cookies, `~/.codex/auth.json`, session database files, shell history, or an
environment dump into issues, PRs, chat, or generated artifacts. `Set-Cookie`
headers are especially out of scope; record only that they were omitted.

1. Runtime prerequisite boundary. Verify the container setup that Codex needs
   before debugging hooks or network transport:

   ```sh
   id -un
   codex --version
   command -v bwrap
   command -v python3
   ```

   If `bwrap` or `python3` is missing, run the runtime refresh above:

   ```sh
   bash .devcontainer/scripts/configure-agent-runtime.sh codex
   ```

   Restart Codex after the refresh. A missing prerequisite can explain
   sandbox warnings and hook `exit code 127`, but it does not prove the
   OpenAI transport path is broken.

2. Hook boundary. If the prompt submission reports `SessionStart hook
   (failed)`, `UserPromptSubmit hook (failed)`, `Broken pipe`, or `exit code
   127`, run the named repo hook command directly from `/workspaces/claude-md`
   with the same user. For the prompt hook, the current repo command is:

   ```sh
   python3 scripts/prompt_context7_gate.py
   ```

   For SessionStart failures, inspect `.codex/hooks.json` and run only the
   failing command shown in the terminal. Record the command and exit code,
   not the full hook payload. Do not disable hooks as the final fix: a
   temporary no-hook comparison is diagnosis only, and any durable fix must
   repair the failing hook command, runtime prerequisite, or generated hook
   configuration.

3. MCP boundary. If Codex reports `MCP client for codex_apps timed out` or
   `MCP startup incomplete`, classify it separately from prompt transport.
   A missing app connector can break connector tools, but it is not by itself
   evidence that the model request cannot reach OpenAI. Record whether the
   timeout appears before the user prompt, after the user prompt, or only
   while invoking a connector tool.

4. Transport boundary. If the prompt still reaches
   `Falling back from WebSockets to HTTPS transport. request timed out`, run
   only these network boundary checks from inside the Codex DevContainer:

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

5. Egress allowlist boundary. If the transport checks fail, compare with the
   egress allowlist disabled for one container start:

```sh
DEVCONTAINER_APPLY_EGRESS_ALLOWLIST=0
```

Then reopen the Codex DevContainer and retry the same `getent` and
`curl -I` commands. If disabling the allowlist changes the result, the
next fix belongs in `.devcontainer/network/shared.allowlist` or the
allowlist apply script. If the checks pass with and without the
allowlist, keep the issue scoped to Codex CLI transport behavior or the
upstream service path rather than changing repository network policy.

Decision matrix:

| Observation | Next owner |
|---|---|
| `command -v bwrap` or `command -v python3` fails | DevContainer runtime setup |
| A named repo hook fails when run directly | Hook script or generated hook config |
| Only `codex_apps` startup fails, and the model prompt still responds | MCP app startup |
| `getent` fails only with the allowlist enabled | Egress allowlist / DNS proxy |
| `curl -I` fails only with the allowlist enabled | Egress allowlist host or IP resolution |
| `getent` and `curl -I` pass with and without the allowlist, but Codex still times out | Codex CLI transport or upstream service path |

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
entrypoints listed above. The prebuild bakes the base image plus the
`common-utils`, `nix`, and `agent-user` Features, and -- for `claude` only --
the `nix-warm-claude` Feature. `devcontainer build` does not run
`postCreateCommand`, so the agent CLI symlink and the `uv sync` venv are NOT
baked into the GHCR image -- `install-agent-cli.sh` and `uv sync` run at
container start as `postCreateCommand` steps.

The `.#claude` devShell closure IS baked, by the `nix-warm-claude` Feature
(`.devcontainer/images/features/nix-warm-claude/`, Refs #1491). Lifecycle
hooks cannot pre-warm it because `devcontainer build` skips them, so the
Feature -- which runs as root during the build -- copies the flake into a
non-git `/opt` dir and runs `nix develop "path:...#claude" --command true`,
leaving the realised closure in `/nix/store`. The split measurement (#1471)
showed this first-time closure realisation was ~23.4s of container-create,
dwarfing the ~2.8s `uv sync`; baking it trades image size (~+250-400 MB
compressed) for that startup time, a net win because the image is cached and
reused locally across sessions. The `path:` ref forces Nix's non-git
evaluator, sidestepping the libgit2 dubious-ownership error the runtime
git+file fetch hits. The publish workflow stages `flake.nix`, `flake.lock`,
and `pyproject.toml` into the Feature dir for the claude legs only (the
workspace is not mounted during Feature install); those copies are
git-ignored so they cannot drift from the source flake. Codex is out of
scope and does not bake its closure. The retained `postCreateCommand`
`nix develop .#claude --command true` is a ~0s no-op against the warm store
and a fallback if the bake ever fails. The startup probe (Refs #1322, #1332)
measures the now-baked warmup segment as near-zero with
`split_nix_develop=true`.

The prebuild base is `ubuntu:24.04` plus the `common-utils` feature (with
zsh / oh-my-zsh disabled) for `git`, `sudo`, and CA certificates, then the
`nix` and `agent-user` features. This replaced
`mcr.microsoft.com/devcontainers/base:ubuntu-24.04`, whose base distro
(`/usr` ~644 MiB) dominated the ~1.034 GiB image and the cold-start pull;
the composition probe (Refs #1332) showed the agent toolchain is supplied by
Nix at runtime, so the heavier base added pull cost without a runtime
benefit. The agent quality-gate tools (ruff, mypy, pytest, shellcheck,
actionlint) continue to come from the Nix devShell, not the base.

## Prebuilt images

Local devcontainers use immutable commit-SHA image tags. The currently
pinned images were published from `7693374fb3f707d0bc0547a53c60b69abc829e91`:

| Agent | Image |
|---|---|
| Claude | `ghcr.io/tvna/claude-md-devcontainer-claude:7693374fb3f707d0bc0547a53c60b69abc829e91` |
| Codex | `ghcr.io/tvna/claude-md-devcontainer-codex:7693374fb3f707d0bc0547a53c60b69abc829e91` |

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
created by a dedicated **GitHub App** rather than the default
`GITHUB_TOKEN`, because `GITHUB_TOKEN`-authored PRs and pushes do not
trigger the downstream `pull_request` checks the auto-merge keeper waits
on (GitHub recursion prevention). The workflows mint a short-lived App
installation token at runtime with `actions/create-github-app-token`, so
the generated PR's author is the App bot (`<app-slug>[bot]`) -- a natural,
recognizable bot identity -- while still triggering downstream workflows.
The pin commit is authored under the same App bot identity, resolved from
the App slug and the bot's numeric user id. Refs #1401.

Create the App with access limited to `tvna/claude-md`. The minimum
repository permissions are Metadata read, Contents read and write, and
Pull requests read and write. Store the App's credentials only in the
`devcontainer-image-pins` Environment, not as repository-wide secrets:
`DEVCONTAINER_PIN_APP_ID` (the App ID) and `DEVCONTAINER_PIN_APP_PRIVATE_KEY`
(a generated private key). Installation tokens expire in <= 1 hour, so they
are never stored -- only the private key is, and it must be rotated on a fixed
cadence (regenerate the key, update the Environment secret, then delete the old
key). Verify the handoff by triggering `Publish devcontainer images` with
`workflow_dispatch` and confirming the `Update local devcontainer image pins`
job opens or reuses the generated image-pin PR -- authored by the App bot --
without exposing the key value in logs. Record the next rotation date with the
Environment secret owner. If the private key is suspected leaked rather than
rotated on schedule, follow the emergency revoke-then-reissue steps in
[`compromised-action-response.md`](compromised-action-response.md).

The `Update local devcontainer image pins` job creates (or reuses) the
generated PR but does **not** request GitHub native auto-merge. The
repository-level "Allow auto-merge" toggle is intentionally OFF so that
agents cannot enable native auto-merge on arbitrary PRs, and native
auto-merge is repo-wide -- it cannot be scoped to a single PR. Completing
the pin PR is therefore delegated to the dedicated keeper below.

### Merging the pin PR when green (`Auto-merge tvna-bot PRs`)

Because repo-wide auto-merge is off by design, the unified
`Auto-merge tvna-bot PRs` workflow (`tvna-bot-automerge.yml`) merges the
generated pin PR on its behalf. This single keeper (consolidated from the
former pin-only `devcontainer-pin-automerge.yml` in #1539) merges *every* open
PR authored by the App bot (`tvna-bot[bot]`), not just the pin branch prefix.
It runs `python3 scripts/bot_pr_automerge.py merge`: it lists the open
`tvna-bot[bot]` PRs and, for each one GitHub reports `mergeable_state == clean`
(all required checks green and the branch up to date), squash-merges it via the
REST merge API and deletes the branch. A PR that is not yet `clean`, or that
loses the head-SHA race, is left untouched for the next trigger. Squash is fixed
so the keyless signing invariant on `main` (see
[`commit-signing.md`](../standards/commit-signing.md)) is preserved.

The keeper originally triggered on `check_suite: completed`, but that event
never fired: GitHub suppresses `check_suite` events for suites created by
GitHub Actions (recursion prevention), and every bot-PR check is
Actions-created, so the keeper never ran and clean PRs stalled (#1363). It
is now driven by `workflow_run` on the two workflows that own the required
status checks (`Verify PR`, `Verify repository scripts`) completing -- gated by
an `if` on `conclusion == 'success'` (the merge subcommand itself filters to
`tvna-bot[bot]` authors and clean PRs, so it is no longer branch-prefix-gated)
-- with a `schedule` cron (every 15 min) as a safety net so a missed event
still converges, and `workflow_dispatch` for manual recovery. Because
`workflow_run` and `schedule` only run from the default branch, the trigger
takes effect once merged to `main`.

Branch protection (`main-protection`) still gates the merge; the keeper never
bypasses required checks or rulesets. The merge uses the GitHub App installation
token (not `GITHUB_TOKEN`) so the resulting push to `main` still triggers the
downstream push workflows (publish / refresh / post-merge). To merge a stuck
bot PR on demand, dispatch this workflow manually. Refs #1539, #1352, #1363, #1401.

### Keeping the pin PR mergeable (`Refresh devcontainer pin PR`)

The pin PR stalls the moment `main` advances past it.
`main-protection` sets `strict_required_status_checks_policy: true`, so the
branch must be up to date before it can merge, while `required_linear_history`,
the `scripts/gate_update_pr_branch.py` hook, and the `non_fast_forward` rule on
non-default branches all forbid rebasing or force-pushing the branch in place.
The branch therefore becomes `behind` and never merges on its own.

The `Refresh devcontainer pin PR` workflow (`devcontainer-pin-refresh.yml`)
closes that gap. On every push to `main` (and on `workflow_dispatch`) it runs
`python3 scripts/devcontainer_pin_pr.py refresh`: if an open pin PR is behind
`main`, it cuts a fresh branch off the latest `main`
(`devcontainer/image-pins-<published-sha>-r-<main-short-sha>`), re-applies
the same pins as a single commit, opens a replacement PR, then comments on,
closes, and deletes the stale PR/branch. The replacement is opened before the
old PR is closed, so a failure never leaves the repository without an open pin
PR. When the open pin PR is already up to date, `refresh` instead attempts a
direct merge (the same path the auto-merge keeper uses), so a green, up-to-date
PR still completes even between the keeper's `workflow_run` events. It reuses the
`devcontainer-image-pins` Environment and the same GitHub App secrets; no new
secret is required. To merge a stuck pin PR on demand, dispatch this workflow
manually. Refs #1137.

### Auto-following flake tool pins (`Refresh flake tool pins`)

`flake.nix` is the single source of truth for the version and per-system
SHA256 of the GitHub-Releases-sourced tools (`waza`, `apm`). Dependabot has no
Nix ecosystem, so those pins do not follow upstream on their own. The
`Refresh flake tool pins` workflow (`weekly-maintenance.yml`) closes that gap.
Weekly (and on `workflow_dispatch`) it runs `scripts/flake_pin_latest.py` to
find the latest release per tool, holds anything still inside the
`[tool.uv].exclude-newer` cooldown, recomputes each per-system SHA256 with
`nix store prefetch-file`, bumps `flake.nix` with `scripts/flake_pin.py`,
validates it with `nix flake check`, and opens a bump PR by reusing
`scripts/devcontainer_pin_pr.py open`. It reuses the `devcontainer-image-pins`
Environment and the same GitHub App secrets; no new secret is required. The
generated PR's `verify-flake` check is the final authenticity gate for the
recomputed hash, and `scan_flake_pin_drift` continues to guard duplicate
copies. Refs #1171.

### One-time setup for `DEVCONTAINER_PIN_APP_ID`

1. Create (or reuse) a GitHub App owned by `tvna` with the minimum
   repository permissions above, installed only on `tvna/claude-md`.
2. Open `tvna/claude-md` -> **Settings** -> **Environments** ->
   `devcontainer-image-pins`.
3. Add the App's numeric App ID as the `DEVCONTAINER_PIN_APP_ID`
   Environment secret.
4. Generate a private key for the App and add it as the
   `DEVCONTAINER_PIN_APP_PRIVATE_KEY` Environment secret (next section).
5. Confirm the repository rulesets allow the generated branches
   (`devcontainer/image-pins-<sha>`, `flake-pin-<...>`) to be pushed -- the
   branch push still uses the persisted-checkout `github-actions[bot]`
   identity -- and allow the App bot to merge the pin PR through required
   checks.
6. Trigger `Publish devcontainer images` with `workflow_dispatch`, or
   wait for the next `main` publish, and confirm the
   `Update local devcontainer image pins` job opens or reuses the
   generated image-pin PR.
7. Confirm the generated PR and its commit show the App bot
   (`<app-slug>[bot]`) as the author. The PR is completed by the
   `Auto-merge devcontainer pin PR` keeper once its checks go green
   (repo-wide native auto-merge stays OFF by design).

### One-time setup for `DEVCONTAINER_PIN_APP_PRIVATE_KEY`

This Environment secret is created together with `DEVCONTAINER_PIN_APP_ID`
in the steps above: generate a private key from the GitHub App and store the
downloaded PEM as the `DEVCONTAINER_PIN_APP_PRIVATE_KEY` Environment secret in
`devcontainer-image-pins` (never a repository-wide secret). The same minimum
permissions, rotation cadence, and verification step apply -- rotate the key by
generating a new one, updating the secret, and confirming the next pin run still
opens the App-bot PR before deleting the old key.

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

## Monthly GHCR image cleanup

Every `Publish devcontainer images` run pushes a new commit-SHA image version
per agent package (plus per-arch `*-amd64` / `*-arm64` tags), so the
`claude-md-devcontainer-claude` and `claude-md-devcontainer-codex` GHCR
packages grow without bound. The `prune-devcontainer-images` job in
`monthly-maintenance.yml` deletes old versions on a monthly cadence
(`scripts/prune_devcontainer_images.py`, [#1400](https://github.com/tvna/claude-md/issues/1400)).

Retention policy (count + age). For each package a version is **protected** --
never deleted -- when any of its tags is:

- `main` (the moving convenience alias),
- a `buildcache-*` BuildKit cache tag, or
- the currently pinned SHA (read from `.devcontainer/<agent>/devcontainer.json`)
  or its `-amd64` / `-arm64` variant.

Among the remaining tagged versions the newest 10 are kept unconditionally; of
the rest, only versions older than 90 days are deleted. Untagged versions are
skipped, because they may be the child manifests of a retained multi-platform
manifest list. The schedule run deletes for real; a `workflow_dispatch` run
previews (dry-run) unless `prune_dry_run` is set to `false`.

### One-time setup for `GHCR_CLEANUP_TOKEN`

Deleting a user-owned container package version is **not** possible with the
Actions `GITHUB_TOKEN`: there is no `packages: delete` Actions permission, and
the token is an app installation token rather than a user token, so the delete
endpoint returns `403`. The job therefore authenticates with a dedicated
personal access token.

1. Create a **classic** PAT at `github.com/settings/tokens` with the minimum
   permissions `read:packages` and `delete:packages` (admin on the
   `claude-md-devcontainer-*` containers, which the repository owner already
   holds). Do not grant `repo`, `write:packages`, or any broader scope.
2. Store it as the `GHCR_CLEANUP_TOKEN` Environment secret in a dedicated
   `devcontainer-image-cleanup` GitHub Environment (Settings -> Environments).
   Keep it out of repository-wide secrets so the delete-capable token stays
   isolated from the `devcontainer-image-pins` Environment.
3. Set an expiry of 90 days or less. Record the next rotation date with the
   Environment secret owner and rotate the token before expiry.
4. Verify the handoff: dispatch `Monthly maintenance` with
   `workflow_dispatch` leaving `prune_dry_run` at its default `true`, and
   confirm the `prune-devcontainer-images` job lists prune candidates without
   error and without deleting anything. The `Guard GHCR_CLEANUP_TOKEN` step
   fails loud if the secret is unset, so nothing is deleted until the handoff
   is complete. Never print the token value in logs.

If this token is suspected leaked rather than rotated on schedule, follow the
emergency revoke-then-reissue steps in
[`compromised-action-response.md`](compromised-action-response.md).

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

## Debug log capture (macOS)

The connectivity and stale-container triage above tells you *what* failed.
This section is the companion for *capturing the logs* that explain why,
focused on the macOS + rootless-Podman path where several log sources behave
differently from a native Linux container (Issue #1460).

### VS Code Dev Containers log (the primary startup log)

When "Reopen in Container" fails before or during `postCreateCommand`, the
authoritative log is the Dev Containers extension's own output, not the
terminal. Capture it before rebuilding (a rebuild rolls the log window):

1. Command Palette -> **Dev Containers: Show Container Log** for the active
   attempt, or **Developer: Show Logs... -> Window** and switch the Output
   panel to the **Dev Containers** channel.
2. The same content is persisted on disk under the per-window logs tree:

   ```sh
   ls -dt "$HOME/Library/Application Support/Code/logs"/*/window*/exthost/ms-vscode-remote.remote-containers
   ```

   (On a Linux host the base path is `~/.config/Code/logs`.) Copy the newest
   matching directory; it holds the create/start command output.

### Podman machine (VM) logs when the VS Code log is truncated

A `postCreateCommand` / `postStartCommand` failure is often truncated in the
VS Code log. On macOS the container runs inside the podman-machine VM, so the
fuller record lives there. Capture it from the host:

```sh
/opt/podman/bin/podman machine list
/opt/podman/bin/podman machine inspect
/opt/podman/bin/podman machine ssh -- journalctl -n 500 --no-pager
```

Do not paste tokens or `~/.config/gh` contents into issues; record only the
failing units and messages (mirrors the redaction discipline above).

### eBPF correlation log is usually unavailable on macOS Podman

The eBPF correlation monitor's `/tmp/egress-correlation.log` is **best-effort
and typically absent on macOS**. Its `check` seam requires a readable
`/sys/kernel/btf/vmlinux`, a mounted tracefs, and `CAP_BPF`/`CAP_PERFMON`,
all host-dependent inside the podman-machine VM, so `start` skips gracefully
there. Confirm before relying on it:

```sh
.devcontainer/scripts/_egress-ebpf.sh check   # expect: skip on most macOS hosts
```

If it reports `skip`, use the egress *audit* log instead of the eBPF log.

### dmesg_restrict caveat for the egress audit log

`dmesg | grep EGRESS-AUDIT` (see the Egress allowlist section) can return
nothing under rootless Podman even when audit mode is active: the host may set
`kernel.dmesg_restrict=1`, and the VM kernel ring buffer is shared across
containers. If the grep is empty, check the restriction and read the buffer
with privilege rather than assuming audit produced no output:

```sh
sysctl kernel.dmesg_restrict        # 1 means non-root dmesg is blocked
sudo dmesg | grep EGRESS-AUDIT
```

### One-shot collector

`.devcontainer/scripts/collect-devcontainer-debug.sh` gathers the host-side
sources above (podman machine/info/connection/ps, best-effort VM `journalctl`,
and the newest VS Code remote-containers log dir) into a single local bundle:

```sh
.devcontainer/scripts/collect-devcontainer-debug.sh plan     # list sources, write nothing
.devcontainer/scripts/collect-devcontainer-debug.sh collect  # write the bundle
```

The bundle is **local-only** and **best-effort redacted** (common token
formats are masked). Redaction is not a guarantee -- review every file before
sharing. The collector deliberately never reads `~/.config/gh`, the agent
session volumes, or a full environment dump, because those are token-bearing.
The end-to-end `collect` path needs a real macOS host with a running
podman-machine VM and cannot be exercised in CI; CI verifies only the pure
`plan` and `redact` seams plus `bash -n` (`tests/test_collect_devcontainer_debug.py`).

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
.devcontainer/scripts/apply-egress-allowlist.sh .devcontainer/network/shared.allowlist
```

Every container now applies the single
`.devcontainer/network/shared.allowlist`; the former per-agent
`claude.allowlist` / `codex.allowlist` files were consolidated into it
(#1420), so Claude and Codex share one deny-by-default list. The `@include`
directive still works (the CI egress self-test builds an
`egress-selftest.allowlist` with `@include shared.allowlist`), but the agent
entrypoints no longer need it. For Codex, `shared.allowlist` keeps both
`api.openai.com` and `auth.openai.com`: the former covers API calls, and the
latter covers ChatGPT-mediated OAuth token exchange during `codex login`.

The enforcement script resolves hostnames at container start and allows
TCP ports `22`, `80`, and `443` to those IPs, plus DNS to the container
resolver. It requires `NET_ADMIN`; the devcontainer entrypoints request
that capability through `runArgs`. The script runs directly inside the
Nix network shell. Do not wrap it in `sudo`: the agent users already run
with UID 0 for rootless Podman workspace writes, and sudo account
validation can fail before the allowlist is applied.

`apply-egress-allowlist.sh` is a thin dispatcher; the reusable parsing and
rule-building helpers live in `.devcontainer/scripts/_egress-lib.sh`, which
is also sourced by the CI parser-parity gate. Sourcing the library has no
side effects (no privilege check, no firewall mutation) -- the dispatcher
decides when to apply rules.

### block vs audit mode

The dispatcher reads `EGRESS_MODE` (default `block`):

- `block` -- deny-by-default. Only allowlisted egress is permitted; everything
  else is dropped by the `OUTPUT DROP` policy. This is the production posture.
- `audit` -- discovery mode. The same ACCEPT rules are installed, but instead
  of dropping non-allowlisted egress the dispatcher logs it (rate-limited,
  destination IP:port header only -- no payload) and leaves the policy at
  `ACCEPT`, so connectivity is unbroken. Use it to learn what a new workload
  actually contacts before promoting the file to `block`:

```sh
EGRESS_MODE=audit \
  .devcontainer/scripts/apply-egress-allowlist.sh .devcontainer/network/shared.allowlist
# run the workload, then inspect the kernel log for the audited destinations
dmesg | grep EGRESS-AUDIT
```

Add the discovered, triaged destinations to the allowlist (with rationale)
and switch back to `block`.

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

Before adding a new outbound destination for a new tool, follow the
observe / evaluate / decide / verify procedure in
[`devcontainer-tool-network-triage.md`](devcontainer-tool-network-triage.md).
Each host entry must carry an inline triage rationale comment; the
`scripts/scan_allowlist_rationale.py` gate fails CI when one is missing.

The allowlist is parsed by two implementations -- the bash `read_allowlist`
in `_egress-lib.sh` (container start path) and `scripts/_allowlist.py`
`resolve_hosts` (CI, tests, rationale gate). The
`scripts/scan_allowlist_parser_parity.py` gate fails CI if the two resolve
different host sets, so the single source of truth stays single across both
languages.

### DNS proxy (dnsmasq + ipset, default off)

`.devcontainer/scripts/_egress-dnsproxy.sh` adds a DNS layer to the same
allowlist. It points `/etc/resolv.conf` at a local `dnsmasq` that forwards
**only** allowlisted domains upstream and adds each resolved IP to the
`allowed-egress` ipset, so a companion firewall rule can permit egress to
exactly the IPs the allowlist actually resolves to (rather than a static
snapshot). Host enumeration reuses `read_allowlist` from `_egress-lib.sh`, so
the proxy stays under the same single source and parser-parity gate.

It is **off by default**: `start` and `stop` are no-ops unless
`EGRESS_DNS_PROXY=1`. Generation is separated from kernel application so the
config can be unit-tested without privileges:

```sh
# Pure, unprivileged config generation (no root, writes nothing):
.devcontainer/scripts/_egress-dnsproxy.sh generate-config \
  .devcontainer/network/shared.allowlist --upstream 1.1.1.1
```

The config emits, per allowlisted host, one `server=/<host>/<upstream>`
(split-horizon forward) and one `ipset=/<host>/allowed-egress`. A leading
`no-resolv` plus an explicit default `server=` keep dnsmasq from re-reading the
rewritten `/etc/resolv.conf` (now `127.0.0.1`, i.e. itself) and looping.

`start` backs up the original `/etc/resolv.conf` to
`/etc/resolv.conf.egress-backup` **once per cycle** -- if the backup already
exists it is the genuine original and is never clobbered by the rewritten file
-- and derives the upstream nameservers from that backup, not the live file.
`stop` restores from the backup and removes it, so a later `start` re-captures a
real original. Both are idempotent.

End-to-end behaviour (DNS resolution, ipset population, resolv.conf rewrite)
requires `NET_ADMIN` and cannot be exercised in CI/sandbox. Manual steps in a
NET_ADMIN devcontainer:

```sh
EGRESS_DNS_PROXY=1 .devcontainer/scripts/_egress-dnsproxy.sh start \
  .devcontainer/network/shared.allowlist
ipset list allowed-egress            # empty until first resolution
getent hosts api.github.com          # resolves via the local dnsmasq (127.0.0.1)
ipset list allowed-egress            # now contains api.github.com IPs
cat /etc/resolv.conf                  # nameserver 127.0.0.1
cat /etc/resolv.conf.egress-backup    # original upstream preserved
# re-run start to prove the backup is not clobbered:
EGRESS_DNS_PROXY=1 .devcontainer/scripts/_egress-dnsproxy.sh start \
  .devcontainer/network/shared.allowlist
cat /etc/resolv.conf.egress-backup    # STILL the original upstream
EGRESS_DNS_PROXY=1 .devcontainer/scripts/_egress-dnsproxy.sh stop
cat /etc/resolv.conf                   # restored to the original
```

### eBPF correlation monitor (bpftrace, best-effort, default off)

`.devcontainer/scripts/_egress-ebpf.sh` runs the bpftrace program
`.devcontainer/scripts/egress-correlation.bt`, which correlates each outbound
TCP connect and each file open with the originating process (`pid` + `comm`).
It records **only** the destination `IP:port` (for connect) or the file path
(for openat) -- it **never reads syscall payload buffers**, so secrets in
transit or on disk are not captured. The report is a **local-only** sink
(`/tmp/egress-correlation.log` by default); nothing is sent off-box, matching
the self-hosted, no-telemetry design of the allowlist and DNS proxy.

It is **off by default**: `start` and `stop` are no-ops unless `EGRESS_EBPF=1`.
The devcontainers add `--cap-add=BPF` and `--cap-add=PERFMON` (and deliberately
**not** `CAP_SYS_ADMIN`) so bpftrace can attach without broad privilege.

eBPF is unavailable on many hosts (Docker Desktop, most hosted CI runners). The
`check` subcommand is a pure, unprivileged probe of the four preconditions, and
`start` **skips gracefully** (exit 0, no boot failure) when any are missing:

```sh
# Pure detection seam (no root, no privileged calls, writes nothing):
.devcontainer/scripts/_egress-ebpf.sh check
# prints `supported` (exit 0) or `skip` with reasons on stderr (exit 3):
#   - bpftrace present
#   - kernel BTF readable (/sys/kernel/btf/vmlinux)
#   - tracefs mounted (/sys/kernel/debug/tracing)
#   - CAP_BPF + CAP_PERFMON held (or root)
```

End-to-end behaviour (probe attach, event capture) requires `CAP_BPF`/BTF and
cannot be exercised in CI/sandbox. Manual steps in a capable NET_ADMIN/CAP_BPF
devcontainer:

```sh
.devcontainer/scripts/_egress-ebpf.sh check          # expect: supported
EGRESS_EBPF=1 .devcontainer/scripts/_egress-ebpf.sh start
curl -s https://api.github.com >/dev/null            # generate a connect
cat /tmp/egress-correlation.log                       # CONNECT/OPEN lines, pid+comm, dest/path only
EGRESS_EBPF=1 .devcontainer/scripts/_egress-ebpf.sh stop
```

### CI self-test (GitHub Actions, block mode)

The same allowlist guards the CI surface through the custom composite action
`.github/actions/egress-firewall`. It is **permission-agnostic** (reads no
`GITHUB_TOKEN`, no secrets, like `setup-uv`) and applies the allowlist by
calling the very same `apply-egress-allowlist.sh` dispatcher -- which sources
`_egress-lib.sh` -- so CI and the container start path share one parser
(parity-gated). `.github/workflows/verify-agents.yml` runs it in an isolated
`egress-firewall-selftest` job.

PR4 first ran the job in **audit** mode (log-only, `OUTPUT` policy `ACCEPT`).
Its only post-apply egress was to allowlisted `github.com`, so audit recorded
no required-but-missing destination and confirmed the allowlist is sufficient
for the job's scope. PR5 promotes the job to **block** mode (deny-by-default)
and proves both directions:

- it pre-resolves `github.com` and `example.com` to IPv4 **before** the
  firewall applies, then drives `curl --resolve -4` against the pinned IPs, so
  the assertion tests the iptables allowlist layer in isolation and does not
  depend on the runner's resolver egress (which block mode also constrains);
- it asserts the `OUTPUT` policy is `DROP`, that allowlisted `github.com` still
  reaches `:443`, and that non-allowlisted `example.com` is dropped;
- an always-run teardown restores `OUTPUT` to `ACCEPT` and flushes the chain,
  because block sets `DROP` for **every** process on the runner -- including the
  Actions runner agent -- so the self-test must not strand the agent's own
  completion/telemetry egress or later steps.

The job is deliberately not part of the required `gate` aggregation, so a
runner-specific network quirk in this isolated self-test never blocks unrelated
work.

### Honest limitation: detection plus best-effort blocking, not a sandbox

The egress allowlist, audit logging, DNS proxy, and the eBPF correlation
monitor are **detection plus best-effort blocking, not an enforcement
boundary**. The agent holds `NET_ADMIN`/`CAP_BPF` inside the devcontainer, so
it can revert the controls from within: `iptables -P OUTPUT ACCEPT`, restore
`/etc/resolv.conf`, kill `dnsmasq` or `bpftrace`, detach the eBPF probes, or
flush the `allowed-egress` ipset. CVE-2025-32955 demonstrated the same class of
in-container bypass against step-security/harden-runner. A true enforcement
boundary must live where the agent cannot modify it (a host-side egress proxy
or a separate network namespace); this work complements that, it does not
replace it. On hosted CI runners, eBPF/BTF and some netfilter features are
often unavailable, so blocking and correlation degrade to audit/skip by design.

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
bash -n .devcontainer/scripts/_egress-lib.sh
bash -n .devcontainer/scripts/_egress-dnsproxy.sh
bash -n .devcontainer/scripts/_egress-ebpf.sh
bash -n .devcontainer/scripts/configure-agent-runtime.sh
bash -n .devcontainer/scripts/install-agent-cli.sh
bash -n .devcontainer/scripts/prepare-agent-workspace.sh
bash -n .devcontainer/scripts/check-stale-agent-container.sh
bash -n .devcontainer/scripts/ensure-agent-image.sh
bash -n .devcontainer/scripts/collect-devcontainer-debug.sh
sh -n .devcontainer/images/features/agent-user/install.sh
sh -n .devcontainer/images/features/nix-warm-claude/install.sh
nix build .#claude-cli
nix build .#codex-cli
```
