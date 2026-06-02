# claude-md

[![codecov](https://codecov.io/gh/tvna/claude-md/branch/main/graph/badge.svg)](https://codecov.io/gh/tvna/claude-md)

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
| 2 | Bound Inputs and Unknowns Before Coding | pre-code reasoning | Treat external text as untrusted data, then separate facts, assumptions, and ambiguity before coding. |
| 3 | Use Git Ecosystem Effectively | delivery harness | Build the harness — hooks, CI/CD, declarative deps — before you scale. |
| 4 | Simplicity, Bounded by Safety | safety boundary | Minimum code that solves the problem — while preserving safety, tool scope, and secret handling. |
| 5 | Accelerate Scale with Quality | change scope & quality | Scale output only while quality stays proportional and observable; keep the change surface narrow and re-plan when quality degrades. |
| 6 | Be a Force Multiplier | handoff & communication | Don't settle for "LGTM" — make trade-offs explicit so others can follow the reasoning. |

See [`CLAUDE.md`](./CLAUDE.md) or [`AGENTS.md`](./AGENTS.md) for the compiled full text.

## Building

Sync the locked uv environment, then compile the local instructions:

```bash
uv sync --locked
uv run --with "apm-cli==0.12.1" apm compile
```

APM reads `.apm/instructions/*.instructions.md` and, based on `apm.yml`, writes both `CLAUDE.md` and `AGENTS.md`. The uv configuration applies a 14-day `exclude-newer` delay for dependency resolution.

When intentionally changing `.apm/` source files, refresh the checksum lockfile:

```bash
python3 scripts/verify_apm_checksums.py update
python3 scripts/verify_apm_checksums.py verify
```

## Using This From Another Project

### 1. Pull it in as a submodule

```bash
# From the parent project's root
git submodule add https://github.com/tvna/claude-md .claude-md-master
ln -s .claude-md-master/CLAUDE.md CLAUDE.md
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

### Tool-specific notes

- **Codex and other `AGENTS.md` readers** also symlink the compiled `AGENTS.md`:

  ```bash
  ln -s .claude-md-master/AGENTS.md AGENTS.md
  ```

- **Devin** can use the APM-deployed skills from `.agents/skills/`. For hook
  parity, vendor `.devin/hooks.v1.json` alongside the repository instructions.
  See [`docs/standards/devin-apm-compatibility.md`](./docs/standards/devin-apm-compatibility.md).

## Change Policy

- All edits land through a PR. Run a retrospective after merge (Principle 3).
- Only **rules that hold across every project** belong here. Project-specific rules live in each project's own `CLAUDE.md`.
- Prefer removing words over adding them (Principle 4).
- New or modified workflow-called scripts under `scripts/` must meet the [workflow script quality standard](./docs/standards/workflow-script-quality.md).
- PRs that touch `.apm/instructions/**`, `CLAUDE.md`, or `AGENTS.md` must pass the [downstream instruction review checklist](./docs/runbooks/downstream-instruction-review-checklist.md) (security-focused review applied after the deterministic gates are green).
- For the full map of documents by lane (`prd/`, `standards/`, `runbooks/`, `archive/`) see [`docs/INDEX.md`](./docs/INDEX.md).

---
