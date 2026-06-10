"""Tests for the SessionStart bun installer shell guard.

scripts/install-bun.sh provisions the pinned bun runtime onto PATH and
materialises the Mermaid-gate node_modules (mermaid + jsdom) in Claude Code on
the Web (CLAUDE_CODE_REMOTE=true) sessions only. These tests pin the remote
gate (silent no-op off-remote), the idempotent reuse when a bun at the pinned
version is already on PATH, and the SessionStart registration. The actual
download + sha256 verify path is exercised live (GitHub Releases egress) rather
than in CI. Refs #1597.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_ci_ops
REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_BUN = REPO_ROOT / "scripts" / "install-bun.sh"
CLAUDE_SETTINGS = REPO_ROOT / ".claude" / "settings.json"
# All three agent configs must provision bun at SessionStart so the Mermaid
# gate runs locally regardless of which agent opened the session (.devin
# mirrors .codex via the generator). Refs #1597.
AGENT_CONFIGS = (
    REPO_ROOT / ".claude" / "settings.json",
    REPO_ROOT / ".codex" / "hooks.json",
    REPO_ROOT / ".devin" / "hooks.v1.json",
)


def _pinned_bun_version() -> str:
    text = INSTALL_BUN.read_text(encoding="utf-8")
    match = re.search(r'BUN_VERSION="([^"]+)"', text)
    assert match, "install-bun.sh must pin BUN_VERSION"
    return match.group(1)


def _make_fake_bun(bin_dir: Path, version: str) -> Path:
    """Stub bun binary: reports *version* for --version, exits 0 otherwise."""
    fake = bin_dir / "bun"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        f'if [ "${{1:-}}" = "--version" ]; then echo "{version}"; exit 0; fi\n'
        "exit 0\n"
    )
    fake.chmod(0o755)
    return fake


def test_script_is_executable() -> None:
    assert INSTALL_BUN.exists()
    assert os.access(INSTALL_BUN, os.X_OK)


def test_local_environment_is_silent_noop(tmp_path: Path) -> None:
    """No CLAUDE_CODE_REMOTE -> silent no-op, no install."""
    env = {"HOME": str(tmp_path), "PATH": os.environ.get("PATH", "")}
    result = subprocess.run(
        [str(INSTALL_BUN)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert not (tmp_path / ".local" / "bin" / "bun").exists()


def test_remote_false_is_silent_noop(tmp_path: Path) -> None:
    env = {
        "HOME": str(tmp_path),
        "PATH": os.environ.get("PATH", ""),
        "CLAUDE_CODE_REMOTE": "false",
    }
    result = subprocess.run(
        [str(INSTALL_BUN)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert not (tmp_path / ".local" / "bin" / "bun").exists()


def test_remote_true_reuses_pinned_bun_without_download(tmp_path: Path) -> None:
    """bun already on PATH at the pinned version -> idempotent reuse, no fetch.

    The repo has no package.json under the temp HOME's CWD override, so the
    best-effort `bun install` step is a no-op; the assertion is only that the
    reuse path runs and does not download a second binary into ~/.local/bin.
    """
    version = _pinned_bun_version()
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    _make_fake_bun(bin_dir, version)

    # Run from an empty working directory so the best-effort dependency
    # materialisation finds no package.json and returns immediately.
    workdir = tmp_path / "empty"
    workdir.mkdir()
    env = {
        "HOME": str(tmp_path),
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
        "CLAUDE_CODE_REMOTE": "true",
    }
    result = subprocess.run(
        [str(INSTALL_BUN)],
        cwd=workdir,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0
    assert "already present" in result.stderr
    assert not (tmp_path / ".local" / "bin" / "bun").exists()


@pytest.mark.parametrize("config_path", AGENT_CONFIGS, ids=lambda p: p.parent.name)
def test_session_start_registers_install_bun(config_path: Path) -> None:
    data = json.loads(config_path.read_text(encoding="utf-8"))
    session_start = data["hooks"]["SessionStart"]
    commands: list[str] = []
    for group in session_start:
        for handler in group.get("hooks", []):
            cmd = handler.get("command")
            if isinstance(cmd, str):
                commands.append(cmd)
    assert any("scripts/install-bun.sh" in cmd for cmd in commands)
