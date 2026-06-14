# Parallel agent dispatch runbook

Operator procedure for the case where the work is a set of
clear-responsibility, individually simple changes whose volume is high
but whose domains are independent -- not the case where a single change
has become complex. Complexity is not the trigger; **task independence
is**. This runbook names the two dispatch modes, the worktree-isolation
path that lets the high-volume case run concurrently without conflicts,
and the integration step that closes the loop.

It is the operational sequencing for three skills the repository already
ships and for the dispatch reference in
[CLAUDE.md](../../CLAUDE.md) section 3:

- [`.agents/skills/dispatching-parallel-agents/SKILL.md`](../../.agents/skills/dispatching-parallel-agents/SKILL.md)
- [`.agents/skills/subagent-driven-development/SKILL.md`](../../.agents/skills/subagent-driven-development/SKILL.md)
- [`.agents/skills/using-git-worktrees/SKILL.md`](../../.agents/skills/using-git-worktrees/SKILL.md)

## When this runbook applies

Use it when **all** of the following hold:

- The work decomposes into 2+ tasks, each with a clear, single
  responsibility.
- Each task is individually simple (a well-specified change, not an
  open-ended investigation).
- The volume is high enough that sequential execution is the bottleneck.
- The tasks are independent: no shared state, no ordering dependency
  between them.

Do **not** use it when tasks are tightly coupled, when one task's output
feeds another, or when understanding requires holding the whole system in
view at once. Those belong to a single agent, per the
`dispatching-parallel-agents` "Don't use when" list.

Per CLAUDE.md section 3, dispatch happens **after** the deterministic
gates pass, at one concentrated point -- not continuously and not as a
substitute for the harness gates.

## Decision: which mode

```
Independent tasks (no shared state, no ordering)?
  |
  +-- No  --> single agent; this runbook does not apply
  |
  +-- Yes --> Do the tasks write to the same files / workspace?
                |
                +-- No (separate files/subsystems)
                |     --> Mode A: concurrent dispatch
                |
                +-- Yes (same workspace, conflict risk)
                      --> Mode B: sequential per task,
                          or isolate each task in its own
                          git worktree to recover concurrency
```

The split exists because `subagent-driven-development` lists "Dispatch
multiple implementation subagents in parallel (conflicts)" as a Red Flag.
Concurrency is safe only once the shared-workspace conflict is removed --
either by the tasks naturally touching disjoint files (Mode A) or by
isolating each task in its own worktree (Mode B + worktrees).

## Mode A: concurrent dispatch (independent domains)

For tasks that touch disjoint files or subsystems with no shared state.

1. Group the work by responsibility. Each group is one focused task with
   a specific scope, a clear goal, explicit constraints ("do not change
   code outside <area>"), and a required output summary. See the
   `dispatching-parallel-agents` "Agent Prompt Structure" section.
2. Dispatch one agent per group, concurrently. Each agent gets only the
   context it needs -- it does not inherit the coordinator's history.
3. Integrate (see [Integration](#integration-and-verification)).

## Mode B: same-workspace work

For tasks that would otherwise edit the same files or share resources.

### B1. Sequential (default, no extra setup)

Execute one task at a time, a fresh subagent per task, with the two-stage
review after each (spec compliance, then code quality) per
`subagent-driven-development`. This is correct but does not parallelize
the high-volume case.

### B2. Worktree-isolated concurrency (recover parallelism)

When the volume justifies it, remove the conflict instead of serializing:
give each independent task its own isolated workspace via
`using-git-worktrees`, then dispatch concurrently as in Mode A.

1. Confirm isolation support. Follow `using-git-worktrees` Step 0: detect
   whether you are already in a linked worktree, and prefer a native
   worktree tool over raw `git worktree add`. Never create a nested
   worktree inside an existing one.
2. Obtain operator consent for worktree creation if no preference is
   already declared (per the skill's Step 0).
3. Create one isolated workspace per independent task. For the manual
   fallback, verify the worktree directory is git-ignored before
   creating it (`using-git-worktrees` Step 1b safety check).
4. Dispatch one agent per worktree, concurrently. Because each agent has
   its own working tree, same-named files no longer collide.
5. Integrate the per-worktree branches back through the normal PR loop;
   resolve any cross-task overlap at integration, not mid-flight.

Sandbox note: if worktree creation is blocked (permission/sandbox
denial), fall back to Mode B1 sequential in place and say so, per the
skill's sandbox-fallback rule.

## Integration and verification

Concurrency is not done until the results are reconciled. Per the
`dispatching-parallel-agents` "Verification" section:

1. Read each agent's summary; confirm each stayed within its scope.
2. Check for conflicts -- did any two agents edit the same code despite
   the independence assumption? If so, the decomposition was wrong;
   reconcile before proceeding.
3. Run the full test suite so the combined result is verified, not just
   each part in isolation.
4. Spot-check for systematic errors agents can share.

## What this runbook does not add

- It adds no automation that auto-dispatches agents. Dispatch stays a
  judgment call the coordinator makes after the gates pass; no hook in
  `.claude/settings.json`, `.codex/hooks.json`, `.devin/hooks.v1.json`,
  or `scripts/agent_hooks_source.json` fires it.
- It does not parallelize implementation of coupled tasks. The Red Flag
  against concurrent implementation subagents stands; Mode B2 removes the
  conflict (separate worktrees), it does not waive the rule.

## Companion

- [`.agents/skills/dispatching-parallel-agents/SKILL.md`](../../.agents/skills/dispatching-parallel-agents/SKILL.md) -- independent-domain concurrent dispatch
- [`.agents/skills/subagent-driven-development/SKILL.md`](../../.agents/skills/subagent-driven-development/SKILL.md) -- fresh subagent per task plus two-stage review
- [`.agents/skills/using-git-worktrees/SKILL.md`](../../.agents/skills/using-git-worktrees/SKILL.md) -- workspace isolation that enables Mode B2
- [CLAUDE.md](../../CLAUDE.md) section 3 -- dispatch after gates, at one concentrated point
- Refs #226, #1709
