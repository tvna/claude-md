# Devin APM Compatibility Standard

Tracking issue: [#982](https://github.com/tvna/claude-md/issues/982)

This is the adopted contract for supporting Devin in this repository. The
shared skills and the compiled instruction SoT stay with APM; the
Devin-specific delta is kept small as a compatibility adapter. Hook parity
is fixed by tests, so this lane is `docs/standards/` rather than design-stage
`docs/prd/`.

## Goal

Add Devin as a formally supported target. Keep the source of truth for shared
skills and compiled instructions in APM, and keep any Devin-specific
difference small, expressed as a compatibility adapter.

## Facts

- Devin discovers repository skills from `.agents/skills/<skill-name>/SKILL.md`.
- This repository deploys the Superpowers skills into `.agents/skills` and
  `.claude/skills` from a pinned APM dependency.
- The existing `apm.yml` targets are `claude` and `codex`; the public APM CLI
  has no `devin` target at this time.
- Claude and Codex hooks live separately in `.claude/settings.json` and
  `.codex/hooks.json`, and existing tests fix the presence of the critical
  gates.

## Assumptions

- Devin hooks can be expressed in a JSON shape compatible with Claude Code
  hooks.
- Devin may be able to read `.claude/settings.json`, but for a formal target a
  dedicated `.devin/hooks.v1.json` communicates intent to consumers more
  clearly.
- If APM later adds a native `devin` target, the `.devin/hooks.v1.json` defined
  here can migrate to the APM output.

## Approach

The adopted approach is an APM-first hybrid.

1. Skills: the APM-deployed `.agents/skills` surface is Devin's primary skill
   surface.
2. Hooks: add `.devin/hooks.v1.json` and make the same safety gates as
   Claude/Codex explicit.
3. Tests: fix the JSON validity of `.devin/hooks.v1.json`, the repo-local
   script references, and the core SessionStart/PreToolUse/PostToolUse parity.
4. Docs: provide a reading path for Devin support from the README and the docs
   index.

## Alternatives considered

### A. Rely on `.claude/settings.json` only

Minimal change, but a weak signal for a formal Devin target, and fragile if
Devin's compatibility reading changes in the future.

### B. Wait for a native APM target

Clean as a source of truth, but it does not satisfy the requirement to support
Devin now.

### C. APM-first hybrid (adopted)

Separate the APM-managed skills from explicit Devin hooks. This is the minimal
safe implementation for now, and it migrates cleanly if APM adds more targets
later.

## Implementation boundary

Added by this change:

- `.devin/hooks.v1.json`
- `tests/test_devin_hooks_config.py`
- Devin usage notes in the README
- The entry for this document in `docs/INDEX.md`

Not added by this change:

- Body changes to `.apm/instructions/master.instructions.md`
- Regeneration of `CLAUDE.md` / `AGENTS.md`
- A Devin-specific skill fork
- A target addition to the APM CLI itself

## Verification

- `python3 -m pytest tests/test_devin_hooks_config.py -q`
- `python3 -m pytest tests/test_superpowers_apm_install.py tests/test_claude_settings_config.py tests/test_codex_hooks_config.py -q`
- `python3 scripts/scan_docs_inventory.py verify`
- `python3 scripts/scan_markdown_links.py verify`

Run the APM CLI only when the local `uv` required-version mismatch is resolved.
If the mismatch remains, state that fact explicitly in the PR body.
