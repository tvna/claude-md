# macOS Rescue Pinned uv Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** macOS レスキュー環境の `~/.uv-pins/claude-md` 運用を、VS Code workspace、Claude Desktop、Codex Desktop の3入口で文書とテストに固定する。

**Architecture:** 既存の `scripts/setup_pinned_uv.sh` と `scripts/session_uv_local_pin.sh` は変更しない。VS Code は `claude-md.code-workspace` の PATH/task 契約で pinned `uv` を優先し、Claude/Codex Desktop は `SessionStart` hook 契約で pinned prefix をセッション PATH に入れる。運用説明は `docs/runbooks/host-uv-pin.md` に集約する。

**Tech Stack:** Python pytest、JSON workspace config、Claude/Codex hook JSON、Markdown runbook、bash syntax verification。

---

## File Structure

- Create: `tests/test_vscode_workspace_uv_pin.py`
  - VS Code workspace の macOS pinned `uv` 契約を読む focused test。
- Modify: `claude-md.code-workspace`
  - `apm: compile` と `uv: sync (locked)` の task detail を追加し、pinned prefix 前提を人間にも読める状態にする。
- Modify: `tests/test_claude_settings_config.py`
  - Claude Desktop の `SessionStart` に `scripts/session_uv_local_pin.sh` があることを固定する。
- Modify: `tests/test_codex_hooks_config.py`
  - Codex Desktop の `SessionStart` に `scripts/session_uv_local_pin.sh` があることを固定する。
- Modify: `docs/runbooks/host-uv-pin.md`
  - macOS レスキュー環境の3入口、durable prefix、APM 実行導線、確認手順を明記する。
- Optional Modify: `docs/INDEX.md`
  - `host-uv-pin.md` の説明文が古い場合だけ、3入口と APM 導線を反映する。

### Task 1: VS Code Workspace Contract Test

**Files:**
- Create: `tests/test_vscode_workspace_uv_pin.py`
- Modify: none
- Test: `tests/test_vscode_workspace_uv_pin.py`

- [ ] **Step 1: Write the workspace contract tests**

Create `tests/test_vscode_workspace_uv_pin.py` with this complete content:

```python
"""Tests for the VS Code macOS pinned-uv workspace contract.

Refs #1745. The workspace is one of the three macOS rescue entrypoints:
VS Code integrated terminals must prefer ``~/.uv-pins/claude-md`` before any
ambient host uv, and the built-in APM task must run through ``uv`` so the repo
pin applies.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_preflight

ROOT = Path(__file__).resolve().parents[1]
WORKSPACE = ROOT / "claude-md.code-workspace"
PINNED_PREFIX = "${env:HOME}/.uv-pins/claude-md"


def _load_workspace() -> dict[str, object]:
    data = json.loads(WORKSPACE.read_text(encoding="utf-8"))
    assert isinstance(data, dict)
    return data


def _tasks_by_label(data: dict[str, object]) -> dict[str, dict[str, object]]:
    tasks_root = data["tasks"]
    assert isinstance(tasks_root, dict)
    tasks = tasks_root["tasks"]
    assert isinstance(tasks, list)
    out: dict[str, dict[str, object]] = {}
    for task in tasks:
        assert isinstance(task, dict)
        label = task["label"]
        assert isinstance(label, str)
        out[label] = task
    return out


def test_macos_terminal_path_prefers_repo_pinned_uv_prefix() -> None:
    data = _load_workspace()
    settings = data["settings"]
    assert isinstance(settings, dict)
    terminal_env = settings["terminal.integrated.env.osx"]
    assert isinstance(terminal_env, dict)
    path = terminal_env["PATH"]
    assert isinstance(path, str)
    assert path.startswith(f"{PINNED_PREFIX}:")


def test_bootstrap_pinned_uv_runs_on_folder_open() -> None:
    tasks = _tasks_by_label(_load_workspace())
    task = tasks["bootstrap pinned uv"]
    assert task["command"] == "${workspaceFolder}/scripts/setup_pinned_uv.sh"
    assert task["runOptions"] == {"runOn": "folderOpen"}
    detail = task["detail"]
    assert isinstance(detail, str)
    assert "~/.uv-pins/claude-md" in detail


def test_apm_compile_task_runs_through_pinned_uv_contract() -> None:
    tasks = _tasks_by_label(_load_workspace())
    task = tasks["apm: compile"]
    assert task["command"] == 'uv run --with "apm-cli==0.12.1" apm compile'
    detail = task["detail"]
    assert isinstance(detail, str)
    assert "pinned uv" in detail
    assert "~/.uv-pins/claude-md" in detail


def test_locked_sync_task_runs_through_pinned_uv_contract() -> None:
    tasks = _tasks_by_label(_load_workspace())
    task = tasks["uv: sync (locked)"]
    assert task["command"] == "uv sync --locked"
    detail = task["detail"]
    assert isinstance(detail, str)
    assert "pinned uv" in detail
    assert "~/.uv-pins/claude-md" in detail
```

- [ ] **Step 2: Run the new tests and confirm the intended failure**

Run:

```bash
python3 -m pytest tests/test_vscode_workspace_uv_pin.py -q
```

Expected: FAIL. The `apm: compile` and `uv: sync (locked)` tasks currently have no `detail`, so the new contract test should fail before implementation.

### Task 2: VS Code Workspace Task Details

**Files:**
- Modify: `claude-md.code-workspace`
- Test: `tests/test_vscode_workspace_uv_pin.py`

- [ ] **Step 1: Add task details**

In `claude-md.code-workspace`, update only the two existing task objects shown below.

Change the `apm: compile` task to:

```json
{
  "label": "apm: compile",
  "detail": "Compile instructions through the repo-pinned uv resolved from ~/.uv-pins/claude-md in macOS rescue terminals.",
  "type": "shell",
  "command": "uv run --with \"apm-cli==0.12.1\" apm compile",
  "problemMatcher": [],
  "presentation": {
    "reveal": "always",
    "panel": "dedicated"
  }
}
```

Change the `uv: sync (locked)` task to:

```json
{
  "label": "uv: sync (locked)",
  "detail": "Synchronize the locked project environment through the repo-pinned uv resolved from ~/.uv-pins/claude-md in macOS rescue terminals.",
  "type": "shell",
  "command": "uv sync --locked",
  "problemMatcher": [],
  "presentation": {
    "reveal": "always",
    "panel": "dedicated"
  }
}
```

- [ ] **Step 2: Run the workspace contract tests**

Run:

```bash
python3 -m pytest tests/test_vscode_workspace_uv_pin.py -q
```

Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_vscode_workspace_uv_pin.py claude-md.code-workspace
git commit -m "test(toolchain): lock vscode pinned uv workspace contract" -m "Refs #1745"
```

### Task 3: Desktop SessionStart Hook Contract Tests

**Files:**
- Modify: `tests/test_claude_settings_config.py`
- Modify: `tests/test_codex_hooks_config.py`
- Test: `tests/test_claude_settings_config.py`
- Test: `tests/test_codex_hooks_config.py`

- [ ] **Step 1: Add Claude Desktop local uv hook test**

Append this test to `tests/test_claude_settings_config.py` after `test_claude_hooks_use_pascalcase_event_keys`:

```python
def test_claude_session_start_registers_local_uv_pin_alignment() -> None:
    """Claude Desktop must align host uv before uv-backed hooks run.

    Refs #1745. The macOS rescue path depends on ``session_uv_local_pin.sh``
    being wired in SessionStart so a drifted package-managed host uv does not
    break later ``uv run`` commands in the session.
    """
    data = _load_settings()
    commands: list[str] = []
    for group in _hook_groups(data, "SessionStart"):
        hooks = group["hooks"]
        assert isinstance(hooks, list)
        for hook in hooks:
            assert isinstance(hook, dict)
            command = hook.get("command")
            if isinstance(command, str):
                commands.append(unwrap_command(command))

    assert "scripts/session_uv_local_pin.sh" in commands
```

- [ ] **Step 2: Add Codex Desktop local uv hook test**

Append this test to `tests/test_codex_hooks_config.py` after `test_codex_hooks_use_pascalcase_event_keys`:

```python
def test_codex_session_start_registers_local_uv_pin_alignment() -> None:
    """Codex Desktop must align host uv before uv-backed hooks run.

    Refs #1745. The macOS rescue path depends on ``session_uv_local_pin.sh``
    being wired in SessionStart so a drifted package-managed host uv does not
    break later ``uv run`` commands in the session.
    """
    data = _load_hooks()
    hooks = data["hooks"]
    assert isinstance(hooks, dict)
    session_start = hooks["SessionStart"]
    assert isinstance(session_start, list)

    commands: list[str] = []
    for group in session_start:
        assert isinstance(group, dict)
        handlers = group["hooks"]
        assert isinstance(handlers, list)
        for handler in handlers:
            assert isinstance(handler, dict)
            command = handler.get("command")
            if isinstance(command, str):
                commands.append(unwrap_command(command))

    assert "scripts/session_uv_local_pin.sh" in commands
```

- [ ] **Step 3: Run the desktop hook contract tests**

Run:

```bash
python3 -m pytest tests/test_claude_settings_config.py tests/test_codex_hooks_config.py -q
```

Expected: PASS. These are characterization tests for already-wired hook behavior.

- [ ] **Step 4: Commit**

```bash
git add tests/test_claude_settings_config.py tests/test_codex_hooks_config.py
git commit -m "test(toolchain): lock desktop pinned uv session hooks" -m "Refs #1745"
```

### Task 4: Host uv Runbook Update

**Files:**
- Modify: `docs/runbooks/host-uv-pin.md`
- Optional Modify: `docs/INDEX.md`
- Test: documentation review plus targeted pytest from Tasks 1 and 3

- [ ] **Step 1: Rewrite the runbook introduction and approach**

Update `docs/runbooks/host-uv-pin.md` so the top sections read like this:

```markdown
# Host uv Pin Alignment (macOS rescue)

Operator procedure for keeping a macOS host's `uv` aligned with the
repository pin **without** depending on Homebrew. This is the durable uv
contract for the no-sandbox macOS rescue environment used when the web
environment is unavailable or a devcontainer is broken. Original problem and
decision record: [#1205](https://github.com/tvna/claude-md/issues/1205).
Current formalization: [#1745](https://github.com/tvna/claude-md/issues/1745).

## Entrypoints

The macOS rescue environment has three supported entrypoints:

- **VS Code workspace** -- `claude-md.code-workspace` prepends
  `~/.uv-pins/claude-md` to integrated-terminal `PATH` and runs the
  `bootstrap pinned uv` task on folder open.
- **Claude Desktop** -- `.claude/settings.json` runs
  `scripts/session_uv_local_pin.sh` during `SessionStart`.
- **Codex Desktop** -- `.codex/hooks.json` runs
  `scripts/session_uv_local_pin.sh` during `SessionStart`.

All three entrypoints use the same durable prefix:
`~/.uv-pins/claude-md`. The prefix is version-agnostic by design; when
`[tool.uv].required-version` changes, `scripts/setup_pinned_uv.sh` refreshes
the binaries in place.
```

Keep the existing `## Problem` section, but adjust its first paragraph to say "macOS host" rather than generic developer host.

- [ ] **Step 2: Update the procedure section**

Replace the existing `## Procedure` section with:

```markdown
## Procedure

### VS Code workspace

1. Open `claude-md.code-workspace` in VS Code (File > Open Workspace from
   File...).
2. Grant Workspace Trust when prompted. Automatic tasks never run in an
   untrusted workspace -- this is a VS Code security control and is expected.
3. Allow the automatic task the first time VS Code asks ("Allow Automatic
   Tasks in Folder"). To skip the prompt on every open, set
   `task.allowAutomaticTasks` to `on` in your user settings (trusted
   workspaces only).
4. The `bootstrap pinned uv` task installs the pinned `uv` on first open. You
   can also run it on demand: Terminal > Run Task... > `bootstrap pinned uv`,
   or run `scripts/setup_pinned_uv.sh` directly.
5. Use Terminal > Run Task... > `apm: compile` for instruction compilation.
   The task runs `uv run --with "apm-cli==0.12.1" apm compile`; in the
   integrated terminal, `uv` resolves through `~/.uv-pins/claude-md`.

### Claude Desktop and Codex Desktop

1. Start or resume the desktop session from this repository.
2. The `SessionStart` hook runs `scripts/session_uv_local_pin.sh`.
3. If the ambient host `uv` is missing or does not match the repo pin, the
   hook runs `scripts/setup_pinned_uv.sh` and persists
   `~/.uv-pins/claude-md` into the session PATH.
4. Continue normal repo commands such as `uv sync --locked` or
   `uv run --with "apm-cli==0.12.1" apm compile`.

The hook fails open if setup cannot complete, so the session still starts.
Run the verification below before relying on the rescue environment.
```

- [ ] **Step 3: Update verification**

Replace the existing `## Verification` bullets with:

```markdown
## Verification

- `python3 scripts/uv_pin.py read pyproject.toml` prints the repository pin.
- `which uv` inside a VS Code integrated terminal or desktop agent session
  resolves under `~/.uv-pins/claude-md`.
- `uv --version` matches `python3 scripts/uv_pin.py read pyproject.toml`.
- VS Code `Tasks: Run Task` lists `bootstrap pinned uv`, `apm: compile`, and
  `uv: sync (locked)`.
- `uv run --with "apm-cli==0.12.1" apm compile` succeeds without reporting a
  `[tool.uv].required-version` mismatch.
```

- [ ] **Step 4: Update docs index if stale**

If `docs/INDEX.md` still describes `host-uv-pin.md` only as a VS Code procedure, update that row to mention all three macOS rescue entrypoints and APM compile. Keep this to one sentence.

- [ ] **Step 5: Run documentation-adjacent tests**

Run:

```bash
python3 -m pytest tests/test_vscode_workspace_uv_pin.py tests/test_claude_settings_config.py tests/test_codex_hooks_config.py -q
```

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add docs/runbooks/host-uv-pin.md docs/INDEX.md
git commit -m "docs(toolchain): formalize macos rescue pinned uv operation" -m "Refs #1745"
```

If `docs/INDEX.md` was not modified, omit it from `git add`.

### Task 5: Final Verification

**Files:**
- No edits
- Test: targeted pytest, generator drift check, shell syntax, uv pin read

- [ ] **Step 1: Run targeted pytest**

Run:

```bash
python3 -m pytest tests/test_vscode_workspace_uv_pin.py tests/test_session_uv_local_pin.py tests/test_claude_settings_config.py tests/test_codex_hooks_config.py tests/test_gen_agent_hooks.py -q
```

Expected: PASS.

- [ ] **Step 2: Run hook generator drift check**

Run:

```bash
python3 scripts/gen_agent_hooks.py --check
```

Expected: exit 0 with no stale config errors.

- [ ] **Step 3: Run shell syntax checks**

Run:

```bash
bash -n scripts/setup_pinned_uv.sh scripts/session_uv_local_pin.sh
```

Expected: exit 0.

- [ ] **Step 4: Read the uv pin**

Run:

```bash
python3 scripts/uv_pin.py read pyproject.toml
```

Expected: prints the current pinned version, for example `0.11.11`.

- [ ] **Step 5: Inspect git status**

Run:

```bash
git status --short
```

Expected: clean working tree after the task commits, except for unrelated user changes if any appear.

