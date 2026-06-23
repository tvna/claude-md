# Agent-agnostic merge-readiness loop

The path from "PR opened" to "ready to merge, handed off" must reach the
same just-before-merge state no matter which agent drives it (Claude, Codex,
Devin). This runbook documents that loop and the deterministic harness pieces
that make each step agent-independent, so a future session or a different
agent reproduces the no-repair path without this session's context.

## The loop

```
open PR
  -> CI monitor starts          (PostToolUse hook, all agents)
  -> mergeability is surfaced    (PostToolUse hook, all agents)
       |
       +-- clean   -> watch required checks -> hand off at just-before-merge
       +-- behind  -> scripts/refresh_pr_branch.py --push  (deterministic)
       |              then re-check (loops back to mergeability)
       +-- dirty   -> replacement branch
                      docs/runbooks/update-pr-branch-recovery.md
```

## What makes each step agent-agnostic

The per-agent hook configs are generated from a single source of truth,
`scripts/agent_hooks_source.json`, by `scripts/gen_agent_hooks.py` into
`.claude/settings.json`, `.codex/hooks.json`, and `.devin/hooks.v1.json`
(devin mirrors codex). The merge-readiness hooks are wired for every agent:

| Step | Mechanism | Event | Agents |
|---|---|---|---|
| CI monitor auto-start | `scripts/post_pr_create_ci_monitor.py` | PostToolUse on `create_pull_request` (and `mcp__codex_apps__github._create_pull_request`) | Claude, Codex, Devin |
| Mergeability surfaced | `scripts/check_pr_mergeability.py` | PostToolUse on the same tools; also SessionStart scan | Claude, Codex, Devin |
| Behind -> up to date | `scripts/refresh_pr_branch.py` | invoked from the advisory above | any agent (plain git, no agent-specific tool) |
| Behind/dirty on resume | `scripts/check_pr_mergeability.py session-start` | SessionStart | Claude, Codex, Devin |

The previously agent-specific weak point was the **behind -> up to date**
step: the advisory used to suggest `force-push`, which the
`non_fast_forward` ruleset blocks, so an agent had to reason out the
unsanctioned `git merge origin/main && git push` workaround on its own. That
reasoning is now encoded in `scripts/refresh_pr_branch.py` and pointed to by
`check_pr_mergeability.py`, so every agent gets the same deterministic step.
See `docs/runbooks/refresh-behind-pr.md`.

## Scope note: the handoff survey is a separate concern

The `Stop`-event retro survey
(`scripts/gate_handoff_retro_survey_askuserquestion.py`) is Claude-only
because it depends on the `AskUserQuestion` tool, which Codex and Devin do
not have. That gate captures *retrospective* data at handoff; it is not part
of reaching merge-readiness, and it is intentionally out of scope for this
loop. The merge-readiness loop above reaches the just-before-merge state
identically across agents without it. See
`docs/runbooks/pre-merge-retro-survey.md` for that separate gate.

## Verifying agent parity

- `python3 scripts/gen_agent_hooks.py --check`; the generated configs match
  the source of truth (no drift).
- `tests/test_codex_hooks_config.py` / `tests/test_devin_hooks_config.py` --
  assert the CI-monitor and mergeability hooks are wired on PR creation for
  Codex and Devin, so the loop cannot silently regress to Claude-only.
- Re-running the same handoff under Codex should reach just-before-merge with
  no agent-specific steps (manual, cross-agent confirmation).

## Companion

- `docs/runbooks/refresh-behind-pr.md`; the deterministic behind step.
- `docs/runbooks/update-pr-branch-recovery.md`; the conflict / replacement path.
- `docs/runbooks/ci-monitoring-polling-vs-webhook.md`; the CI monitor options.
- `docs/standards/agent-hooks-generation.md`; how per-agent configs are generated.
- `scripts/agent_hooks_source.json`; single source of truth for the hooks.
- Refs #1361, #1359.
