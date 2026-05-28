# Remote Execution Environment — uv Provisioning Runbook

This document is the operator-facing runbook for keeping the remote execution environment's `uv` aligned with what CI uses. Original problem and decision record: [#106](https://github.com/tvna/claude-md/issues/106). The `.claude/settings.json` governance carve-out that enables the in-repo hook below: [#109](https://github.com/tvna/claude-md/issues/109).

The Claude Code on the Web remote environment ships with a stale `uv` (`0.8.17`) that does not satisfy `pyproject.toml`'s pinned `[tool.uv].required-version`. Sessions need a working `uv` from the first command, without manual reinstall.

## SoT layout

| Location | Target | Purpose |
|---|---|---|
| `pyproject.toml` `[tool.uv].required-version` | All | **Single source of truth for the pinned uv version.** Exact `==X.Y.Z` pin (see [#112](https://github.com/tvna/claude-md/issues/112) for the tradeoff). |
| `scripts/uv_pin.py` | All | Pin reader / drift checker / upstream-staleness checker. Single implementation consumed by CI, the SessionStart hook, and `tests/test_uv_pin.py`. |
| `tests/test_uv_pin.py` | CI | Pytest suite for `scripts/uv_pin.py` (run by the `lint-uv-pin` job before the drift check). |
| `.github/workflows/generate-agents.yml`, `.github/workflows/verify-apm-drift.yml` | CI | Call `scripts/uv_pin.py read` to derive the version, then install via the existing `curl` flow. No version literal lives here. |
| `scripts/install-uv.sh` | Remote session | Calls `scripts/uv_pin.py read` to derive the pin, then installs `uv` at SessionStart. |
| `.claude/settings.json` | Remote session | Registers `scripts/install-uv.sh` as the `SessionStart` hook. Permitted under the [#109](https://github.com/tvna/claude-md/issues/109) carve-out in `docs/standards/repo-scope.md`. |
| `.codex/hooks.json` | Codex session | Registers the same SessionStart hook shape for Codex. The uv installer remains Claude-remote-gated until Codex documents a stable remote-only signal; the language-context hook consumes Codex's `cwd` event field. Tracked by [#604](https://github.com/tvna/claude-md/issues/604) / [#606](https://github.com/tvna/claude-md/issues/606) / [#616](https://github.com/tvna/claude-md/issues/616). |
| `.github/workflows/verify-agents.yml` (`lint-uv-pin` job) | CI | Drift gate — runs `pytest tests/test_uv_pin.py` then `scripts/uv_pin.py drift`. Fails any PR that re-introduces a uv version literal outside `pyproject.toml`. See [#112](https://github.com/tvna/claude-md/issues/112). |
| `.github/dependabot.yml` | CI | Bumps GitHub Actions SHAs and `uv.lock` entries weekly. The uv binary pin itself is bumped manually (see *Update procedure* below). |
| `docs/standards/remote-environment.md` *(this file)* | — | Runbook: how the hook works, how the SoT propagates, verification, update procedure. |

## How it works

1. Every new Claude Code on the Web session triggers the `SessionStart` hook registered in `.claude/settings.json`.
2. The hook invokes `scripts/install-uv.sh`, which is a no-op when `CLAUDE_CODE_REMOTE` is not set (so local dev sessions are unaffected).
3. In the remote environment, the script reads `[tool.uv].required-version` from `pyproject.toml`, strips the leading `==`, and compares against the installed `uv`. If it differs (default container ships `0.8.17`), it downloads and installs the pinned version to `$HOME/.local/bin/uv`, overwriting the stock binary at the same path.
4. It exports `$HOME/.local/bin` on `$PATH` for the rest of the session (via `$CLAUDE_ENV_FILE` when present).
5. Finally, `uv sync --locked` warms the project venv against the locked dependencies.

The script is idempotent: when a container is reused and `uv` is already at the pinned version, the install is skipped and only `uv sync --locked` runs.

## Why not the Web UI setup script

An earlier draft of this runbook ([#107](https://github.com/tvna/claude-md/pull/107)) proposed registering the same shell in the Claude Code on the Web Environment setup-script field instead of an in-repo hook. That approach was rejected once [#109](https://github.com/tvna/claude-md/issues/109) carved out `.claude/settings.json`:

- The Web UI configuration is not under git history — it cannot be code-reviewed, diffed, or reproduced when the environment is recreated.
- Drift between the Web UI value and the pin in `pyproject.toml` is invisible to the repo.
- The same shell-execution risk that motivated the broad `.claude/` ban applies *more* to the Web UI script, because it sits entirely outside change control.

The carve-out for `.claude/settings.json` pulls the hook surface back under PR review. See `docs/standards/repo-scope.md` § "Security tradeoff for `.claude/settings.json`" for the recorded risk-acceptance.

## Codex boundary

Codex consumes this repository's universal instruction surface through `AGENTS.md`. Issue [#604](https://github.com/tvna/claude-md/issues/604) establishes the narrow `.codex/hooks.json` carve-out for repository-owned deterministic hooks, and [#606](https://github.com/tvna/claude-md/issues/606) lands the first implementation slice.

The Codex hook config may mirror existing Claude hook scripts only when the script behavior is tested for both payload shapes or is payload-independent. Do not add Codex-only hook behavior that weakens the Claude guardrail or assumes complete hook parity. Current documented Codex limits include incomplete shell interception for some shell paths and unsupported `permissionDecision: "ask"` behavior in `PreToolUse`.

As of 2026-05-28, the official Codex hooks documentation defines `SessionStart.source` as `startup`, `resume`, `clear`, or `compact`, and defines shared hook input fields such as `session_id`, `cwd`, `hook_event_name`, `model`, and `permission_mode`. Those fields identify hook lifecycle and workspace context, not whether the session is local, cloud, SSH-backed, or controlled remotely from another device. The official Codex cloud-environment documentation describes setup scripts, maintenance scripts, and user-configured environment variables, but it does not document a built-in remote-only environment variable for repo hooks.

When a Codex remote environment needs the same dependency state, use the verification commands below as the contract until Codex documents a stable remote-only signal. Do not treat `SessionStart.source`, `session_id`, `cwd`, `model`, `permission_mode`, or user-defined Codex environment variables as sufficient install gates, and do not make `scripts/install-uv.sh` perform network installation in local Codex sessions.

Once Codex documents a remote-only signal, the implementation path is intentionally narrow:

1. Add that signal to the guard in `scripts/install-uv.sh` without changing `CLAUDE_CODE_REMOTE=true` behavior.
2. Add a shell-level test that proves local Codex-shaped environments remain no-op and the documented remote signal enters the install path.
3. Update this runbook with the exact official documentation URL, the rollback command, and a manual remote verification transcript.

## Why not nix

- Nix is not pre-installed in the remote environment; installing it adds 60–90 s to every container creation just to deliver one binary.
- `nixpkgs.uv` trails upstream uv releases by up to several days, working against the "always current" goal.
- A `flake.nix` for a single binary conflicts with CLAUDE.md §4 ("minimum code that solves the problem").

Decision recorded in [#106](https://github.com/tvna/claude-md/issues/106).

## Verification

In a fresh remote session:

```sh
PIN="$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml","rb"))["tool"]["uv"]["required-version"].lstrip("="))')"
uv --version                                           # must print: uv $PIN
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

The uv version lives in **one place only**: `[tool.uv].required-version` in `pyproject.toml`. To bump:

1. Edit `pyproject.toml` — change `required-version` to the new `==X.Y.Z` pin. That is the only file you touch.
2. Open a PR. CI must show green for `verify-agents` (which includes the `lint-uv-pin` drift gate from [#112](https://github.com/tvna/claude-md/issues/112)) and `verify-apm-drift`.
3. Open a new session against the PR branch and run the [Verification](#verification) recipe end-to-end.
4. Record the bump in the retrospective issue for that PR (CLAUDE.md §3).

Upstream-follow: Dependabot (`.github/dependabot.yml`) does not natively bump `[tool.uv].required-version`. The `lint-uv-pin` job emits a `::warning::` annotation on every PR when the pin trails the latest upstream uv release — that warning is the operator's cue to open a one-line bump PR. (If staleness reminders prove inadequate, switching to Renovate is config-only; tracked as a potential follow-up under #58.)

## Risks

- **Outbound network policy.** The hook fetches from `github.com/astral-sh/uv/releases`. If the environment's network policy denies that, the hook fails at session start. Confirm policy before first use; see https://code.claude.com/docs/en/claude-code-on-the-web for policy options.
- **Hook execution mode is synchronous.** The session does not become interactive until `uv sync --locked` completes (typically <10 s on a warm container, longer on a fresh one). This is intentional — it guarantees the first command sees the pinned `uv` and the locked venv. If startup latency becomes a problem, the script can switch to the async pattern (`{"async": true, "asyncTimeout": 300000}`) at the cost of a race window where early commands may see stale `uv`.

## References

- [#106](https://github.com/tvna/claude-md/issues/106) — original problem (stale default uv) and decision record.
- [#109](https://github.com/tvna/claude-md/issues/109) — `.claude/settings.json` carve-out that enables the in-repo hook.
- [#58](https://github.com/tvna/claude-md/issues/58) — parent governance issue for the `.claude/` prohibition.
- `docs/standards/repo-scope.md` § "Security tradeoff for `.claude/settings.json`" — risk-acceptance record.
- `pyproject.toml` — canonical `[tool.uv].required-version` (the single source of truth, see [#112](https://github.com/tvna/claude-md/issues/112)).
- `.github/workflows/generate-agents.yml`, `.github/workflows/verify-apm-drift.yml` — consumers via inline `tomllib` read.
- `.github/workflows/verify-agents.yml` (`lint-uv-pin` job) — drift gate that fails any reintroduction of a uv-version literal outside `pyproject.toml`.
- `.github/dependabot.yml` — weekly bumps for `github-actions` SHAs and `uv.lock` entries.
- https://code.claude.com/docs/en/claude-code-on-the-web — environment / network policy documentation.
