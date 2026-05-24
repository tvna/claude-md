# claude-md

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
| 2 | Bound the Unknown Before Coding | 编码前的认知整理 | 列出假设，暴露歧义，验证或提问；模糊输入需要澄清，证据则需要修复。 |
| 3 | Use Git Ecosystem Effectively | 交付工具链 | 在扩大规模之前，先建立 hooks、CI/CD、声明式依赖管理等工具链。 |
| 4 | Simplicity, Bounded by Safety | 安全边界 | 用满足需求的最少代码解决问题，但绝不牺牲安全性。 |
| 5 | Accelerate Scale with Quality | 变更范围与角色拆分 | 只改必须修改的地方；将实现、验证和探索拆给不同代理。 |
| 6 | Be a Force Multiplier | 交接与沟通 | 不满足于 "LGTM"；明确说明权衡，让他人能跟上判断过程。 |

完整编译结果请参阅 [`CLAUDE.md`](./CLAUDE.md) 或 [`AGENTS.md`](./AGENTS.md)。

## 构建

先同步锁定的 uv 环境，再编译本地指令：

```bash
uv sync --locked
uv run --with "apm-cli==0.12.1" apm compile
```

APM 会读取 `.apm/instructions/*.instructions.md`，并根据 `apm.yml` 写出 `CLAUDE.md` 和 `AGENTS.md`。uv 配置对依赖解析应用了 14 天的 `exclude-newer` 延迟。

## 在其他项目中使用

### 1. 作为 submodule 引入

```bash
# 在父项目根目录执行
git submodule add https://github.com/tvna/claude-md .claude-md-master
ln -s .claude-md-master/CLAUDE.md CLAUDE.md
```

对于 Codex 或其他读取 `AGENTS.md` 的工具，再添加：

```bash
ln -s .claude-md-master/AGENTS.md AGENTS.md
```

### 2. 添加项目专属规则

在父项目中创建本地项目指令文件，在开头导入这个主仓库，然后只写项目专属的差异部分。

```markdown
@.claude-md-master/CLAUDE.md

## Project-specific rules
- (only the delta for this project)
```

### 3. 拉取更新

```bash
git submodule update --remote .claude-md-master
```

## 变更策略

- 所有编辑都通过 PR 合入。合并后运行 retrospective（Principle 3）。
- 这里只放 **适用于每个项目的规则**。项目专属规则应放在各项目自己的 `CLAUDE.md` 中。
- 优先删减文字，而不是增加文字（Principle 4）。
