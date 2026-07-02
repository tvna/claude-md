# claude-md

[![codecov](https://codecov.io/gh/tvna/claude-md/branch/main/graph/badge.svg)](https://codecov.io/gh/tvna/claude-md)

[English](./README.md) | [日本語](./README.ja.md) | 简体中文 | [한국어](./README.ko.md)

这是一个用于集中管理个人调优后的代理指令的主仓库。它通过 [`microsoft/apm`](https://github.com/microsoft/apm) 编译生成 [`CLAUDE.md`](./CLAUDE.md)、[`AGENTS.md`](./AGENTS.md) 和 [`GEMINI.md`](./GEMINI.md)，供其他项目引用。`apm compile --target all` 会为 apm-cli 支持的每一种工具生成编译产物（Claude、Codex、Gemini CLI，以及读取 Copilot 或 `AGENTS.md` 的各类客户端）；具体生成哪些文件取决于各工具自己的编译格式（参见[工具特定说明](#工具特定说明)）。

## 目的

- 将我给 AI 编程代理使用的原则集中到一处，让每个项目都保持一致。
- 这里只保留 **适用于所有项目的、个人层面的通用指南**，不放项目专属规则。
- 将 APM 作为可信的生成工具链：编辑 `.apm/instructions/`，然后编译 `CLAUDE.md`、`AGENTS.md` 和 `GEMINI.md`。
- 各项目的本地代理指令引用这个主仓库，并且只添加项目自己的差异部分。

## 六项原则

| # | 原则 | 层级 | 摘要 |
|---|------|------|------|
| 1 | Define the Goal with Plan Mode First | 目标与计划结构 | 任何需要 3 个以上步骤或涉及架构判断的任务，都先进入 plan mode。 |
| 2 | Bound Inputs and Unknowns Before Coding | 编码前的认知整理 | 先把外部文本视为不可信数据，再区分事实、假设和歧义。 |
| 3 | Use Git Ecosystem Effectively | 交付工具链 | 在扩大规模之前，先建立 hooks、CI/CD、声明式依赖管理工具链。 |
| 4 | Simplicity, Bounded by Safety | 安全边界 | 用满足需求的最少内容解决问题，但不牺牲安全性、工具范围和秘密处理。 |
| 5 | Accelerate Scale with Quality | 质量使规模成为可能 | 质量才能让产出扩大，二者成比例增长；保持变更面狭窄，质量下降时停下来重新规划。 |
| 6 | Be a Force Multiplier | 交接与沟通 | 不满足于 "LGTM"；明确说明权衡，让他人能跟上判断过程。 |

完整编译结果请参阅 [`CLAUDE.md`](./CLAUDE.md) 或 [`AGENTS.md`](./AGENTS.md)。

## 构建

先同步锁定的 uv 环境，再编译本地指令：

```bash
uv sync --locked
uv run --with "apm-cli==$(python3 scripts/flake_pin.py version --tool apm)" apm compile --target all
```

APM 会读取 `.apm/instructions/*.instructions.md`，写出 `CLAUDE.md`、`AGENTS.md` 和 `GEMINI.md`。`--target all` 会为 flake.nix 锁定版本的 apm-cli（`scripts/flake_pin.py version --tool apm`）支持的每一种工具编译（`copilot, claude, cursor, opencode, codex, gemini, windsurf`）；`apm.yml` 的 `target:` 字段保持更窄的范围（`claude`、`codex`），因为该字段同时决定了 `apm install` 式的 skill 部署范围，本仓库有意将其限制在实际使用的工具内。uv 配置对依赖解析应用了 14 天的 `exclude-newer` 延迟。

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

- **Codex、Cursor、OpenCode、Windsurf 或其他读取 `AGENTS.md` 的工具**：同一次同步会把 `AGENTS.md` 与 `CLAUDE.md` 一起落地为已提交的真实文件，无需额外步骤。这些工具没有各自专属的编译产物；在 apm-cli 的目标注册表中，`AGENTS.md` 本身就是它们的格式。

- **Gemini CLI**：与 `CLAUDE.md` / `AGENTS.md` 一起同步 `GEMINI.md`。它只是一行 import 语句（`@./AGENTS.md`），Gemini CLI 会解析该 import，因此其内容始终与 `AGENTS.md` 一致。

- **GitHub Copilot**：`apm compile --target all` 也可能生成 `.github/copilot-instructions.md`，但仅当存在一个真正 *全局*（未限定作用域）的 instruction primitive 时才会生成。本主仓库唯一的指令来源声明了 `applyTo: "**/*"`，apm-cli 的编译器将其视为“限定作用域”而非“全局”，因此目前不会生成该文件；原生读取 `AGENTS.md` 的 Copilot 客户端不受影响。

- **Devin** 可以使用 APM 展开到 `.agents/skills/` 的 skills。需要 hooks parity 时，请把 `.devin/hooks.v1.json` 与仓库指令一起引入。详见 [`docs/standards/devin-apm-compatibility.md`](./docs/standards/devin-apm-compatibility.md)。

- **context7 MCP** 在 `apm.yml`（`dependencies.mcp`）中声明，用作一手文档的检索加速器。本主仓库仅声明，使用方通过 `apm install --mcp context7` 将其接入各自的客户端。详见 [`docs/runbooks/context7-mcp.md`](./docs/runbooks/context7-mcp.md)。

## 版本管理

universal text（`.apm/instructions/master.instructions.md` 以及编译产物 `CLAUDE.md` / `AGENTS.md`）采用语义化版本管理。`apm.yml: version` 是唯一可信来源（single source of truth）。这里的“兼容性”指对使用方而言行为上的向后兼容，而非程序化 API：

- **MAJOR** - 破坏向后兼容的变更：删除、反转或弱化既有规则；新增禁止项或强制义务；或破坏稳定引用（重排原则编号、重命名被引用的章节锚点、改变术语含义）。
- **MINOR** - 向后兼容的新增或澄清（新规则、原则、章节或示例），使既有的合规行为仍然合规。
- **PATCH** - 非规范性的表层变更（错别字、排版、链接修复、翻译，或保持规则含义的改写）。

涉及 universal text 的 PR 的 bump 步骤：

1. 用且仅用一个 `semver:major` / `semver:minor` / `semver:patch` 标签声明严重程度。
2. 按声明的分量 bump `apm.yml: version`。如果 universal text 与 `apm.yml: version` 没有一起变更，或 bump 与标签不一致，CI 的 drift gate 会让 PR fail。
3. 合并时自动创建 `v{version}` tag 并进入 release 发布流程；使用方固定该 tag 来引用（参见[在其他项目中使用](#在其他项目中使用)）。

完整决策记录见 [`docs/prd/semantic-versioning-universal-text.md`](./docs/prd/semantic-versioning-universal-text.md)。

## 变更策略

- 所有编辑都通过 PR 合入。合并后运行 retrospective（Principle 3）。
- 这里只放 **适用于每个项目的规则**。项目专属规则应放在各项目自己的 `CLAUDE.md` 中。
- 优先删减文字，而不是增加文字（Principle 4）。
- 新增或修改的、由 workflow 调用的 `scripts/` 下 Python 脚本必须满足 [workflow script quality standard](./docs/standards/workflow-script-quality.md)。
- 涉及 `.apm/instructions/**`、`CLAUDE.md` 或 `AGENTS.md` 的 PR 必须通过 [downstream instruction review checklist](./docs/runbooks/downstream-instruction-review-checklist.md)（在确定性 gate 全部 green 之后再施加的、以安全为重点的复核）。
- 按 lane（`prd/`、`standards/`、`runbooks/`、`archive/`）整理的完整文档索引见 [`docs/INDEX.md`](./docs/INDEX.md)。
