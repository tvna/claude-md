# claude-md

[English](./README.md) | 日本語 | [简体中文](./README.zh.md)

個人用に調整したエージェント指示のマスターリポジトリです。[`microsoft/apm`](https://github.com/microsoft/apm) で [`CLAUDE.md`](./CLAUDE.md) と [`AGENTS.md`](./AGENTS.md) にコンパイルし、他のプロジェクトから参照して使います。

## 目的

- AI コーディングエージェントに渡す原則を一箇所に集約し、どのプロジェクトでも一貫した振る舞いにする。
- ここには **どのプロジェクトでも成り立つ、個人レベルの普遍的なガイドライン** だけを置き、プロジェクト固有のルールは置かない。
- APM を信頼できる生成ハーネスとして使う。`.apm/instructions/` を編集し、`CLAUDE.md` と `AGENTS.md` をコンパイルする。
- 各プロジェクトのローカルなエージェント指示は、このマスターを参照し、差分だけを追加する。

## 6 つの原則

| # | 原則 | レイヤー | 要旨 |
|---|------|----------|------|
| 1 | Define the Goal with Plan Mode First | ゴールとプラン構造 | 3 ステップ以上の作業や設計判断を含む作業は plan mode から始める。 |
| 2 | Bound the Unknown Before Coding | 実装前の認識整理 | 仮定を列挙し、曖昧さを表に出し、検証するか質問する。曖昧な入力には問い、証拠には修正で応じる。 |
| 3 | Use Git Ecosystem Effectively | デリバリーハーネス | スケールさせる前に、hooks、CI/CD、宣言的依存管理などのハーネスを整える。 |
| 4 | Simplicity, Bounded by Safety | 安全境界 | 要求を満たす最小限のコードにする。ただし安全性を犠牲にしない。 |
| 5 | Accelerate Scale with Quality | 変更スコープと役割分担 | 必要な箇所だけ触り、実装・検証・探索を別エージェントに分ける。 |
| 6 | Be a Force Multiplier | 引き渡しと伝達 | "LGTM" で終わらせず、トレードオフを明示して他者が判断を追えるようにする。 |

コンパイル後の全文は [`CLAUDE.md`](./CLAUDE.md) または [`AGENTS.md`](./AGENTS.md) を参照してください。

## ビルド

ロックされた uv 環境を同期してから、ローカル指示をコンパイルします。

```bash
uv sync --locked
uv run --with "apm-cli==0.12.1" apm compile
```

APM は `.apm/instructions/*.instructions.md` を読み、`apm.yml` に基づいて `CLAUDE.md` と `AGENTS.md` の両方を書き出します。uv 設定では、依存関係解決に 14 日間の `exclude-newer` 遅延を適用しています。

## 別プロジェクトから使う

### 1. サブモジュールとして取り込む

```bash
# 親プロジェクトのルートで実行
git submodule add https://github.com/tvna/claude-md .claude-md-master
ln -s .claude-md-master/CLAUDE.md CLAUDE.md
```

Codex など `AGENTS.md` を読むツール向けには、次も追加します。

```bash
ln -s .claude-md-master/AGENTS.md AGENTS.md
```

### 2. プロジェクト固有ルールを追加する

親プロジェクト側でローカルなプロジェクト指示ファイルを作成し、先頭でこのマスターを読み込んでから、プロジェクト固有の差分だけを書きます。

```markdown
@.claude-md-master/CLAUDE.md

## Project-specific rules
- (only the delta for this project)
```

### 3. 更新を取り込む

```bash
git submodule update --remote .claude-md-master
```

## 変更ポリシー

- すべての編集は PR 経由で取り込む。マージ後は retrospective を実施する（Principle 3）。
- ここに置くのは **すべてのプロジェクトに当てはまるルール** だけにする。プロジェクト固有のルールは各プロジェクト自身の `CLAUDE.md` に置く。
- 追加より削除を優先する（Principle 4）。
