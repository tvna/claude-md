# macOS Rescue Pinned uv Design

## 関連 issue

- https://github.com/tvna/claude-md/issues/1745

## 背景

このリポジトリには、Claude/Codex の web 版と devcontainer が使えない、または devcontainer が破損した場合のレスキュー環境として、サンドボックスなしの macOS ホスト環境がある。この macOS 環境には、VS Code workspace、Claude Desktop、Codex Desktop の3つの入口がある。macOS ホストでは Homebrew などで管理された `uv` がリポジトリの `[tool.uv].required-version` から先行して、`uv run` や `uv sync` が失敗することがある。

既存実装では、`pyproject.toml` の `[tool.uv].required-version` を単一ソースとして、`scripts/setup_pinned_uv.sh` が pinned `uv` / `uvx` を `~/.uv-pins/claude-md` に配置する。`scripts/session_uv_local_pin.sh` は Claude/Codex の `SessionStart` に配線され、ローカルホストの `uv` が欠落または drift している場合に pinned prefix をセッション PATH へ追加する。`claude-md.code-workspace` も統合ターミナルの PATH 先頭に同じ prefix を置く。

## ゴール

既存の `~/.uv-pins/claude-md` 方式を macOS レスキュー環境の恒久運用として確定し、VS Code workspace、Claude Desktop、Codex Desktop の各入口で `apm compile` などの実行導線が pinned `uv` に依存することを文書とテストで固定する。

## 非ゴール

- full third-environment subsystem として macOS レスキュー環境全体を再設計しない。
- `uv` のインストール元や pin 管理の単一ソースを変更しない。
- Homebrew などホストの package-managed `uv` を変更しない。
- ネットワークを伴う実インストールを CI の必須検証にしない。

## 設計

### 運用モデル

macOS レスキュー環境では、リポジトリ内の `uv` 実行は host `uv` ではなく `~/.uv-pins/claude-md/uv` を優先する。prefix は version-agnostic のまま維持し、pin が更新された場合は `scripts/setup_pinned_uv.sh` が同じ prefix を self-heal する。

入口ごとの責務は分ける。VS Code workspace は `claude-md.code-workspace` の integrated terminal PATH と `folderOpen` task で pinned prefix を優先する。Claude Desktop と Codex Desktop は agent hook config の `SessionStart` から `scripts/session_uv_local_pin.sh` を実行し、ホスト `uv` が欠落または drift している場合に pinned prefix をセッション PATH へ永続化する。

`apm compile` の正式な導線は `uv run --with "apm-cli==0.12.1" apm compile` とし、この `uv` は workspace 統合ターミナルまたは SessionStart hook によって pinned prefix から解決されるものとする。これにより APM の実行時依存解決も ambient host `uv` ではなく repo pin に従う。

### 変更対象

- `docs/runbooks/host-uv-pin.md`
  - macOS no-sandbox rescue environment の正式運用であることを明記する。
  - 入口を VS Code workspace、Claude Desktop、Codex Desktop の3つに分けて説明する。
  - `~/.uv-pins/claude-md` を durable prefix として定義する。
  - `apm compile` が pinned `uv` 経由で実行される前提と確認手順を追加する。

- `claude-md.code-workspace`
  - 既存の `bootstrap pinned uv`、`apm: compile`、`uv: sync (locked)` タスクの意図を task detail で明確にする。
  - コマンド自体は既存の `uv run --with "apm-cli==0.12.1" apm compile` と `uv sync --locked` を維持する。

- テスト
  - workspace 設定を読むテストを追加または拡張し、`terminal.integrated.env.osx.PATH` が `~/.uv-pins/claude-md` を先頭に置くことを検証する。
  - `bootstrap pinned uv` が folderOpen task として `scripts/setup_pinned_uv.sh` を呼ぶことを検証する。
  - `apm: compile` task が `uv run --with "apm-cli==0.12.1" apm compile` を使うことを検証する。
  - Claude Desktop と Codex Desktop の `SessionStart` に `scripts/session_uv_local_pin.sh` が配線されていることを既存テストで固定または強化する。

## エラー処理

`scripts/session_uv_local_pin.sh` の既存方針を維持する。pin が読めない、ネットワーク不調で setup が失敗する、または prefix が書けない場合でも SessionStart は wedge しない。失敗は stderr に出し、後続の `preflight_uv_version` や明示的な operator verification で検出する。

この設計では fail-open の SessionStart と fail-loud の verification を分離する。レスキュー環境の起動性を優先しつつ、運用確定の証拠はテストと runbook に置く。

## 検証

実装後に次を実行する。

- `python3 -m pytest tests/test_session_uv_local_pin.py tests/test_claude_settings_config.py -q`
- `python3 -m pytest tests/test_gen_agent_hooks.py -q`
- `bash -n scripts/setup_pinned_uv.sh scripts/session_uv_local_pin.sh`
- `python3 scripts/uv_pin.py read pyproject.toml`

ネットワークを伴う `scripts/setup_pinned_uv.sh` の実インストールは、CI の必須条件にしない。operator が macOS ホスト上で実運用確認する場合は、`which uv` が `~/.uv-pins/claude-md/uv` を指し、`uv --version` が `python3 scripts/uv_pin.py read pyproject.toml` と一致することを確認する。

## 想定されるトレードオフ

この設計は macOS レスキュー環境の全体像を完全にはモデル化しない。その代わり、今回の主問題である pinned `uv` と APM 実行導線に絞り、既存のフック、workspace task、runbook、テストを最小変更で恒久運用へ引き上げる。
