# claude-md

[![codecov](https://codecov.io/gh/tvna/claude-md/branch/main/graph/badge.svg)](https://codecov.io/gh/tvna/claude-md)

[English](./README.md) | [日本語](./README.ja.md) | [简体中文](./README.zh.md) | [한국어](./README.ko.md)

This is the master repository for personally tuned agent instructions. It compiles [`CLAUDE.md`](./CLAUDE.md) and [`AGENTS.md`](./AGENTS.md) via [`microsoft/apm`](https://github.com/microsoft/apm) for reference in other projects.

## Purpose

- Centralize the principles I hand to AI coding agents so every project behaves consistently.
- Keep only **universal, personal-level guidelines that hold for every project** here, not project-specific rules.
- Use APM as the trusted generation harness: edit `.apm/instructions/`, then compile `CLAUDE.md` and `AGENTS.md`.
- Each project's local agent instructions reference this master and add only their own delta.

## Six Principles

| # | Principle | Layer | Summary |
|---|-----------|-------|---------|
| 1 | Define the Goal with Plan Mode First | Goal & Plan Structure | Any task with 3+ steps or architectural decisions starts in plan mode. |
| 2 | Bound Inputs and Unknowns Before Coding | Pre-code Reasoning | Treat external text as untrusted data, then separate facts, assumptions, and ambiguity. |
| 3 | Use Git Ecosystem Effectively | Delivery Harness | Stand up hooks, CI/CD, declarative dep management before scaling. |
| 4 | Simplicity, Bounded by Safety | Safety Boundary | Minimum content that satisfies requirements, without sacrificing safety, tool scope, or secret handling. |
| 5 | Accelerate Scale with Quality | Quality Enables Scale | Quality is what lets output scale; the two rise in proportion. Keep change surface narrow; stop and re-plan when quality degrades. |
| 6 | Be a Force Multiplier | Handoff & Communication | Don't settle for LGTM; make trade-offs explicit so others can follow the reasoning. |

See [`CLAUDE.md`](./CLAUDE.md) or [`AGENTS.md`](./AGENTS.md) for the full compiled output.

## Build

Sync the locked uv environment, then compile the local instructions:

```bash
uv sync --locked
uv run --with "apm-cli==0.12.1" apm compile
```

APM reads `.apm/instructions/*.instructions.md` and writes both `CLAUDE.md` and `AGENTS.md` based on `apm.yml`. The uv config applies a 14-day `exclude-newer` lag to dependency resolution.

When intentionally modifying `.apm/` source files, refresh the checksum lock file:

```bash
python3 scripts/verify_apm_checksums.py update
python3 scripts/verify_apm_checksums.py verify
```

## Using in other projects

Bring in the compiled `CLAUDE.md` / `AGENTS.md` as **committed real files**, not as a submodule or symlink. Submodules are stored only as commit pointers, so a fresh `git clone` (e.g. a Claude Code on the web session) leaves them empty; a symlinked `CLAUDE.md` becomes a broken link and loads nothing silently. The approach below lands the instructions as real files that are part of the clone.

### 1. Add a sync workflow

Copy the sync workflow from [`docs/runbooks/consumer-instruction-sync.md`](./docs/runbooks/consumer-instruction-sync.md) into your project. It fetches compiled instructions from a pinned tagged release, verifies each file against the published `SHA256SUMS`, and opens a PR that writes them as committed real files. Merge that PR through the code-owner gate; do not auto-merge.

### 2. Add project-specific rules

If your project has its own delta, sync the master to a vendored path and import it in your own `CLAUDE.md`, then write only the project-specific delta below:

```markdown
@.agents/claude-md-master/CLAUDE.md

## Project-specific rules
- (only the delta for this project)
```

The sync only overwrites the vendored file, so your own `CLAUDE.md` is not clobbered.

### 3. Pull updates

Bump the pinned release tag in the sync workflow in a reviewed PR. The scheduled run then opens an update PR, which you merge through the code-owner gate.

### Tool-specific notes

- **Codex or other tools that read `AGENTS.md`**: the same sync lands `AGENTS.md` alongside `CLAUDE.md` as a committed real file; no extra steps needed.

- **Devin** can use skills that APM expands to `.agents/skills/`. When you need hooks parity, bring in `.devin/hooks.v1.json` alongside the repo instructions. See [`docs/standards/devin-apm-compatibility.md`](./docs/standards/devin-apm-compatibility.md).

- **context7 MCP** is declared in `apm.yml` (`dependencies.mcp`) as a retrieval accelerator for primary-source documentation. This master only declares it; consumers wire it into their own clients via `apm install --mcp context7`. See [`docs/runbooks/context7-mcp.md`](./docs/runbooks/context7-mcp.md).

## Versioning

The universal text (`.apm/instructions/master.instructions.md` and the compiled `CLAUDE.md` / `AGENTS.md`) is versioned with semantic versioning. `apm.yml: version` is the single source of truth. "Compatibility" here is behavioral, for downstream consumers, not a programmatic API:

- **MAJOR** - breaks backward compatibility: removing, reversing, or weakening an existing rule; adding a new prohibition or mandatory obligation; or breaking a stable reference (renumbering principles, renaming a keyed section anchor, changing a term's meaning).
- **MINOR** - a backward-compatible addition or clarification (a new rule, principle, section, or example) that leaves prior-compliant behavior compliant.
- **PATCH** - a non-normative surface change (typo, formatting, link fix, translation, or a reword that preserves the rule's meaning).

Bump procedure for a PR that touches the universal text:

1. Declare the severity with exactly one `semver:major` / `semver:minor` / `semver:patch` label.
2. Bump `apm.yml: version` to match the declared component. A CI drift gate fails the PR if the universal text and `apm.yml: version` do not change together, or if the bump does not match the label.
3. On merge, a `v{version}` tag is created automatically and feeds the release publish flow; downstream consumers pin that tag (see [Using in other projects](#using-in-other-projects)).

Full decision record: [`docs/prd/semantic-versioning-universal-text.md`](./docs/prd/semantic-versioning-universal-text.md).

## Change policy

- All edits land via PR. Run a retrospective after merge (Principle 3).
- Keep only **rules that apply to every project** here. Project-specific rules belong in each project's own `CLAUDE.md`.
- Prefer deletion over addition (Principle 4).
- New or changed Python scripts under `scripts/` called by workflows must satisfy the [workflow script quality standard](./docs/standards/workflow-script-quality.md).
- PRs touching `.apm/instructions/**`, `CLAUDE.md`, or `AGENTS.md` must pass the [downstream instruction review checklist](./docs/runbooks/downstream-instruction-review-checklist.md) (a security-focused review applied after all deterministic gates are green).
- Full doc index organized by lane (`prd/`, `standards/`, `runbooks/`, `archive/`) in [`docs/INDEX.md`](./docs/INDEX.md).
