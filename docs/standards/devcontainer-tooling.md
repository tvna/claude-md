# Devcontainer Tooling Provisioning Standard

This document is the adopted rule for keeping the devcontainer's tool set in
sync with what the repository's gates need at runtime. Original problem and
decision record: [#1103](https://github.com/tvna/claude-md/issues/1103)
(retrospective for [#1100](https://github.com/tvna/claude-md/issues/1100) /
[#1101](https://github.com/tvna/claude-md/issues/1101)).

## Problem

The skill quality gate landed with a pre-commit hook that needs the `waza`
binary, but `waza` was never added to `flake.nix`. The devcontainer has no Go
toolchain and an egress allowlist without the Go module proxy, so committing a
`SKILL.md` change inside the container would have hard-failed. Nothing tied "a
gate needs tool X" to "the devcontainer provides tool X", so the omission was
invisible until exercised.

## Rule

Any CLI a gate needs at runtime MUST be provisioned by the devcontainer
`flake.nix`, declaratively and pinned (mirroring `pinned-uv`, `claude-cli`,
`codex-cli`, `apm-cli`, and `waza-cli`). Runtime `go install` / `curl | bash`
provisioning is reserved for CI, where the toolchain and network are present.

When a tool needs network access at *build* time only (a `fetchurl`
derivation), no egress-allowlist entry is required at runtime. When a tool
reaches the network at *runtime*, add the destination to
`.devcontainer/network/*.allowlist` as well.

## SoT layout

| Location | Purpose |
|---|---|
| `flake.nix` | **Single source of truth for provisioned tools.** Each tool is a pinned `fetchurl` derivation included in the dev shell. |
| `scripts/preflight_all.py` (`Step.required_bin`) | The authoritative declaration that a gate needs a tool at runtime. |
| `scripts/scan_devcontainer_tool_drift.py` | Deterministic gate: every `required_bin` tool must be provisioned in `flake.nix` (matched by a registered marker) or explicitly allowlisted with a rationale. |
| `.github/workflows/verify-agents.yml` (`lint-scripts-static`) | Runs the drift gate on every PR. |
| `.devcontainer/network/*.allowlist` | Runtime egress destinations, when a provisioned tool needs the network at runtime. Each host carries an inline triage rationale. |
| `scripts/scan_allowlist_rationale.py` | Deterministic gate: every allowlist host must carry an inline triage rationale recorded via the network-triage runbook. |

## How the gate works

1. `scan_devcontainer_tool_drift.py` imports `preflight_all.py` and collects
   the union of `Step.required_bin` across all steps.
2. For each tool it looks up a marker in `TOOL_FLAKE_MARKERS` (e.g.
   `waza -> waza-cli`) and asserts the marker appears in `flake.nix`.
3. A `required_bin` tool with no registered marker, or a marker absent from
   `flake.nix`, fails the gate with a remediation message. Tools intentionally
   not in the container go in `ALLOWLIST` with a rationale.

## Adding a new gate-required tool

1. Add a pinned `fetchurl` derivation to `flake.nix` and include it in the
   dev shell (`sharedPackages`).
2. If the tool reaches the network at runtime, add the host to the relevant
   `.devcontainer/network/*.allowlist`.
3. Register the tool in `scan_devcontainer_tool_drift.TOOL_FLAKE_MARKERS`.
4. Run `python3 scripts/scan_devcontainer_tool_drift.py verify` -- it must
   pass before the change merges.

## Network destination triage

Provisioning a tool answers "is the binary present"; it does not answer "is
the tool's outbound traffic safe to allow". Before a runtime destination is
added to a `.devcontainer/network/*.allowlist` file, triage it with the
observe -> evaluate -> decide -> verify procedure in
[`docs/runbooks/devcontainer-tool-network-triage.md`](../runbooks/devcontainer-tool-network-triage.md).

The decision is recorded as an inline trailing rationale comment on the host
entry (`api.example.com  # why this destination is allowed`). That record is
not optional: `scripts/scan_allowlist_rationale.py verify` fails CI (in the
`lint-scripts-static` job) when any allowlist host lacks a rationale, so a new
egress destination cannot be admitted on reviewer memory alone. The inline
`#` is stripped by the allowlist parser, so the rationale never changes the
resolved host set.

## Verification

- `python3 scripts/scan_devcontainer_tool_drift.py verify` exits 0 when every
  gate-required tool is provisioned, exit 1 otherwise.
- `tests/test_scan_devcontainer_tool_drift.py` covers the gate logic and
  asserts the live repository passes.
- `python3 scripts/scan_allowlist_rationale.py verify` exits 0 when every
  egress allowlist host carries an inline triage rationale, exit 1 otherwise;
  covered by `tests/test_scan_allowlist_rationale.py`.
- Note: `nix build` is not runnable in the Claude Code on the Web environment;
  flake derivation changes are verified by pinned SHA256 and by mirroring a
  proven derivation, with real build confirmation deferred to CI or a
  nix-capable host.
