# Host uv Pin Alignment (macOS rescue)

Operator procedure for keeping a macOS host's `uv` aligned with the
repository pin **without** depending on Homebrew. This is the durable uv
contract for the no-sandbox macOS rescue environment used when the web
environment is unavailable or a devcontainer is broken. Original problem and
decision record: [#1205](https://github.com/tvna/claude-md/issues/1205).
Current formalization: [#1745](https://github.com/tvna/claude-md/issues/1745).

## Entrypoints

The macOS rescue environment has three supported entrypoints:

- **VS Code workspace** -- `claude-md.code-workspace` prepends
  `~/.uv-pins/claude-md` to integrated-terminal `PATH` and runs the
  `bootstrap pinned uv` task on folder open.
- **Claude Desktop** -- `.claude/settings.json` runs
  `scripts/session_uv_local_pin.sh` during `SessionStart`.
- **Codex Desktop** -- `.codex/hooks.json` runs
  `scripts/session_uv_local_pin.sh` during `SessionStart`.

All three entrypoints use the same durable prefix:
`~/.uv-pins/claude-md`. The prefix is version-agnostic by design; when
`[tool.uv].required-version` changes, `scripts/setup_pinned_uv.sh` refreshes
the binaries in place.

## Problem

The repository pins an exact `uv` version at `[tool.uv].required-version` in
`pyproject.toml` (the single source of truth; `flake.nix` reads the same
value). A macOS host that installs `uv` through a package manager such as
Homebrew follows upstream releases and drifts ahead of the pin. When that
happens, `uv run` / `uv sync` inside this repository -- and any Claude Code
plugin Stop hook that shells out to `uv` -- fail with a version-mismatch error
until the developer enters `nix develop` or otherwise leaves the repository.

Package-managed `uv` cannot fix this with `uv self update`: self-update is
disabled when uv was installed by another package manager, so the host binary
can only move when the package manager moves it.

## Approach

Leave the host's package-managed `uv` untouched. Install a second, pinned `uv`
into a durable prefix and make each macOS rescue entrypoint prefer it. Three
pieces are checked into the repository:

- `scripts/setup_pinned_uv.sh` -- reads the pin via `scripts/uv_pin.py read`
  and installs the matching `uv` into a version-agnostic prefix
  (`~/.uv-pins/claude-md` by default; override with `UV_PIN_DIR`). It uses the
  official Astral installer with `UV_UNMANAGED_INSTALL`, so the install does
  not modify shell profiles and does not touch the host binary. The script is
  idempotent and self-heals: if the prefix already holds the pinned version it
  exits early, and if the pin later moves it reinstalls.
- `claude-md.code-workspace` -- prepends the prefix to `PATH` for integrated
  terminals (so `which uv` resolves to the pinned binary inside the
  repository), and registers `setup_pinned_uv.sh` as a `folderOpen` task so
  the install runs when the workspace is opened.
- `.claude/settings.json` and `.codex/hooks.json` -- run
  `scripts/session_uv_local_pin.sh` during `SessionStart`, which calls
  `setup_pinned_uv.sh` when the ambient `uv` is missing or mismatched and then
  persists the prefix into the desktop agent session PATH.

No uv version number is hard-coded in these artifacts: the prefix is
version-agnostic and the version is derived at runtime from `pyproject.toml`.
This keeps the rescue entrypoint files clear of the uv pin drift gate.

## Procedure

### VS Code workspace

1. Open `claude-md.code-workspace` in VS Code (File > Open Workspace from
   File...).
2. Grant Workspace Trust when prompted. Automatic tasks never run in an
   untrusted workspace -- this is a VS Code security control and is expected.
3. Allow the automatic task the first time VS Code asks ("Allow Automatic
   Tasks in Folder"). To skip the prompt on every open, set
   `task.allowAutomaticTasks` to `on` in your user settings (trusted
   workspaces only).
4. The `bootstrap pinned uv` task installs the pinned `uv` on first open. You
   can also run it on demand: Terminal > Run Task... > `bootstrap pinned uv`,
   or run `scripts/setup_pinned_uv.sh` directly.
5. Use Terminal > Run Task... > `apm: compile` for instruction compilation.
   The task runs `uv run --with "apm-cli==0.12.1" apm compile`; in the
   integrated terminal, `uv` resolves through `~/.uv-pins/claude-md`.

### Claude Desktop and Codex Desktop

1. Start or resume the desktop session from this repository.
2. The `SessionStart` hook runs `scripts/session_uv_local_pin.sh`.
3. If the ambient host `uv` is missing or does not match the repo pin, the
   hook runs `scripts/setup_pinned_uv.sh` and persists
   `~/.uv-pins/claude-md` into the session PATH.
4. Continue normal repo commands such as `uv sync --locked` or
   `uv run --with "apm-cli==0.12.1" apm compile`.

The hook fails open if setup cannot complete, so the session still starts.
Run the verification below before relying on the rescue environment.

## Verification

- `python3 scripts/uv_pin.py read pyproject.toml` prints the repository pin.
- `which uv` inside a VS Code integrated terminal or desktop agent session
  resolves under `~/.uv-pins/claude-md`.
- `uv --version` matches `python3 scripts/uv_pin.py read pyproject.toml`.
- VS Code `Tasks: Run Task` lists `bootstrap pinned uv`, `apm: compile`, and
  `uv: sync (locked)`.
- `uv run --with "apm-cli==0.12.1" apm compile` succeeds without reporting a
  `[tool.uv].required-version` mismatch.

## Related

- [remote-environment.md](../standards/remote-environment.md) -- the
  equivalent alignment for the Claude Code on the Web remote environment via
  the SessionStart hook (`scripts/install-uv.sh`).
- `nix develop` remains the highest-fidelity path (bit-for-bit match to the
  Nix-pinned build) and is unaffected by this procedure.
