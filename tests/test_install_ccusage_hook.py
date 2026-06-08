"""Tests for the SessionStart ccusage installer shell guard.

scripts/install-ccusage.sh provisions the flake-pinned ccusage binary onto PATH
in Claude Code on the Web (CLAUDE_CODE_REMOTE=true) sessions only. These tests
pin the remote gate (silent no-op off-remote), the idempotent skip when a
ccusage at the pinned version is already on PATH, and the SessionStart
registration. The actual download + sha256 verify path is exercised live (npm
registry egress) rather than in CI. Mirrors tests/test_install_waza_hook.py.
Refs #1404.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_ci_ops
REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_CCUSAGE = REPO_ROOT / "scripts" / "install-ccusage.sh"
CLAUDE_SETTINGS = REPO_ROOT / ".claude" / "settings.json"


def _pinned_ccusage_version() -> str:
    return subprocess.check_output(
        ["python3", str(REPO_ROOT / "scripts" / "ccusage_pin.py"), "version"],
        cwd=REPO_ROOT,
        text=True,
        timeout=5,
    ).strip()


def _make_fake_ccusage(bin_dir: Path, version: str) -> Path:
    """Stub ccusage binary: reports *version* for --version, exits 0 otherwise."""
    fake = bin_dir / "ccusage"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        f'if [ "${{1:-}}" = "--version" ]; then echo "ccusage {version}"; fi\n'
        "exit 0\n"
    )
    fake.chmod(0o755)
    return fake


def test_script_is_executable() -> None:
    assert INSTALL_CCUSAGE.exists()
    assert os.access(INSTALL_CCUSAGE, os.X_OK)


def test_local_environment_is_silent_noop(tmp_path: Path) -> None:
    """No CLAUDE_CODE_REMOTE -> silent no-op, no install."""
    env = {
        "HOME": str(tmp_path),
        "PATH": os.environ.get("PATH", ""),
    }
    result = subprocess.run(
        [str(INSTALL_CCUSAGE)],
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
    assert not (tmp_path / ".local" / "bin" / "ccusage").exists()


def test_remote_false_is_silent_noop(tmp_path: Path) -> None:
    env = {
        "HOME": str(tmp_path),
        "PATH": os.environ.get("PATH", ""),
        "CLAUDE_CODE_REMOTE": "false",
    }
    result = subprocess.run(
        [str(INSTALL_CCUSAGE)],
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
    assert not (tmp_path / ".local" / "bin" / "ccusage").exists()


def test_remote_true_reuses_pinned_ccusage_without_download(tmp_path: Path) -> None:
    """ccusage already on PATH at the pinned version -> idempotent skip, no fetch."""
    version = _pinned_ccusage_version()
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    _make_fake_ccusage(bin_dir, version)

    env = {
        "HOME": str(tmp_path),
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
        "CLAUDE_CODE_REMOTE": "true",
    }
    result = subprocess.run(
        [str(INSTALL_CCUSAGE)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "already present" in result.stderr
    # The idempotent path must not download into ~/.local/bin.
    assert not (tmp_path / ".local" / "bin" / "ccusage").exists()


def test_session_start_registers_install_ccusage() -> None:
    data = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
    session_start = data["hooks"]["SessionStart"]
    commands: list[str] = []
    for group in session_start:
        for handler in group.get("hooks", []):
            cmd = handler.get("command")
            if isinstance(cmd, str):
                commands.append(cmd)
    assert any("scripts/install-ccusage.sh" in cmd for cmd in commands)
