# Agent Hook Config Generation Standard

Tracking issue: [#1317](https://github.com/tvna/claude-md/issues/1317).
Related working-directory constraint: [#783](https://github.com/tvna/claude-md/issues/783).

This is the adopted contract for how the per-agent hook configuration files are
produced. They are **generated artifacts**, not hand-maintained files.

## Problem

The three agent hook configs registered hook commands as repository-root
relative paths:

| File | Example command |
|---|---|
| `.claude/settings.json` | `python3 scripts/check_hooks_path.py` |
| `.codex/hooks.json` | `scripts/install-uv.sh` |
| `.devin/hooks.v1.json` | `python3 scripts/plan_language_context.py` |

A relative `scripts/...` path only resolves when the agent launches the hook
with the working directory at the repository root. When a session starts from a
subdirectory (`cd subdir && claude`), the path misses the script and the hook
silently fails to run -- including the safety gates (branch/base checks,
non-ASCII preflight, sensitive-read blocks). The scripts themselves already
resolve the repo root internally (`Path(__file__).resolve().parents[...]` for
Python, `$(dirname "$0")` for shell); the gap was purely that the **command
string could not reach the script** from a non-root CWD.

## Source of truth and generator

| Location | Role |
|---|---|
| `scripts/agent_hooks_source.json` | Single source of truth. Holds each agent config with clean repo-relative command strings that humans read and edit. |
| `scripts/gen_agent_hooks.py` | Generator. Renders each agent config from the source and injects the CWD-independence wrapper. `--check` is the drift gate. |
| `.claude/settings.json`, `.codex/hooks.json`, `.devin/hooks.v1.json` | Generated artifacts. Do not edit directly. |
| `tests/test_gen_agent_hooks.py` | Unit + drift coverage for the generator. |

`.devin/hooks.v1.json` is declared in the source with `"mirror": "codex"` so it
stays byte-for-byte identical to `.codex/hooks.json`
(see [devin-apm-compatibility.md](devin-apm-compatibility.md)) without
duplicating the config.

## Per-agent installer scope

Every SessionStart provisioning installer is classified **shared** (intended for
claude + codex + devin). The decision and a one-line rationale for each installer
live in the `installer_scope_audit` sibling key of
[`scripts/agent_hooks_source.json`](../../scripts/agent_hooks_source.json)
(Refs [#1606](https://github.com/tvna/claude-md/issues/1606)). The generator
reads only `targets`, so that key documents intent without changing any
generated config or the `--check` drift gate.

Rationale: every web installer reproduces a devcontainer capability that the nix
path skips, and codex/devin web sessions equally lack that nix path, so all
installers are provisioned for uniform cross-agent parity. Each entry still
records `functionally_required` -- whether a pre-commit / local gate invokes the
binary directly (`true` for `uv`, `bun`, `actionlint`; `false` for the
explicit-use binaries `rtk`, `apm`, `waza`, `ccusage`, `zizmor`, `lychee`,
`betterleaks`) -- to show which installers are already operationally needed
versus provisioned for uniformity. `ccusage` is an accepted no-op under
codex/devin, where its Claude-scoped telemetry has no data source.

The `wired` field records the **current** wiring. Installers not yet wired into
codex+devin carry a `wiring_followup`: the actual wiring **and** the remote-gate
widening it needs (each not-yet-shared script gates on `CLAUDE_CODE_REMOTE` only,
so config wiring alone is a no-op under codex's `CODEX_CODE_REMOTE` signal -- the
script must also widen its gate and persist PATH for codex, mirroring
`install-uv.sh`) are deferred to
[#1608](https://github.com/tvna/claude-md/issues/1608). This issue (#1606) is
audit-only.

## The CWD-independence wrapper

For every command that references a repo-local `scripts/` file, the generator
prepends:

```
cd "$(git rev-parse --show-toplevel)" && <command>
```

`git rev-parse --show-toplevel` is the same repo-root resolver
`.githooks/pre-push` already uses, and it works from any subdirectory of the
worktree. `$CLAUDE_PROJECT_DIR` is **intentionally avoided**: it is unset in the
FleetView remote environment and would expand to a broken path
(Refs [#783](https://github.com/tvna/claude-md/issues/783)).

Commands that are already location-independent are left untouched: the
APM/superpowers `${CLAUDE_PLUGIN_ROOT}` passthrough and `PATH` binaries such as
`rtk hook claude` carry no `scripts/` token, so the generator skips them.

Wrapping is idempotent (an already-wrapped command is returned unchanged), so
the generator is safe to run repeatedly.

### Edge case

If `git rev-parse --show-toplevel` fails (the CWD is outside any git worktree,
or git is absent), the `cd` fails and the `&&` short-circuits, so the hook does
not run -- the same outcome as the pre-existing relative-path behavior in that
already-broken context, not a regression. The wrapper fixes the in-repo
subdirectory case, which is the reported defect.

## Recurrence prevention

The wrapper is applied at **generation time**, so it cannot drift per agent or
be forgotten when a hook is added. The contract is enforced deterministically:

- `gen-agent-hooks` in [`.pre-commit-config.yaml`](../../.pre-commit-config.yaml)
  runs `scripts/gen_agent_hooks.py --check` whenever the source or any generated
  config changes. It also runs in CI via `prek` inside `preflight_all.py`.
- `--check` fails when a committed config does not match a fresh render -- i.e.
  the moment someone hand-edits a config (and could reintroduce a CWD-relative
  command) instead of regenerating.

## How to change a hook

1. Edit `scripts/agent_hooks_source.json` (clean repo-relative commands).
2. Run `python3 scripts/gen_agent_hooks.py` to regenerate the three configs.
3. Commit the source and the regenerated configs together.

The drift gate rejects step 3 if the configs were not regenerated from the
source.

## Verification

```sh
python3 scripts/gen_agent_hooks.py --check                 # exit 0 on a clean tree
python3 -m pytest tests/test_gen_agent_hooks.py -q         # generator contract
python3 -m pytest tests/test_claude_settings_config.py \
  tests/test_codex_hooks_config.py tests/test_devin_hooks_config.py -q
```
