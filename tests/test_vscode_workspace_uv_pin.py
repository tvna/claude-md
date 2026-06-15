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
