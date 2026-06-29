"""Tests for the SessionStart stop-hook-git-check restore script.

scripts/session_restore_stop_hook_git_check.sh copies the repo-owned source of
truth tests/fixtures/stop-hook-git-check.sh into ~/.claude/stop-hook-git-check.sh
in Claude Code on the Web (CLAUDE_CODE_REMOTE=true) sessions, because the remote
environment periodically reverts that file to the upstream (buggy) variant. It
is a Claude-only hook restore (named session_* rather than install-*) and is
intentionally outside the install-*.sh cross-agent parity contract.

These tests pin:
- the remote gate (silent no-op off-remote);
- that the script deploys EXACTLY the fixture bytes (the drift gate: the
  deployed hook can never diverge from the version the smoke test validates);
- idempotent re-run when already in sync;
- the SessionStart registration in .claude/settings.json.

Refs #2159.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "session_restore_stop_hook_git_check.sh"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "stop-hook-git-check.sh"
CLAUDE_SETTINGS = REPO_ROOT / ".claude" / "settings.json"
DEST_REL = ".claude/stop-hook-git-check.sh"


def _run(home: Path, *, remote: bool) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k != "CLAUDE_CODE_REMOTE"}
    env["HOME"] = str(home)
    if remote:
        env["CLAUDE_CODE_REMOTE"] = "true"
    return subprocess.run(
        ["bash", str(SCRIPT)], env=env, capture_output=True, text=True
    )


def test_script_is_executable() -> None:
    assert SCRIPT.exists()
    assert os.access(SCRIPT, os.X_OK)


def test_local_environment_is_silent_noop(tmp_path: Path) -> None:
    result = _run(tmp_path, remote=False)
    assert result.returncode == 0
    assert not (tmp_path / DEST_REL).exists(), "off-remote run must not deploy anything"


def test_deploys_exact_fixture_bytes(tmp_path: Path) -> None:
    result = _run(tmp_path, remote=True)
    assert result.returncode == 0, result.stderr
    dest = tmp_path / DEST_REL
    assert dest.exists(), "remote run must deploy the hook"
    assert dest.read_bytes() == FIXTURE.read_bytes(), (
        "deployed hook must be byte-identical to the smoke-tested fixture"
    )
    assert os.access(dest, os.X_OK), "deployed hook must be executable"


def test_replaces_a_reverted_hook(tmp_path: Path) -> None:
    """A stale/buggy hook already in place is overwritten with the fixture."""
    dest = tmp_path / DEST_REL
    dest.parent.mkdir(parents=True)
    dest.write_text("#!/bin/bash\n# stale upstream variant\nexit 0\n", encoding="utf-8")
    result = _run(tmp_path, remote=True)
    assert result.returncode == 0, result.stderr
    assert dest.read_bytes() == FIXTURE.read_bytes()


def test_idempotent_when_in_sync(tmp_path: Path) -> None:
    first = _run(tmp_path, remote=True)
    assert first.returncode == 0, first.stderr
    second = _run(tmp_path, remote=True)
    assert second.returncode == 0
    assert second.stderr.strip() == "", "a second in-sync run must be a silent no-op"


def test_session_start_registration() -> None:
    settings = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
    commands = [
        hook["command"]
        for entry in settings["hooks"]["SessionStart"]
        for hook in entry["hooks"]
    ]
    assert any("session_restore_stop_hook_git_check.sh" in c for c in commands), (
        "the restore script must be wired into .claude/settings.json SessionStart"
    )
