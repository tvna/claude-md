# Remote Execution Environment — uv Provisioning Runbook

This document is the operator-facing runbook for keeping the remote execution environment's `uv` aligned with what CI uses. Original problem and decision record: [#106](https://github.com/tvna/claude-md/issues/106). The `.claude/settings.json` governance carve-out that enables the in-repo hook below: [#109](https://github.com/tvna/claude-md/issues/109).

The Claude Code on the Web remote environment ships with a stale `uv` (`0.8.17`) that does not satisfy `pyproject.toml`'s pinned `[tool.uv].required-version`. Sessions need a working `uv` from the first command, without manual reinstall.

## SoT layout

| Location | Target | Purpose |
|---|---|---|
| `pyproject.toml` `[tool.uv].required-version` | All | **Single source of truth for the pinned uv version.** Exact `==X.Y.Z` pin (see [#112](https://github.com/tvna/claude-md/issues/112) for the tradeoff). |
| `scripts/uv_pin.py` | All | Pin reader / drift checker / upstream-staleness checker. Single implementation consumed by CI, the SessionStart hook, and `tests/test_uv_pin.py`. |
| `tests/test_uv_pin.py` | CI | Pytest suite for `scripts/uv_pin.py` (run by the `lint-uv-pin` job before the drift check). |
| `.github/workflows/generate-agents.yml`, `.github/workflows/verify-pr.yml` | CI | Call `scripts/uv_pin.py read` to derive the version, then install via the existing `curl` flow. No version literal lives here. |
| `scripts/install-uv.sh` | Remote session | Calls `scripts/uv_pin.py read` to derive the pin, then installs `uv` at SessionStart. |
| `.claude/settings.json` | Remote session | Registers `scripts/install-uv.sh` as the `SessionStart` hook. Permitted under the [#109](https://github.com/tvna/claude-md/issues/109) carve-out in `docs/standards/repo-scope.md`. |
| `.codex/hooks.json` | Codex session | Registers the same SessionStart hook shape for Codex. The uv installer remains Claude-remote-gated until Codex documents a stable remote-only signal; the language-context hook consumes Codex's `cwd` event field. Tracked by [#604](https://github.com/tvna/claude-md/issues/604) / [#606](https://github.com/tvna/claude-md/issues/606) / [#616](https://github.com/tvna/claude-md/issues/616). |
| `.github/workflows/verify-agents.yml` (`lint-uv-pin` job) | CI | Drift gate — runs `pytest tests/test_uv_pin.py` then `scripts/uv_pin.py drift`. Fails any PR that re-introduces a uv version literal outside `pyproject.toml`. See [#112](https://github.com/tvna/claude-md/issues/112). |
| `.python-version` | All | **Single source of truth for the pinned Python interpreter.** Exact `X.Y.Z` patch so `uv run python` resolves the same interpreter everywhere. See the [Python interpreter pin](#python-interpreter-pin) section and [#1680](https://github.com/tvna/claude-md/issues/1680). |
| `scripts/python_pin.py` | All | Pin reader / consistency checker for `.python-version`. Verifies the pin is exact and its minor matches `requires-python`, ruff, mypy, and `flake.nix`. Mirrored as a `preflight_all` step and run by `verify-agents` / `weekly-maintenance`. Tested by `tests/test_python_pin.py`. |
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

This git-external boundary is not limited to the setup-script field. Per the official docs (https://code.claude.com/docs/en/claude-code-on-the-web § "Network access"), the **network access policy** — the access level (`None` / `Trusted` / `Custom`) and any custom allowed domains — is likewise part of the environment configuration set in the Cloud environment UI at environment create/edit time, and is not stored in git. The `.claude/settings.json` carve-out only pulls the *SessionStart hook* back under PR review; the network policy remains Web-UI-managed (git-external) by design. So when reasoning about what is and is not under change control, treat network access policy the same as the setup-script field — it lives in the Web UI, not the repo.

## Codex boundary

Codex consumes this repository's universal instruction surface through `AGENTS.md`. Issue [#604](https://github.com/tvna/claude-md/issues/604) establishes the narrow `.codex/hooks.json` carve-out for repository-owned deterministic hooks, and [#606](https://github.com/tvna/claude-md/issues/606) lands the first implementation slice.

The Codex hook config may mirror existing Claude hook scripts only when the script behavior is tested for both payload shapes or is payload-independent. Do not add Codex-only hook behavior that weakens the Claude guardrail or assumes complete hook parity. Current documented Codex limits include incomplete shell interception for some shell paths and unsupported `permissionDecision: "ask"` behavior in `PreToolUse`.

As of 2026-05-28, the official Codex hooks documentation defines `SessionStart.source` as `startup`, `resume`, `clear`, or `compact`, and defines shared hook input fields such as `session_id`, `cwd`, `hook_event_name`, `model`, and `permission_mode`. Those fields identify hook lifecycle and workspace context, not whether the session is local, cloud, SSH-backed, or controlled remotely from another device. The official Codex cloud-environment documentation describes setup scripts, maintenance scripts, and user-configured environment variables, but it does not document a built-in remote-only environment variable for repo hooks. The `AGENT=codex` proposal (openai/codex#13416) was closed as not planned as of 2026-05-30.

Because no built-in platform signal exists, `scripts/install-uv.sh` uses an explicit operator opt-in: `CODEX_CODE_REMOTE=true`. This is not a proxy detection mechanism — it is a deliberate deployment decision. Do not treat `SessionStart.source`, `session_id`, `cwd`, `model`, or `permission_mode` as install gates.

**Configuring `CODEX_CODE_REMOTE=true` for Codex cloud tasks:**

In your Codex environment configuration (web dashboard or `codex cloud env` CLI), add the environment variable:

```
CODEX_CODE_REMOTE=true
```

Environment variables configured in the Codex cloud environment are set for the full duration of the task — including the `SessionStart` hook phase — and persist when a cached container is resumed. Do not set `CODEX_CODE_REMOTE=true` in local `.codex/config.toml`, local shell profiles, or any context outside the cloud environment configuration; doing so causes the installer to run in local sessions.

**Rollback:** Remove `CODEX_CODE_REMOTE=true` from the Codex cloud environment configuration. The guard is a single `if` check in `scripts/install-uv.sh`; no other change is required.

**Codex cloud verification** (run inside a Codex cloud task after setting `CODEX_CODE_REMOTE=true`):

```sh
PIN="$(python3 -c 'import tomllib; print(tomllib.load(open("pyproject.toml","rb"))["tool"]["uv"]["required-version"].lstrip("="))')"
uv --version                    # must print: uv $PIN
command -v uv                   # must print: $HOME/.local/bin/uv
uv sync --locked                # must exit 0
```

**Future migration:** When OpenAI documents a built-in Codex remote-only signal, the migration path is narrow:

1. Replace the `[ "${CODEX_CODE_REMOTE:-}" != "true" ]` branch in `scripts/install-uv.sh` with the official signal check, without changing `CLAUDE_CODE_REMOTE=true` behavior.
2. Add a test that proves the official signal enters the install path.
3. Update this runbook with the exact official documentation URL.
4. Retain `CODEX_CODE_REMOTE=true` as a fallback for one release cycle with a deprecation note, then remove it.

## Why not nix

- Nix is not pre-installed in the remote environment; installing it adds 60–90 s to every container creation just to deliver one binary.
- `nixpkgs.uv` trails upstream uv releases by up to several days, working against the "always current" goal.
- A `flake.nix` for a single binary conflicts with CLAUDE.md §4 ("minimum code that solves the problem").

Decision recorded in [#106](https://github.com/tvna/claude-md/issues/106).

This decision applies only to the remote-session hook that repairs a
single pre-existing `uv` binary. The VS Code devcontainer workflow in
[`docs/runbooks/devcontainers.md`](../runbooks/devcontainers.md) uses
Nix for a different problem: provisioning full Claude and Codex
workspace toolchains with isolated agent-specific package sets.

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

The final two commands match the CI `verify-pr.yml` APM drift steps. If they pass locally, the remote session is functionally equivalent to CI.

Direct script test (any environment, no session needed):

```sh
CLAUDE_CODE_REMOTE=true scripts/install-uv.sh         # full install + uv sync
env -u CLAUDE_CODE_REMOTE scripts/install-uv.sh        # no-op, exits 0 silently
```

## Update procedure

The uv version lives in **one place only**: `[tool.uv].required-version` in `pyproject.toml`. To bump:

1. Edit `pyproject.toml` — change `required-version` to the new `==X.Y.Z` pin. That is the only file you touch.
2. Open a PR. CI must show green for `verify-agents` (which includes the `lint-uv-pin` drift gate from [#112](https://github.com/tvna/claude-md/issues/112)) and `portable-pr-policy`.
3. Open a new session against the PR branch and run the [Verification](#verification) recipe end-to-end.
4. Record the bump in the retrospective issue for that PR (CLAUDE.md §3).

Upstream-follow: Dependabot (`.github/dependabot.yml`) does not natively bump `[tool.uv].required-version`. The `lint-uv-pin` job emits a `::warning::` annotation on every PR when the pin trails the latest upstream uv release — that warning is the operator's cue to open a one-line bump PR. (If staleness reminders prove inadequate, switching to Renovate is config-only; tracked as a potential follow-up under #58.)

## Python interpreter pin

`uv run python` is the interpreter that writes the deterministic `docs/generated/` tree (the AST graphs, dependency graph, and trigger map). `requires-python = ">=3.12"` in `pyproject.toml` is a *range*, so without a patch pin `uv run python` binds to whatever 3.12.x the host already has. `ast.unparse` renders nested f-string format specs differently across 3.12 patch releases, so the same generator on two patches produces a one-line diff in `docs/generated/scripts/ast/preflight_all.md` — phantom drift between the post-merge committer ([#1571](https://github.com/tvna/claude-md/issues/1571)), the `verify-docs-drift` gate ([#1574](https://github.com/tvna/claude-md/issues/1574)), and a local pre-push. Follow-up to [#1533](https://github.com/tvna/claude-md/issues/1533); decision record [#1680](https://github.com/tvna/claude-md/issues/1680).

`.python-version` closes that gap. It pins one exact patch (`X.Y.Z`); uv reads it when resolving `uv run python` and downloads that exact interpreter, so every environment converges on the same one.

`scripts/python_pin.py verify` keeps the pin from silently drifting. `requires-python` is the source of truth for the Python *minor*; the gate fails when `.python-version` is not an exact patch, or when its minor diverges from `requires-python`, `[tool.ruff].target-version`, `[tool.mypy].python_version`, or any `python3XY` token in `flake.nix`. It runs in `verify-agents` and `weekly-maintenance`, and is mirrored locally as the `python_pin` `preflight_all` step.

**Bump procedure.** Edit `.python-version` to the new `X.Y.Z` patch (and, if the minor changes, `requires-python`, the ruff/mypy version keys, and the `flake.nix` `python3XY` attributes in the same change). Open a PR; `verify-agents` runs `python_pin verify`, and the `push`-triggered `verify-docs-drift` job confirms a no-op regeneration of `docs/generated/` stays clean under the new interpreter. Record the bump in the PR retrospective (CLAUDE.md §3).

## Risks

- **Outbound network policy.** The hook fetches from `github.com/astral-sh/uv/releases`. If the environment's network policy denies that, the hook fails at session start. Confirm policy before first use; see https://code.claude.com/docs/en/claude-code-on-the-web for policy options.
- **Hook execution mode is synchronous.** The session does not become interactive until `uv sync --locked` completes (typically <10 s on a warm container, longer on a fresh one). This is intentional — it guarantees the first command sees the pinned `uv` and the locked venv. If startup latency becomes a problem, the script can switch to the async pattern (`{"async": true, "asyncTimeout": 300000}`) at the cost of a race window where early commands may see stale `uv`.
- **The pin read must not go through `uv run`.** `scripts/install-uv.sh` reads `[tool.uv].required-version` with a bare `python3` / inline `tomllib` call (`python3 scripts/uv_pin.py read`, before the pinned binary is installed and on `PATH`); the [Verification](#verification) recipe and `scripts/session_uv_local_pin.sh` follow the same pattern. Do not redirect that read through `uv run python`. It would be circular: the stock container `uv` (`0.8.17`) does not satisfy the pin, and `uv run` aborts on a `required-version` mismatch (the failure mode this hook repairs — see [`docs/runbooks/host-uv-pin.md`](../runbooks/host-uv-pin.md)), so the read would fail at the exact moment it is meant to fix the drift. A bare-`python3` read also avoids `uv run`'s implicit project sync (venv creation, dependency install, index network access) for a step that only needs one TOML value. `uv` may run project code only *after* step 4 puts the pinned binary on `PATH`.

## References

- [#106](https://github.com/tvna/claude-md/issues/106) — original problem (stale default uv) and decision record.
- [#109](https://github.com/tvna/claude-md/issues/109) — `.claude/settings.json` carve-out that enables the in-repo hook.
- [#58](https://github.com/tvna/claude-md/issues/58) — parent governance issue for the `.claude/` prohibition.
- `docs/standards/repo-scope.md` § "Security tradeoff for `.claude/settings.json`" — risk-acceptance record.
- `pyproject.toml` — canonical `[tool.uv].required-version` (the single source of truth, see [#112](https://github.com/tvna/claude-md/issues/112)).
- `.github/workflows/generate-agents.yml`, `.github/workflows/verify-pr.yml` — consumers via inline `tomllib` read.
- `.github/workflows/verify-agents.yml` (`lint-uv-pin` job) — drift gate that fails any reintroduction of a uv-version literal outside `pyproject.toml`.
- `.github/dependabot.yml` — weekly bumps for `github-actions` SHAs and `uv.lock` entries.
- https://code.claude.com/docs/en/claude-code-on-the-web — environment / network policy documentation.
- [#616](https://github.com/tvna/claude-md/issues/616) — Codex remote uv provisioning: verified signal research and implementation.
- openai/codex#13416 — `AGENT=codex` env-var proposal; closed as not planned (2026-05-30).
