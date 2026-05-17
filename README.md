# claude-md

個人用に最適化された [`CLAUDE.md`](./CLAUDE.md) のマスターリポジトリ。他プロジェクトから参照する前提で運用する。

## 目的

- Claude Code を使う際の行動原則を 1 か所に集約し、複数プロジェクト間で一貫性を保つ。
- プロジェクト固有のルールではなく、**作業者個人としての普遍的な指針**だけをここに置く。
- 個別プロジェクトの `CLAUDE.md` からはこのマスターを参照し、差分のみをローカルで定義する。

## 6 つの原則

| # | 原則 | 要旨 |
|---|------|------|
| 1 | Define the Goal with Plan Mode First | 3 ステップ以上の作業は必ず plan mode から入る |
| 2 | Think Before Coding | 仮定を明示し、不明点は実装前に解消する |
| 3 | Use Git Ecosystem Effectively | hooks / CI / 宣言的依存管理でハーネスを先に整える |
| 4 | Simplicity is Perfect | 要求された最小コードのみ。投機的な抽象化は禁止 |
| 5 | Accelerate Scale with Quality | 自分の散らかしのみ掃除、sub-agent と Skills を使い分ける |
| 6 | Be A Force Multiplier | "LGTM" で終わらせず、トレードオフを言語化する |

詳細は [`CLAUDE.md`](./CLAUDE.md) を参照。

## 他プロジェクトからの参照方法

### 1. シンボリックリンクで取り込む

```bash
# 親プロジェクトのルートで
git submodule add https://github.com/tvna/claude-md .claude-md-master
ln -s .claude-md-master/CLAUDE.md CLAUDE.md
```

### 2. プロジェクト固有ルールを足す場合

プロジェクト側で `CLAUDE.local.md` を作成し、マスターを `@import` する形で先頭に置く。

```markdown
@.claude-md-master/CLAUDE.md

## Project-specific rules
- (このプロジェクト固有の差分のみ)
```

### 3. 更新の取り込み

```bash
git submodule update --remote .claude-md-master
```

## 変更ポリシー

- 修正は PR 経由。マージ後にレトロスペクティブを行う (原則 3)。
- ここに書くのは **どのプロジェクトでも成り立つ普遍ルール** だけ。プロジェクト固有のものは個別 `CLAUDE.md` 側へ。
- 文言追加よりも削減を優先する (原則 4)。
