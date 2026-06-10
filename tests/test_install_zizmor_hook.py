"""Tests for the SessionStart zizmor installer shell guard.

scripts/install-zizmor.sh provisions the flake-pinned zizmor binary onto PATH
in Claude Code on the Web (CLAUDE_CODE_REMOTE=true) sessions only -- zizmor is
web-only by design (not wired into the nix devShell). These tests pin the
remote gate (silent no-op off-remote), the idempotent skip when a zizmor at the
pinned version is already on PATH, and the SessionStart registration. The
actual download + sha256 verify path is exercised live (GitHub Releases egress)
rather than in CI. Refs #1610.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_ci_ops
REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_ZIZMOR = REPO_ROOT / "scripts" / "install-zizmor.sh"
CLAUDE_SETTINGS = REPO_ROOT / ".claude" / "settings.json"


def _pinned_zizmor_version() -> str:
    return subprocess.check_output(
        ["python3", str(REPO_ROOT / "scripts" / "flake_pin.py"),
         "version", "--tool", "zizmor"],
        cwd=REPO_ROOT,
        text=True,
        timeout=5,
    ).strip()


def _make_fake_zizmor(bin_dir: Path, version: str) -> Path:
    """Stub zizmor binary: reports ``zizmor <version>`` for --version."""
    fake = bin_dir / "zizmor"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        f'if [ "${{1:-}}" = "--version" ]; then echo "zizmor {version}"; fi\n'
        "exit 0\n"
    )
    fake.chmod(0o755)
    return fake


def test_script_is_executable() -> None:
    assert INSTALL_ZIZMOR.exists()
    assert os.access(INSTALL_ZIZMOR, os.X_OK)


def test_local_environment_is_silent_noop(tmp_path: Path) -> None:
    """No CLAUDE_CODE_REMOTE -> silent no-op, no install."""
    env = {
        "HOME": str(tmp_path),
        "PATH": os.environ.get("PATH", ""),
    }
    result = subprocess.run(
        [str(INSTALL_ZIZMOR)],
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
    assert not (tmp_path / ".local" / "bin" / "zizmor").exists()


def test_remote_false_is_silent_noop(tmp_path: Path) -> None:
    env = {
        "HOME": str(tmp_path),
        "PATH": os.environ.get("PATH", ""),
        "CLAUDE_CODE_REMOTE": "false",
    }
    result = subprocess.run(
        [str(INSTALL_ZIZMOR)],
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
    assert not (tmp_path / ".local" / "bin" / "zizmor").exists()


def test_remote_true_reuses_pinned_zizmor_without_download(tmp_path: Path) -> None:
    """zizmor already on PATH at the pinned version -> idempotent skip, no fetch."""
    version = _pinned_zizmor_version()
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    _make_fake_zizmor(bin_dir, version)

    env = {
        "HOME": str(tmp_path),
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
        "CLAUDE_CODE_REMOTE": "true",
    }
    result = subprocess.run(
        [str(INSTALL_ZIZMOR)],
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
    assert not (tmp_path / ".local" / "bin" / "zizmor").exists()


def test_session_start_registers_install_zizmor() -> None:
    data = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
    session_start = data["hooks"]["SessionStart"]
    commands: list[str] = []
    for group in session_start:
        for handler in group.get("hooks", []):
            cmd = handler.get("command")
            if isinstance(cmd, str):
                commands.append(cmd)
    assert any("scripts/install-zizmor.sh" in cmd for cmd in commands)
