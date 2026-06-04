# rtk auto-rewrite hook: verification-first runbook

> Operator procedure for deciding whether to enable the `rtk` (rtk-ai/rtk)
> auto-rewrite PreToolUse hook in the Claude agent devcontainer. The `rtk`
> binary itself is already provisioned by `flake.nix` (Refs #1193 / PR #1195);
> this runbook governs the *next* step -- the transparent command rewrite -- and
> exists because that step's effectiveness is unverifiable in the Claude Code on
> the Web environment and must be confirmed in a live session before any hook is
> shipped. Refs #1199.

## What the hook would do

`rtk init -g` (for Claude Code) writes a `PreToolUse` hook into
`~/.claude/settings.json`:

```json
{
  "hooks": {
    "PreToolUse": [
      { "matcher": "Bash", "hooks": [ { "type": "command", "command": "rtk hook claude" } ] }
    ]
  }
}
```

`rtk hook claude` reads the PreToolUse JSON from stdin and returns
`hookSpecificOutput.updatedInput.command` with the command rewritten to its
token-optimized proxy form, e.g. `git status` -> `rtk git status`,
`echo hi && ls` -> `echo hi && rtk ls`. Unknown commands pass through
unchanged. Observed against the pinned v0.42.1 binary, the emitted object
carries `permissionDecisionReason` + `updatedInput` and does **not** set
`permissionDecision`.

The declarative integration point in this repository is
`.devcontainer/config/claude/settings.json`, which
`.devcontainer/scripts/configure-agent-runtime.sh` copies verbatim to
`~/.claude/settings.json` (the `case "$agent" in claude)` arm). The hook
command `rtk` must resolve on PATH when the hook fires; gh/uv/apm are symlinked
into `/usr/local/bin` by `install_nix_binary`, and `rtk` would need the same.

## Why verification must come first

There is a decisive, unverified risk that the rewrite is a **no-op in this
repository**:

- Claude Code issue
  [#15897](https://github.com/anthropics/claude-code/issues/15897)
  (Closed as not planned; reported on v2.0.76) describes `updatedInput` being
  ignored -- the original command runs instead -- when a PreToolUse hook
  returns the rewrite (the report ties it to `permissionDecision: "allow"`
  and/or to multiple PreToolUse hooks executing).
- This repository already ships **four** Bash-matched `PreToolUse` gates in the
  project `.claude/settings.json`: `gate_gh_cli`, `preflight_push_base`,
  `preflight_push_session_branch`, `preflight_push_nonempty`. Adding the rtk
  hook makes the event a multiple-hook event.
- The repository pins Claude Code **2.1.154**. Whether #15897 still applies at
  that version, and whether rtk's `permissionDecision`-less output shape trips
  the same path, can only be observed in a live Claude Code session. It cannot
  be reproduced in the Claude Code on the Web environment (no interactive Claude
  Code runtime there; the same `nix build` limitation is recorded in
  `docs/standards/devcontainer-tooling.md`).

If the rewrite is silently discarded, enabling the hook adds a per-Bash-command
subprocess for zero benefit. Hence: confirm the rewrite actually applies before
shipping the hook.

## Safety analysis (holds either way)

Enabling the hook does **not** create a push-safety hole, regardless of whether
the rewrite works:

- If the rewrite is a no-op, every gate sees the original command -- unchanged
  behavior.
- If the rewrite works, `git push` becomes `rtk git push`. The push gates detect
  pushes with `_GIT_PUSH_RE = re.compile(r"(?m)^\s*(?:rtk\s+)?git\s+push\b")`
  (`scripts/preflight_push_base.py`, `preflight_push_session_branch.py`,
  `preflight_push_nonempty.py`), whose optional `rtk` prefix matches both
  `git push` and the rewritten `rtk git push`. The prefix was added by the
  enablement PR (Refs #1199); before that the line-anchored regex would have
  missed `rtk git push`. Push safety is additionally defended in depth by the
  git `pre-push` hook (`preflight_all.py`) and CI, which run regardless.
- `gate_gh_cli` matches `gh <subcommand>` mid-string, so `rtk gh ...` still
  triggers it -- no bypass there.

`rtk hook claude` performs only local string rewriting (reads stdin, writes
stdout); it needs no network at runtime, so no `.devcontainer/network/*.allowlist`
entry is required.

## Live-session verification procedure (go / no-go)

Run inside a real Claude Code 2.1.154 session in the claude devcontainer.

1. Confirm the binary resolves: `which rtk` and `rtk --version` (expect
   `rtk 0.42.1`).
2. Confirm the expected rewrite shape out-of-band:
   `rtk hook check "git status"` prints `rtk git status`.
3. Establish a baseline counter: `rtk gain --history` (note the current entries;
   `rtk` records each proxied command).
4. Enable the hook for the session by adding the `PreToolUse` Bash ->
   `rtk hook claude` block to `~/.claude/settings.json`, then restart Claude
   Code so the hook is loaded. Leave the project `.claude/settings.json` gates
   in place (this is the real multiple-hook configuration).
5. From the agent's Bash tool, run a harmless rewritable command, e.g.
   `git status`.
6. Observe whether the rewrite applied:
   - **PASS**: `rtk gain --history` shows a new entry for the command (it was
     executed as `rtk git status`), and/or the output is rtk's compacted form.
   - **FAIL (no-op)**: no new `rtk` history entry and native (non-compacted)
     output -- the original command ran, confirming #15897 applies at 2.1.154
     in the multiple-hook configuration.
7. (Optional, to localize the cause) Repeat step 5 with the project
   `.claude/settings.json` Bash gates temporarily removed so the rtk hook is the
   only PreToolUse Bash hook. If the rewrite then applies, the regression is the
   multiple-hook path specifically.

Record the result:

| Field | Value |
|---|---|
| Claude Code version | `rtk --version` / Claude Code build |
| Single-hook rewrite (step 7) | PASS / FAIL |
| Multiple-hook rewrite (step 6) | PASS / FAIL |
| Decision | enable / do not enable |

## Decision

- **Multiple-hook rewrite PASS** -> proceed to the enablement checklist below in
  a follow-up PR.
- **Multiple-hook rewrite FAIL** -> do not enable the hook. The merged binary
  already supports explicit `rtk <cmd>` usage (it is on the devShell PATH);
  prefer that and close / re-scope #1199 as "hook not viable at the pinned
  Claude Code version".

## Enablement checklist

> Status: applied by the rtk hook enablement PR (Refs #1199). The hook and its
> supporting changes ship on that PR's branch so the live-session verification
> above can be run by checking the branch out and rebuilding the claude
> devcontainer. Do **not** merge the enablement PR until a multiple-hook PASS is
> recorded; on a FAIL, close it and re-scope #1199 per the Decision section.

Changes applied by the enablement PR:

- `.devcontainer/config/claude/settings.json`: add
  `{ "matcher": "Bash", "hooks": [ { "type": "command", "command": "rtk hook claude" } ] }`
  under a `PreToolUse` array (preserving the existing `permissions` block).
- `.devcontainer/scripts/configure-agent-runtime.sh`: add
  `install_nix_binary rtk-cli rtk` so `/usr/local/bin/rtk` exists when the hook
  fires (mirrors the gh/uv/apm provisioning).
- Harden the push gates so the rewritten form is still detected: extend
  `_GIT_PUSH_RE` to `(?m)^\s*(?:rtk\s+)?git\s+push\b` in
  `scripts/preflight_push_base.py`, `preflight_push_session_branch.py`, and
  `preflight_push_nonempty.py`, and the `re.search(r"git\s+push\b...")` in
  `preflight_push_session_branch._extract_push_remote_ref`.
- Extend `scripts/preflight_hook_event_keys.py` `HOOK_CONFIG_FILES` to include
  `.devcontainer/config/claude/settings.json`, so its hook event keys are
  PascalCase-gated like the other agent configs.
- Tests: extend `tests/test_devcontainer_agent_runtime.py` to assert
  `install_nix_binary rtk-cli rtk` and the PreToolUse rtk hook in the
  devcontainer settings; add regex tests asserting the push gates fire on both
  `git push` and `rtk git push`.
- Do **not** inject `RTK.md` / `@RTK.md` into `CLAUDE.md` or `AGENTS.md`: those
  files are APM-generated and the `apm compile` drift gate (portable-pr-policy)
  would fail. Decide separately whether a standalone instruction file is wanted.
- No allowlist change (the hook is local-only).

## See also

- [`docs/standards/devcontainer-tooling.md`](../standards/devcontainer-tooling.md)
  -- the devcontainer tool provisioning standard (and the `nix build` web-env
  limitation).
- [`.devcontainer/scripts/configure-agent-runtime.sh`](../../.devcontainer/scripts/configure-agent-runtime.sh)
  -- where `~/.claude/settings.json` is provisioned and tools are symlinked.
- [`flake.nix`](../../flake.nix) -- the pinned `rtk-cli` derivation.
