# Host uv Pin Alignment (brew-independent)

Operator procedure for keeping a developer host's `uv` aligned with the
repository pin **without** depending on Homebrew. Original problem and
decision record: [#1205](https://github.com/tvna/claude-md/issues/1205).

## Problem

The repository pins an exact `uv` version at `[tool.uv].required-version` in
`pyproject.toml` (the single source of truth; `flake.nix` reads the same
value). A host that installs `uv` through a package manager such as Homebrew
follows upstream releases and drifts ahead of the pin. When that happens,
`uv run` / `uv sync` inside this repository -- and any Claude Code plugin Stop
hook that shells out to `uv` -- fail with a version-mismatch error until the
developer enters `nix develop` or otherwise leaves the repository.

Package-managed `uv` cannot fix this with `uv self update`: self-update is
disabled when uv was installed by another package manager, so the host binary
can only move when the package manager moves it.

## Approach

Leave the host's package-managed `uv` untouched. Install a second, pinned `uv`
into a workspace-local prefix and make the repository's VS Code workspace
prefer it. Two pieces, both checked into the repository:

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

No version number is hard-coded in either artifact: the prefix is
version-agnostic and the version is derived at runtime from `pyproject.toml`.
This keeps both files clear of the uv pin drift gate.

## Procedure

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

## Verification

- `which uv` in a workspace integrated terminal resolves under
  `~/.uv-pins/claude-md`.
- `uv --version` matches the pin in `pyproject.toml`
  (`python3 scripts/uv_pin.py read pyproject.toml`).
- `uv run` / `uv sync` inside the repository, and any uv-shelling Stop hook,
  no longer report a version mismatch.

## Related

- [remote-environment.md](../standards/remote-environment.md) -- the
  equivalent alignment for the Claude Code on the Web remote environment via
  the SessionStart hook (`scripts/install-uv.sh`).
- `nix develop` remains the highest-fidelity path (bit-for-bit match to the
  Nix-pinned build) and is unaffected by this procedure.
