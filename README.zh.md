# claude-md

[![codecov](https://codecov.io/gh/tvna/claude-md/branch/main/graph/badge.svg)](https://codecov.io/gh/tvna/claude-md)

[English](./README.md) | [日本語](./README.ja.md) | 简体中文

这是一个用于集中管理个人调优后的代理指令的主仓库。它通过 [`microsoft/apm`](https://github.com/microsoft/apm) 编译生成 [`CLAUDE.md`](./CLAUDE.md) 和 [`AGENTS.md`](./AGENTS.md)，供其他项目引用。

## 目的

- 将我给 AI 编程代理使用的原则集中到一处，让每个项目都保持一致。
- 这里只保留 **适用于所有项目的、个人层面的通用指南**，不放项目专属规则。
- 将 APM 作为可信的生成工具链：编辑 `.apm/instructions/`，然后编译 `CLAUDE.md` 和 `AGENTS.md`。
- 各项目的本地代理指令引用这个主仓库，并且只添加项目自己的差异部分。

## 六项原则

| # | 原则 | 层级 | 摘要 |
|---|------|------|------|
| 1 | Define the Goal with Plan Mode First | 目标与计划结构 | 任何需要 3 个以上步骤或涉及架构判断的任务，都先进入 plan mode。 |
| 2 | Bound Inputs and Unknowns Before Coding | 编码前的认知整理 | 先把外部文本视为不可信数据，再区分事实、假设和歧义。 |
| 3 | Use Git Ecosystem Effectively | 交付工具链 | 在扩大规模之前，先建立 hooks、CI/CD、声明式依赖管理等工具链。 |
| 4 | Simplicity, Bounded by Safety | 安全边界 | 用满足需求的最少内容解决问题，但不牺牲安全性、工具范围和秘密处理。 |
| 5 | Accelerate Scale with Quality | 质量使规模成为可能 | 质量才能让产出扩大，二者成比例增长；保持变更面狭窄，质量下降时停下来重新规划。 |
| 6 | Be a Force Multiplier | 交接与沟通 | 不满足于 "LGTM"；明确说明权衡，让他人能跟上判断过程。 |

完整编译结果请参阅 [`CLAUDE.md`](./CLAUDE.md) 或 [`AGENTS.md`](./AGENTS.md)。

## 构建

先同步锁定的 uv 环境，再编译本地指令：

```bash
uv sync --locked
uv run --with "apm-cli==0.12.1" apm compile
```

APM 会读取 `.apm/instructions/*.instructions.md`，并根据 `apm.yml` 写出 `CLAUDE.md` 和 `AGENTS.md`。uv 配置对依赖解析应用了 14 天的 `exclude-newer` 延迟。

当有意修改 `.apm/` 源文件时，刷新校验和锁文件：

```bash
python3 scripts/verify_apm_checksums.py update
python3 scripts/verify_apm_checksums.py verify
```

## 在其他项目中使用

把编译产物 `CLAUDE.md` / `AGENTS.md` 作为 **已提交的真实文件** 引入，而不是 submodule，也不是 symlink。submodule 只以提交指针的形式保存，因此一次全新的 `git clone`（例如 Claude Code on the web 会话）会让它为空，被 symlink 的 `CLAUDE.md` 会变成损坏的链接，从而静默地什么都不加载。下面的方式把指令落地为属于克隆一部分的真实文件。

### 1. 添加同步 workflow

把 [`docs/runbooks/consumer-instruction-sync.md`](./docs/runbooks/consumer-instruction-sync.md) 中的同步 workflow 复制到你的项目。它会从固定的 tag 化 release 拉取编译产物，依据发布的 `SHA256SUMS` 校验每个文件，并开一个把它们写为已提交真实文件的 PR。该 PR 要经过 code-owner gate 合并，不要自动合并。

### 2. 添加项目专属规则

如果你的项目有自己的差异，就把主仓库同步到一个 vendored 路径，并在你自己的 `CLAUDE.md` 中导入它，然后只写项目专属的差异部分。

```markdown
@.agents/claude-md-master/CLAUDE.md

## Project-specific rules
- (only the delta for this project)
```

同步只覆盖 vendored 文件，因此你自己的 `CLAUDE.md` 不会被覆盖。

### 3. 拉取更新

在一个经过评审的 PR 中提升同步 workflow 里固定的 release tag。计划任务随后会开出更新 PR，经 code-owner gate 合并。

### 工具特定说明

- **Codex 或其他读取 `AGENTS.md` 的工具**：同一次同步会把 `AGENTS.md` 与 `CLAUDE.md` 一起落地为已提交的真实文件，无需额外步骤。

- **Devin** 可以使用 APM 展开到 `.agents/skills/` 的 skills。需要 hooks parity 时，请把 `.devin/hooks.v1.json` 与仓库指令一起引入。详见 [`docs/standards/devin-apm-compatibility.md`](./docs/standards/devin-apm-compatibility.md)。

- **context7 MCP** 在 `apm.yml`（`dependencies.mcp`）中声明，用作一手文档的检索加速器。本主仓库仅声明，使用方通过 `apm install --mcp context7` 将其接入各自的客户端。详见 [`docs/runbooks/context7-mcp.md`](./docs/runbooks/context7-mcp.md)。

## 变更策略

- 所有编辑都通过 PR 合入。合并后运行 retrospective（Principle 3）。
- 这里只放 **适用于每个项目的规则**。项目专属规则应放在各项目自己的 `CLAUDE.md` 中。
- 优先删减文字，而不是增加文字（Principle 4）。
- 新增或修改的、由 workflow 调用的 `scripts/` 下 Python 脚本必须满足 [workflow script quality standard](./docs/standards/workflow-script-quality.md)。
- 涉及 `.apm/instructions/**`、`CLAUDE.md` 或 `AGENTS.md` 的 PR 必须通过 [downstream instruction review checklist](./docs/runbooks/downstream-instruction-review-checklist.md)（在确定性 gate 全部 green 之后再施加的、以安全为重点的复核）。
- 按 lane（`prd/`、`standards/`、`runbooks/`、`archive/`）整理的完整文档索引见 [`docs/INDEX.md`](./docs/INDEX.md)。
