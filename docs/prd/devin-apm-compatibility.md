# Devin APM Compatibility Design

Tracking issue: [#982](https://github.com/tvna/claude-md/issues/982)

## 目的

Devin を正式な利用対象に加える。ただし、共有 skills とコンパイル済み指示の SoT は APM のままにし、Devin 固有の差分は互換アダプタとして小さく保つ。

## 事実

- Devin は repository skills を `.agents/skills/<skill-name>/SKILL.md` から検出する。
- このリポジトリは pinned APM dependency から Superpowers skills を `.agents/skills` と `.claude/skills` に展開している。
- `apm.yml` の既存 target は `claude` と `codex` で、APM CLI の公開 target には現時点で `devin` がない。
- Claude と Codex の hooks は `.claude/settings.json` と `.codex/hooks.json` に分かれており、既存テストで重要ゲートの存在を固定している。

## 仮定

- Devin 側の hooks は Claude Code hooks と互換の JSON 形状で扱える。
- Devin は `.claude/settings.json` を読める場合があるが、正式導入では `.devin/hooks.v1.json` を置いたほうが利用者に意図が伝わりやすい。
- APM が将来 native `devin` target を追加した場合、この設計の `.devin/hooks.v1.json` は APM 出力へ移行できる。

## アプローチ

推奨案は APM-first hybrid。

1. Skills は APM が展開する `.agents/skills` を Devin の primary surface とする。
2. Hooks は `.devin/hooks.v1.json` を新設し、Claude/Codex と同じ安全ゲートを明示する。
3. Tests は `.devin/hooks.v1.json` の JSON 妥当性、repo script 参照、SessionStart/PreToolUse/PostToolUse の主要 parity を固定する。
4. Docs は README と docs index から Devin 対応の読み筋を提供する。

## 代替案

### A. `.claude/settings.json` への依存のみ

最小変更だが、Devin 正式導入のシグナルが弱く、将来 Devin 側の互換読み込みが変わったときに壊れやすい。

### B. APM native target が出るまで待つ

SoT としては美しいが、今すぐ Devin を導入する要求を満たせない。

### C. APM-first hybrid

APM 管理の skills と明示的な Devin hooks を分ける。現時点の最小安全実装で、将来 APM target が増えた場合にも移行しやすい。

## 実装境界

今回追加するもの:

- `.devin/hooks.v1.json`
- `tests/test_devin_hooks_config.py`
- README の Devin 利用メモ
- `docs/INDEX.md` の本設計書エントリ

今回追加しないもの:

- `.apm/instructions/master.instructions.md` の本文変更
- `CLAUDE.md` / `AGENTS.md` の再生成
- Devin 専用の独自 skill fork
- APM CLI 自体への target 追加

## 検証

- `python3 -m pytest tests/test_devin_hooks_config.py -q`
- `python3 -m pytest tests/test_superpowers_apm_install.py tests/test_claude_settings_config.py tests/test_codex_hooks_config.py -q`
- `python3 scripts/scan_docs_inventory.py verify`
- `python3 scripts/scan_markdown_links.py verify`

APM CLI 実行はローカル `uv` の required-version mismatch が解消している場合にだけ実施する。mismatch が残る場合は、PR 本文でその事実を明記する。
