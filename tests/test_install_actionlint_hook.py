"""Tests for the SessionStart actionlint installer shell guard.

scripts/install-actionlint.sh provisions the flake-pinned actionlint binary
onto PATH in Claude Code on the Web (CLAUDE_CODE_REMOTE=true) sessions only,
so the workflow-lint gate adopted in #1258 actually runs during web-based
development instead of soft-skipping. These tests pin the remote gate (silent
no-op off-remote), the idempotent skip when an actionlint at the pinned version
is already on PATH, and the SessionStart registration. The actual download +
sha256 verify path is exercised live (GitHub Releases egress) rather than in
CI. Refs #1263.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_ci_ops
REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_ACTIONLINT = REPO_ROOT / "scripts" / "install-actionlint.sh"
CLAUDE_SETTINGS = REPO_ROOT / ".claude" / "settings.json"


def _pinned_actionlint_version() -> str:
    return subprocess.check_output(
        ["python3", str(REPO_ROOT / "scripts" / "flake_pin.py"),
         "version", "--tool", "actionlint"],
        cwd=REPO_ROOT,
        text=True,
        timeout=5,
    ).strip()


def _make_fake_actionlint(bin_dir: Path, version: str) -> Path:
    """Stub actionlint binary: prints *version* for --version, exits 0 else.

    install-actionlint.sh compares against ``actionlint --version | head -1``,
    so the stub prints the bare version on the first line.
    """
    fake = bin_dir / "actionlint"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        f'if [ "${{1:-}}" = "--version" ]; then echo "{version}"; fi\n'
        "exit 0\n"
    )
    fake.chmod(0o755)
    return fake


def test_script_is_executable() -> None:
    assert INSTALL_ACTIONLINT.exists()
    assert os.access(INSTALL_ACTIONLINT, os.X_OK)


def test_local_environment_is_silent_noop(tmp_path: Path) -> None:
    """No CLAUDE_CODE_REMOTE -> silent no-op, no install."""
    env = {
        "HOME": str(tmp_path),
        "PATH": os.environ.get("PATH", ""),
    }
    result = subprocess.run(
        [str(INSTALL_ACTIONLINT)],
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
    assert not (tmp_path / ".local" / "bin" / "actionlint").exists()


def test_remote_false_is_silent_noop(tmp_path: Path) -> None:
    env = {
        "HOME": str(tmp_path),
        "PATH": os.environ.get("PATH", ""),
        "CLAUDE_CODE_REMOTE": "false",
    }
    result = subprocess.run(
        [str(INSTALL_ACTIONLINT)],
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
    assert not (tmp_path / ".local" / "bin" / "actionlint").exists()


def test_remote_true_reuses_pinned_actionlint_without_download(
    tmp_path: Path,
) -> None:
    """actionlint already on PATH at the pinned version -> skip, no fetch."""
    version = _pinned_actionlint_version()
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    _make_fake_actionlint(bin_dir, version)

    env = {
        "HOME": str(tmp_path),
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
        "CLAUDE_CODE_REMOTE": "true",
    }
    result = subprocess.run(
        [str(INSTALL_ACTIONLINT)],
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
    assert not (tmp_path / ".local" / "bin" / "actionlint").exists()


def test_codex_remote_true_enters_active_path(tmp_path: Path) -> None:
    """CODEX_CODE_REMOTE=true (no CLAUDE_CODE_REMOTE) reaches provisioning.

    Anchors the #1608 gate widening: under Codex cloud the script must NOT be
    a no-op. With a pinned actionlint already on PATH it hits the idempotent
    reuse branch; proof the dual-signal gate let it past, mirroring the
    CLAUDE_CODE_REMOTE case above.
    """
    version = _pinned_actionlint_version()
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    _make_fake_actionlint(bin_dir, version)

    env = {
        "HOME": str(tmp_path),
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
        "CODEX_CODE_REMOTE": "true",
    }
    result = subprocess.run(
        [str(INSTALL_ACTIONLINT)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0
    assert "already present" in result.stderr
    assert not (tmp_path / ".local" / "bin" / "actionlint").exists()


def test_session_start_registers_install_actionlint_on_all_agents() -> None:
    """actionlint provisions claude, codex, and devin (Refs #1608)."""
    for path in (
        CLAUDE_SETTINGS,
        REPO_ROOT / ".codex" / "hooks.json",
        REPO_ROOT / ".devin" / "hooks.v1.json",
    ):
        data = json.loads(path.read_text(encoding="utf-8"))
        commands: list[str] = []
        for group in data["hooks"]["SessionStart"]:
            for handler in group.get("hooks", []):
                cmd = handler.get("command")
                if isinstance(cmd, str):
                    commands.append(cmd)
        assert any(
            "scripts/install-actionlint.sh" in cmd for cmd in commands
        ), f"install-actionlint.sh missing from SessionStart in {path.name}"
