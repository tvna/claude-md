# claude-md

English | [Japanese](./README.ja.md) | [Simplified Chinese](./README.zh.md)

Master repository for personally tuned agent instructions, compiled with [`microsoft/apm`](https://github.com/microsoft/apm) into [`CLAUDE.md`](./CLAUDE.md) and [`AGENTS.md`](./AGENTS.md) for other projects.

## Purpose

- Centralize the principles I use with AI coding agents so that every project stays consistent.
- Keep only **universal, individual-level guidelines** here — never project-specific rules.
- Use APM as the source-of-truth harness: edit `.apm/instructions/`, then compile `CLAUDE.md` and `AGENTS.md`.
- Each project's local agent instructions reference this master and only add their own delta.

## The Six Principles

| # | Principle | Layer | Summary |
|---|-----------|-------|---------|
| 1 | Define the Goal with Plan Mode First | goal & plan structure | Enter plan mode for any task that takes 3+ steps or touches architecture. |
| 2 | Bound the Unknown Before Coding | pre-code reasoning | List assumptions, surface ambiguity, verify or ask — ambiguity earns a question, evidence earns a fix. |
| 3 | Use Git Ecosystem Effectively | delivery harness | Build the harness — hooks, CI/CD, declarative deps — before you scale. |
| 4 | Simplicity, Bounded by Safety | artifact code | Minimum code that solves the problem — never at the cost of safety. |
| 5 | Accelerate Scale with Quality | change scope & agent split | Touch only what you must; split implementation, verification, and exploration across separate agents. |
| 6 | Be a Force Multiplier | handoff & communication | Don't settle for "LGTM" — make trade-offs explicit so others can follow the reasoning. |

See [`CLAUDE.md`](./CLAUDE.md) or [`AGENTS.md`](./AGENTS.md) for the compiled full text.

## Building

Sync the locked uv environment, then compile the local instructions:

```bash
uv sync --locked
uv run --with "apm-cli==0.12.1" apm compile
```

APM reads `.apm/instructions/*.instructions.md` and, based on `apm.yml`, writes both `CLAUDE.md` and `AGENTS.md`. The uv configuration applies a 14-day `exclude-newer` delay for dependency resolution.

## Using This From Another Project

### 1. Pull it in as a submodule

```bash
# From the parent project's root
git submodule add https://github.com/tvna/claude-md .claude-md-master
ln -s .claude-md-master/CLAUDE.md CLAUDE.md
```

For Codex or other tools that read `AGENTS.md`:

```bash
ln -s .claude-md-master/AGENTS.md AGENTS.md
```

### 2. Add project-specific rules

Create a local project instructions file in the parent project and import the master at the top, then list only the project-specific delta below.

```markdown
@.claude-md-master/CLAUDE.md

## Project-specific rules
- (only the delta for this project)
```

### 3. Pulling in updates

```bash
git submodule update --remote .claude-md-master
```

## Change Policy

- All edits land through a PR. Run a retrospective after merge (Principle 3).
- Only **rules that hold across every project** belong here. Project-specific rules live in each project's own `CLAUDE.md`.
- Prefer removing words over adding them (Principle 4).

---
