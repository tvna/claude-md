# Remote Execution Environment — uv Provisioning Runbook

This document is the operator-facing runbook for keeping the remote execution environment's `uv` aligned with what CI uses. It is the companion to [#106](https://github.com/tvna/claude-md/issues/106).

The Claude Code on the Web remote environment ships with a stale `uv` (`0.8.17`) that does not satisfy `pyproject.toml`'s `required-version = ">=0.11.8"`. Sessions need a working `uv` from the first command, without manual reinstall.

## SoT layout

| Location | Target | Purpose |
|---|---|---|
| `.github/workflows/generate-agents.yml` env `UV_VERSION` (line 21) | CI | **Single source of truth for the pinned uv version.** |
| `.github/workflows/verify-apm-drift.yml` env `UV_VERSION` (line 23) | CI | Must equal the value above; kept in lockstep. |
| Claude Code on the Web → Environment → setup script | Remote session | Provisions `uv` at container creation time. Mirrors the CI `UV_VERSION`. |
| `docs/remote-environment.md` *(this file)* | — | Runbook: script body, sync rule, verification, update procedure. |

## Why no `.claude/settings.json` hook

`docs/repo-scope.md` (per [#58](https://github.com/tvna/claude-md/issues/58)) forbids committing anything under `.claude/`. A `SessionStart` hook would have to live there, so the trigger must live outside the repo. The Web UI's environment setup script is the only place that runs before the user's first command without violating the repo-scope rule.

## Why not nix

Considered and rejected for this case:

- `nix` is not pre-installed in the remote environment. Installing it adds 60–90 s to every container creation just to deliver one binary.
- `nixpkgs.uv` trails upstream uv releases by up to several days. Using nix for "always current" uv works against the goal.
- A `flake.nix` for a single binary contradicts CLAUDE.md §4 ("minimum code that solves the problem").

The decision record is in [#106](https://github.com/tvna/claude-md/issues/106).

## Setup script body

Paste this into **Claude Code on the Web → Environment → setup script**. Keep the `UV_VERSION` value in lockstep with `.github/workflows/generate-agents.yml`'s `UV_VERSION`.

```sh
set -euo pipefail
UV_VERSION="0.11.11"

current="$(uv --version 2>/dev/null | awk '{print $2}' || true)"
if [ "${current}" != "${UV_VERSION}" ]; then
  curl -LsSf "https://github.com/astral-sh/uv/releases/download/${UV_VERSION}/uv-x86_64-unknown-linux-gnu.tar.gz" -o /tmp/uv.tar.gz
  tar -xzf /tmp/uv.tar.gz -C /tmp
  mkdir -p "$HOME/.local/bin"
  install -m 0755 /tmp/uv-x86_64-unknown-linux-gnu/uv "$HOME/.local/bin/uv"
fi

case ":$PATH:" in *":$HOME/.local/bin:"*) ;; *) export PATH="$HOME/.local/bin:$PATH" ;; esac

uv --version
uv sync --locked
```

Design notes:

- **Idempotent.** If the installed version already matches `UV_VERSION`, the download and install are skipped — fast on container reuse.
- **Overwrites the stock uv at the same path.** The default remote uv lives at `~/.local/bin/uv`; `install -m 0755` replaces it in-place.
- **No `|| true` on `uv sync --locked`.** A failure must surface at session start, not be hidden — see CLAUDE.md §4 ("when a check is warranted, fail loudly").

## Verification

Run these in a fresh session to confirm the setup script took effect:

```sh
uv --version                                           # must print: uv 0.11.11
command -v uv                                          # must print: $HOME/.local/bin/uv
uv sync --locked                                       # must exit 0
uv run --with "apm-cli==0.12.1" apm compile            # must exit 0
git diff --exit-code -- CLAUDE.md AGENTS.md            # must exit 0 (no drift vs CI)
```

The final two commands match the CI `verify-apm-drift.yml` gate. If they pass locally, the remote session is functionally equivalent to CI.

## Update procedure

When CI's `UV_VERSION` is bumped:

1. Note the new version (e.g. `0.11.12`).
2. Edit **both** CI workflows in the same PR:
   - `.github/workflows/generate-agents.yml` — `env.UV_VERSION`
   - `.github/workflows/verify-apm-drift.yml` — `env.UV_VERSION`
3. Update the **setup script in the Web UI** to the same version. (This step is outside git — done manually in the Claude Code on the Web Environment settings.)
4. Open a new session and run the [Verification](#verification) recipe end-to-end.
5. Record the bump in the retrospective issue for that PR (CLAUDE.md §3).

The setup script does not need to be re-pasted on every CI bump — only the `UV_VERSION="..."` line changes.

## Risks

- **Drift between Web UI and CI.** The Web UI configuration is outside git; there is no automated gate that catches a missed update. Mitigation: the retrospective-issue checklist (step 5 above) plus the verification recipe.
- **Outbound network policy.** The setup script fetches from `github.com/astral-sh/uv/releases`. If the environment's network policy denies that, the script fails at container creation. Confirm policy before first use; see https://code.claude.com/docs/en/claude-code-on-the-web for policy options.

## References

- [#106](https://github.com/tvna/claude-md/issues/106) — parent issue for this runbook.
- [#58](https://github.com/tvna/claude-md/issues/58) — repo-scope policy; rationale for not using `.claude/` hooks.
- `docs/repo-scope.md` — operator runbook governance (this file falls under the "operator runbooks" carve-out).
- `.github/workflows/generate-agents.yml`, `.github/workflows/verify-apm-drift.yml` — canonical `UV_VERSION` source.
- `pyproject.toml` — declares `required-version = ">=0.11.8"`.
- https://code.claude.com/docs/en/claude-code-on-the-web — environment / network policy documentation.
