# Remote Execution Environment — uv Provisioning Runbook

This document is the operator-facing runbook for keeping the remote execution environment's `uv` aligned with what CI uses. Original problem and decision record: [#106](https://github.com/tvna/claude-md/issues/106). The `.claude/settings.json` governance carve-out that enables the in-repo hook below: [#109](https://github.com/tvna/claude-md/issues/109).

The Claude Code on the Web remote environment ships with a stale `uv` (`0.8.17`) that does not satisfy `pyproject.toml`'s `required-version = ">=0.11.8"`. Sessions need a working `uv` from the first command, without manual reinstall.

## SoT layout

| Location | Target | Purpose |
|---|---|---|
| `.github/workflows/generate-agents.yml` env `UV_VERSION` (line 21) | CI | **Single source of truth for the pinned uv version.** |
| `.github/workflows/verify-apm-drift.yml` env `UV_VERSION` (line 23) | CI | Must equal the value above; kept in lockstep. |
| `scripts/install-uv.sh` | Remote session | Pins `uv` to `UV_VERSION` at SessionStart. Mirrors the CI install pattern. |
| `.claude/settings.json` | Remote session | Registers `scripts/install-uv.sh` as the `SessionStart` hook. Permitted under the [#109](https://github.com/tvna/claude-md/issues/109) carve-out in `docs/repo-scope.md`. |
| `docs/remote-environment.md` *(this file)* | — | Runbook: how the hook works, how to keep `UV_VERSION` in sync with CI, verification, update procedure. |

## How it works

1. Every new Claude Code on the Web session triggers the `SessionStart` hook registered in `.claude/settings.json`.
2. The hook invokes `scripts/install-uv.sh`, which is a no-op when `CLAUDE_CODE_REMOTE` is not set (so local dev sessions are unaffected).
3. In the remote environment, the script compares the installed `uv` against the pinned `UV_VERSION`. If it differs (default container ships `0.8.17`), it downloads and installs the pinned version to `$HOME/.local/bin/uv`, overwriting the stock binary at the same path.
4. It exports `$HOME/.local/bin` on `$PATH` for the rest of the session (via `$CLAUDE_ENV_FILE` when present).
5. Finally, `uv sync --locked` warms the project venv against the locked dependencies.

The script is idempotent: when a container is reused and `uv` is already at the pinned version, the install is skipped and only `uv sync --locked` runs.

## Why not the Web UI setup script

An earlier draft of this runbook ([#107](https://github.com/tvna/claude-md/pull/107)) proposed registering the same shell in the Claude Code on the Web Environment setup-script field instead of an in-repo hook. That approach was rejected once [#109](https://github.com/tvna/claude-md/issues/109) carved out `.claude/settings.json`:

- The Web UI configuration is not under git history — it cannot be code-reviewed, diffed, or reproduced when the environment is recreated.
- Drift between the Web UI value and the CI `UV_VERSION` is invisible to the repo.
- The same shell-execution risk that motivated the broad `.claude/` ban applies *more* to the Web UI script, because it sits entirely outside change control.

The carve-out for `.claude/settings.json` pulls the hook surface back under PR review. See `docs/repo-scope.md` § "Security tradeoff for `.claude/settings.json`" for the recorded risk-acceptance.

## Why not nix

- Nix is not pre-installed in the remote environment; installing it adds 60–90 s to every container creation just to deliver one binary.
- `nixpkgs.uv` trails upstream uv releases by up to several days, working against the "always current" goal.
- A `flake.nix` for a single binary conflicts with CLAUDE.md §4 ("minimum code that solves the problem").

Decision recorded in [#106](https://github.com/tvna/claude-md/issues/106).

## Verification

In a fresh remote session:

```sh
uv --version                                           # must print: uv 0.11.11
command -v uv                                          # must print: $HOME/.local/bin/uv
uv sync --locked                                       # must exit 0
uv run --with "apm-cli==0.12.1" apm compile            # must exit 0
git diff --exit-code -- CLAUDE.md AGENTS.md            # must exit 0 (no drift vs CI)
```

The final two commands match the CI `verify-apm-drift.yml` gate. If they pass locally, the remote session is functionally equivalent to CI.

Direct script test (any environment, no session needed):

```sh
CLAUDE_CODE_REMOTE=true scripts/install-uv.sh         # full install + uv sync
env -u CLAUDE_CODE_REMOTE scripts/install-uv.sh        # no-op, exits 0 silently
```

## Update procedure

When CI's `UV_VERSION` is bumped:

1. Note the new version (e.g. `0.11.12`).
2. In the **same PR**, edit:
   - `.github/workflows/generate-agents.yml` — `env.UV_VERSION`
   - `.github/workflows/verify-apm-drift.yml` — `env.UV_VERSION`
   - `scripts/install-uv.sh` — the `UV_VERSION="..."` line
3. Open a new session against the PR branch and run the [Verification](#verification) recipe end-to-end.
4. Record the bump in the retrospective issue for that PR (CLAUDE.md §3).

A future improvement (tracked under #58 phase work) is a CI lint that fails if the three `UV_VERSION` references drift. Until that lands, the three-file edit is operator discipline.

## Risks

- **Outbound network policy.** The hook fetches from `github.com/astral-sh/uv/releases`. If the environment's network policy denies that, the hook fails at session start. Confirm policy before first use; see https://code.claude.com/docs/en/claude-code-on-the-web for policy options.
- **Hook execution mode is synchronous.** The session does not become interactive until `uv sync --locked` completes (typically <10 s on a warm container, longer on a fresh one). This is intentional — it guarantees the first command sees the pinned `uv` and the locked venv. If startup latency becomes a problem, the script can switch to the async pattern (`{"async": true, "asyncTimeout": 300000}`) at the cost of a race window where early commands may see stale `uv`.

## References

- [#106](https://github.com/tvna/claude-md/issues/106) — original problem (stale default uv) and decision record.
- [#109](https://github.com/tvna/claude-md/issues/109) — `.claude/settings.json` carve-out that enables the in-repo hook.
- [#58](https://github.com/tvna/claude-md/issues/58) — parent governance issue for the `.claude/` prohibition.
- `docs/repo-scope.md` § "Security tradeoff for `.claude/settings.json`" — risk-acceptance record.
- `.github/workflows/generate-agents.yml`, `.github/workflows/verify-apm-drift.yml` — canonical `UV_VERSION` source.
- `pyproject.toml` — declares `required-version = ">=0.11.8"`.
- https://code.claude.com/docs/en/claude-code-on-the-web — environment / network policy documentation.
