# claude-md

[![codecov](https://codecov.io/gh/tvna/claude-md/branch/main/graph/badge.svg)](https://codecov.io/gh/tvna/claude-md)

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
| 2 | Bound Inputs and Unknowns Before Coding | 実装前の認識整理 | 外部テキストを未信頼データとして扱い、事実、仮定、曖昧さを分けてから実装する。 |
| 3 | Use Git Ecosystem Effectively | デリバリーハーネス | スケールさせる前に、hooks、CI/CD、宣言的依存管理などのハーネスを整える。 |
| 4 | Simplicity, Bounded by Safety | 安全境界 | 要求を満たす最小限にする。ただし安全性、ツール範囲、秘密情報の扱いを犠牲にしない。 |
| 5 | Accelerate Scale with Quality | 品質がスケールを可能にする | 品質こそが出力のスケールを可能にし、両者は比例して伸びる。変更面は狭く保ち、品質が劣化したら止めて再計画する。 |
| 6 | Be a Force Multiplier | 引き渡しと伝達 | "LGTM" で終わらせず、トレードオフを明示して他者が判断を追えるようにする。 |

コンパイル後の全文は [`CLAUDE.md`](./CLAUDE.md) または [`AGENTS.md`](./AGENTS.md) を参照してください。

## ビルド

ロックされた uv 環境を同期してから、ローカル指示をコンパイルします。

```bash
uv sync --locked
uv run --with "apm-cli==0.12.1" apm compile
```

APM は `.apm/instructions/*.instructions.md` を読み、`apm.yml` に基づいて `CLAUDE.md` と `AGENTS.md` の両方を書き出します。uv 設定では、依存関係解決に 14 日間の `exclude-newer` 遅延を適用しています。

意図的に `.apm/` のソースファイルを変更したときは、チェックサムのロックファイルを更新します。

```bash
python3 scripts/verify_apm_checksums.py update
python3 scripts/verify_apm_checksums.py verify
```

## 別プロジェクトから使う

コンパイル済みの `CLAUDE.md` / `AGENTS.md` は **コミット済みの実ファイル** として取り込みます（submodule でも symlink でもありません）。submodule はコミットポインタとしてしか保存されないため、fresh な `git clone`（Claude Code on the web のセッションなど）では空になり、symlink した `CLAUDE.md` は壊れたリンクとなって何もサイレントに読み込まれません。以下の方式は、クローンの一部となる実ファイルとして指示を配置します。

### 1. 同期ワークフローを追加する

[`docs/runbooks/consumer-instruction-sync.md`](./docs/runbooks/consumer-instruction-sync.md) の同期ワークフローを自分のプロジェクトにコピーします。固定したタグ付きリリースからコンパイル済み指示を取得し、公開された `SHA256SUMS` で各ファイルを検証し、コミット済み実ファイルとして書き込む PR を開きます。その PR は code-owner ゲートを通してマージし、自動マージはしないでください。

### 2. プロジェクト固有ルールを追加する

プロジェクト固有の差分がある場合は、マスターを vendored パスへ同期し、自分の `CLAUDE.md` から import して、その下にプロジェクト固有の差分だけを書きます。

```markdown
@.agents/claude-md-master/CLAUDE.md

## Project-specific rules
- (only the delta for this project)
```

同期は vendored ファイルだけを上書きするので、自分の `CLAUDE.md` が壊されることはありません。

### 3. 更新を取り込む

レビュー済みの PR で同期ワークフローの固定リリースタグを更新します。スケジュール実行が更新 PR を開くので、code-owner ゲートを通してマージします。

### ツール別の補足

- **Codex など `AGENTS.md` を読むツール** 向けにも、同じ同期で `AGENTS.md` が `CLAUDE.md` と並ぶコミット済み実ファイルとして配置されます。別の手順は不要です。

- **Devin** は APM が展開した `.agents/skills/` の skills を利用できます。hooks の parity が必要な場合は、リポジトリ指示と一緒に `.devin/hooks.v1.json` を取り込んでください。詳細は [`docs/standards/devin-apm-compatibility.md`](./docs/standards/devin-apm-compatibility.md) を参照してください。

- **context7 MCP** は一次情報ドキュメントの取得を高速化するため `apm.yml`（`dependencies.mcp`）で宣言しています。本マスターは宣言のみで、利用側が `apm install --mcp context7` で各自のクライアントに配線します。詳細は [`docs/runbooks/context7-mcp.md`](./docs/runbooks/context7-mcp.md) を参照してください。

## 変更ポリシー

- すべての編集は PR 経由で取り込む。マージ後は retrospective を実施する（Principle 3）。
- ここに置くのは **すべてのプロジェクトに当てはまるルール** だけにする。プロジェクト固有のルールは各プロジェクト自身の `CLAUDE.md` に置く。
- 追加より削除を優先する（Principle 4）。
- 新規または変更された、`scripts/` 配下の workflow から呼ばれる Python スクリプトは [workflow script quality standard](./docs/standards/workflow-script-quality.md) を満たすこと。
- `.apm/instructions/**`、`CLAUDE.md`、`AGENTS.md` を編集する PR は [downstream instruction review checklist](./docs/runbooks/downstream-instruction-review-checklist.md) を通すこと（決定的ゲートが green になった後に適用するセキュリティ重視のレビュー）。
- レーン別（`prd/`、`standards/`、`runbooks/`、`archive/`）の文書地図全体は [`docs/INDEX.md`](./docs/INDEX.md) を参照。
