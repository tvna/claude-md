# claude-md

Master repository for personally tuned agent instructions, compiled with [`microsoft/apm`](https://github.com/microsoft/apm) into [`CLAUDE.md`](./CLAUDE.md) and [`AGENTS.md`](./AGENTS.md) for other projects.

## Purpose

- Centralize the principles I use with AI coding agents so that every project stays consistent.
- Keep only **universal, individual-level guidelines** here — never project-specific rules.
- Use APM as the source-of-truth harness: edit `.apm/instructions/`, then compile `CLAUDE.md` and `AGENTS.md`.
- Each project's local agent instructions reference this master and only add their own delta.

## The Six Principles

| # | Principle | Summary |
|---|-----------|---------|
| 1 | Define the Goal with Plan Mode First | Enter plan mode for any task that takes 3+ steps or touches architecture. |
| 2 | Think Before Coding | State assumptions, surface ambiguity, and ask before guessing. |
| 3 | Use Git Ecosystem Effectively | Build the harness — hooks, CI/CD, declarative deps — before you scale. |
| 4 | Simplicity, Bounded by Safety | Minimum code that solves the problem — never at the cost of safety. |
| 5 | Accelerate Scale with Quality | Touch only what you must; split implementation, verification, and exploration across separate agents. |
| 6 | Be a Force Multiplier | Don't settle for "LGTM" — make trade-offs explicit so others can follow the reasoning. |

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

## 日本語版（概要）

個人用に最適化されたエージェント指示のマスターリポジトリ。`microsoft/apm` で [`CLAUDE.md`](./CLAUDE.md) と [`AGENTS.md`](./AGENTS.md) にコンパイルし、他プロジェクトから参照する前提で運用する。ここに置くのは **どのプロジェクトでも成り立つ普遍ルール** のみで、プロジェクト固有の差分は個別のローカル指示ファイル側に書く。

| # | 原則 | 要旨 |
|---|------|------|
| 1 | Define the Goal with Plan Mode First | 3 ステップ以上の作業は必ず plan mode から入る |
| 2 | Think Before Coding | 仮定を明示し、不明点は実装前に解消する |
| 3 | Use Git Ecosystem Effectively | hooks / CI / 宣言的依存管理でハーネスを先に整える |
| 4 | Simplicity, Bounded by Safety | 要求された最小コードのみ。ただし安全装置は削らない |
| 5 | Accelerate Scale with Quality | 自分の散らかしのみ掃除、実装/検証/探索でエージェントを分ける |
| 6 | Be a Force Multiplier | "LGTM" で終わらせず、トレードオフを言語化する |

詳細は英語本文と [`CLAUDE.md`](./CLAUDE.md) を参照。
