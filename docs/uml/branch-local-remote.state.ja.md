# ローカルブランチ と リモートブランチ の状態遷移

[English](./branch-local-remote.state.md) | 日本語

> ステータス: 読み取り専用の UML 設計記録（レビュー用成果物）。起点となる Issue は
> #1627（エージェント処理のブランチギャップを状態遷移のレンズで分析する）。これが
> 交差するのは、セッションブランチのロック（#785, #1181, #1513）、空 push ゲート
> （#1130）、サーバ側ブランチ更新の deny（#893）、そしてスコープ外のリモート削除
> 経路（#31 Goal D）である。

本ドキュメントは、エージェントが 1 つのリモート実行セッション内で駆動するブランチ
ライフサイクルを、実際に乖離する 2 つの状態機械に分けてモデル化する: エフェメラルな
コンテナ内の **ローカル** 作業ブランチと、GitHub 上の **リモート** ブランチである。
ここで状態遷移図が適切なレンズなのは（フック単位のメッセージ順序は既存の
`survey-followup-timing.sequence.md` が扱っている）、欠陥クラスが *コンテナ境界を
またぐ状態の乖離* にあるからだ —— ブランチが取りうる状態、決定論的ゲートが守る遷移、
そしてゲートが一切ない遷移は何か。

- 証拠タグ: `[fact]` はツリー内で観測された事実（file:line を引用）、`[analysis]` は
  ギャップに対する判断。

## ゲートの位置

`[fact]` ローカルのライフサイクルは PreToolUse の Bash ゲート群と 1 つの SessionStart
レコーダで統治され、リモートのライフサイクルは `mcp__github__*` の PreToolUse ゲートと
1 つの PostToolUse フォローアップで統治される。いずれも code-owner マージゲートの背後の
`scripts/` 配下にあり、`.claude/settings.json` で配線されている。

| 守る遷移 | ゲート | フェーズ |
|---|---|---|
| 許可された push 先を記録 | `check_session_branch.py:17`（`.git/CLAUDE_SESSION_BRANCH` へ追記） | SessionStart |
| 非セッションブランチへの commit | `preflight_commit_session_branch.py` | PreToolUse `git commit` |
| 非セッションブランチへの push | `preflight_push_session_branch.py` | PreToolUse `git push` |
| base に後れたブランチの push | `preflight_branch_base.py:45-58`, `preflight_push_base.py` | PreToolUse `git push` |
| 新規分のない push（HEAD == base tip） | `preflight_push_nonempty.py:40` | PreToolUse `git push` |
| ローカル prek なしの push | `preflight_push_prek.py` | PreToolUse `git push` |
| 陳腐化した main 上でのリモートブランチ作成 | `preflight_main_freshness.py` | PreToolUse `mcp__github__create_branch` |
| サーバ側ブランチ更新（マージコミット） | `gate_update_pr_branch.py:4-9`（deny） | PreToolUse `mcp__github__update_pull_request_branch` |
| 設定変更マージ後のフォローアップ提示 | `post_merge_new_session_prompt.py` | PostToolUse `mcp__github__merge_pull_request` |

`[analysis]` 許可ブランチの述語は連言である —— 記録された集合のメンバーであり、かつ
保護ブランチでないこと（`_session_branches.py:84-87`）。だが空または読めない集合は
全ゲートで fail-open として扱われるため、記録されていないセッションは、サーバ側の
ブランチ保護と CI がバックストップとして働くまで無拘束になる。

## ローカルブランチ状態機械

```mermaid
stateDiagram-v2
    [*] --> ContainerCloned: container start (fresh clone)
    ContainerCloned --> Recorded: SessionStart records branch (remote env)
    ContainerCloned --> Unrecorded: SessionStart fail-open or non-remote
    Recorded --> WorkingTree
    Unrecorded --> WorkingTree
    WorkingTree --> WorkingTree: edit files
    WorkingTree --> Committed: git commit allowed (branch authorized)
    WorkingTree --> WorkingTree: git commit denied (branch not authorized)
    Committed --> WorkingTree: more edits
    Committed --> Pushed: git push allowed (base-fresh AND non-empty AND session-locked AND prek)
    Committed --> BehindBase: git push denied (HEAD missing origin/main)
    BehindBase --> WorkingTree: rebase onto origin/main
    Committed --> EmptyRejected: git push denied (HEAD equals base tip)
    EmptyRejected --> WorkingTree: inspect git log, add real work
    Pushed --> WorkingTree: continue session
    Committed --> Lost: container reclaimed (unpushed work)
    WorkingTree --> Lost: container reclaimed (uncommitted work)
    Pushed --> [*]
    Lost --> [*]
```

## リモートブランチ状態機械

```mermaid
stateDiagram-v2
    [*] --> Absent
    Absent --> Live: first push or create_branch (main-freshness gate)
    Live --> Live: fast-forward push
    Live --> Diverged: partner session advanced the remote (paired work)
    Diverged --> Live: local rebase then push (no client gate detects this early)
    Live --> PROpen: create_pull_request (Family A gates)
    PROpen --> PROpen: update_pull_request_branch DENIED (server-side merge)
    PROpen --> CIRunning: checks dispatched
    CIRunning --> CIGreen
    CIRunning --> CIRed
    CIRed --> Live: push fix
    CIGreen --> Merged: merge_pull_request
    Merged --> MergedFollowup: post_merge prompt (session-affecting files)
    Merged --> StaleRemote: branch left on remote
    StaleRemote --> Surveyed: branch_cleanup read-only survey
    Surveyed --> StaleRemote: no DELETE path (#31 Goal D)
    Merged --> [*]
    MergedFollowup --> [*]
```

## ギャップ分析

| # | ギャップ `[analysis]` | 証拠 `[fact]`（file:line） | 追跡 |
|---|---|---|---|
| 1 | 未記録セッションの fail-open: `.git/CLAUDE_SESSION_BRANCH` が空または読めないと許可集合は空になり、各セッションブランチゲートは任意のブランチへの commit/push を許してしまう —— ロックが効くのは SessionStart が実際にブランチを記録した後だけである。 | `_session_branches.py:43`, `:84-87`; fail-open は `preflight_commit_session_branch.py:27` と `preflight_push_session_branch.py:18` に記載。 | #785, #1513, #1181 |
| 2 | HEAD をリモートのセッションブランチ tip と突き合わせるローカルゲートがない。push ゲートは HEAD が `origin/main` を含むこと、および HEAD が base tip より進んでいることしか主張しない —— 相方セッション（ペア作業の codex/claude）が同じリモートブランチを進めると non-fast-forward の乖離が生じ、誘導付きの rebase ではなく素の push reject としてしか表面化しない。 | `preflight_branch_base.py:45-58`; `preflight_push_nonempty.py:40`; ペア作業の根拠は `_session_branches.py` の docstring。 | #1513 |
| 3 | エフェメラルなコンテナの喪失: コンテナ回収前に push されなかったローカルコミットは回復不能。push ゲートは明示的な `git push` でのみ発火するため、アイドル回収前の push を促すものがない。 | 環境契約（非アクティブ後にコンテナ回収）; push ゲートはリテラルな `git push` を条件とする —— `preflight_push_nonempty.py:45-46`。 | #1627 |
| 4 | リモートのマージ済みブランチ削除は意図的にスコープ外: `branch_cleanup` は DELETE 経路を持たない読み取り専用サーベイのため、マージ済みリモートブランチは決定論的な削除ゲートなしに蓄積する。 | `branch_cleanup.py:5`, `:342-343`（DELETE 経路なし; #31 Goal D）。 | #31 |
| 5 | `update_pull_request_branch` は deny される（マージコミットを加えるサーバ側マージのため）が、その回復 —— ローカル rebase 後の push —— はランブックに記された運用/エージェント手順であり、自動化された遷移ではない。 | `gate_update_pr_branch.py:4-9`, 回復ランブックは `:40`。 | #893 |
| 6 | 多層防御の前提: すべてのローカル commit/push ゲートは内部エラーで fail-open するため、静かに壊れたゲートは守るべき操作を許す。correctness はサーバ側のブランチ保護と CI に全面的に依存する。 | fail-open は `preflight_push_session_branch.py:18`, `preflight_commit_session_branch.py:27`, `check_session_branch.py:23`。 | #785 |

## 推奨される方向（speculation）

- `[analysis]` ギャップ 1 + 6 は 2 層に現れる 1 つの欠陥: 許可集合の読み取りで
  「セッション未記録（正当に fail-open）」と「記録済み集合をセッション途中で喪失
  （fail-closed または再記録すべき）」を区別し、未記録セッションでも保護ブランチへは
  push できないという回帰テストを追加する。
- `[analysis]` ギャップ 2: push 前にリモートのセッションブランチ tip を観測し、
  non-fast-forward の乖離を素の 403/reject ではなく誘導付きの rebase プロンプトに
  変える —— `preflight_branch_base` が陳腐化した base を実行可能な deny に変えるのと
  同じ要領で。
- `[analysis]` ギャップ 4: 破壊的削除はセッション内エージェント経路から外したまま、
  蓄積は決定論的な post-merge クリーンアップジョブ（CI）で閉じる —— サーベイが既に
  前提としているのと同じバックストップ型。エージェントの記憶には委ねない。

## スコープ注記

`[fact]` ローカルゲートは authoritative ではなく advisory + バックストップである:
各ゲートは fail-open し、真のガードとして CI とサーバ側ブランチ保護を名指しする
（`preflight_push_session_branch.py:18`）。`[analysis]` よってここでモデル化した
ローカル/リモートの乖離は correctness の穴ではなく、エージェント/オペレータの摩擦
クラス —— 欠落した誘導遷移 —— である: サーバ側ルールは依然として不正な push を
reject する。`finishing-a-development-branch` スキル（advisory, CLAUDE.md 第 3 節）は
ブランチの仕上げ方を形作るが、これらの遷移に強制力は加えない。
