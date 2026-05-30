"""Tests for the SessionStart uv installer shell guard.

Refs #616.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_ci_ops
REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_UV = REPO_ROOT / "scripts" / "install-uv.sh"


def _make_fake_uv(bin_dir: Path, version: str) -> Path:
    """Stub uv binary: reports *version* for --version, exits 0 for everything else."""
    fake = bin_dir / "uv"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        f'if [ "${{1:-}}" = "--version" ]; then echo "uv {version}"; fi\n'
        "exit 0\n"
    )
    fake.chmod(0o755)
    return fake


def test_codex_shaped_local_environment_is_noop(tmp_path: Path) -> None:
    env = {
        "HOME": str(tmp_path),
        "PATH": os.environ.get("PATH", ""),
        "CODEX_HOME": str(tmp_path / ".codex"),
        "CODEX_THREAD_ID": "codex-local-thread",
        "CLAUDE_PROJECT_DIR": str(REPO_ROOT),
    }

    result = subprocess.run(
        [str(INSTALL_UV)],
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
    assert not (tmp_path / ".local" / "bin" / "uv").exists()


def test_codex_code_remote_false_is_noop(tmp_path: Path) -> None:
    """CODEX_CODE_REMOTE=false keeps the no-op guard."""
    env = {
        "HOME": str(tmp_path),
        "PATH": os.environ.get("PATH", ""),
        "CODEX_HOME": str(tmp_path / ".codex"),
        "CODEX_THREAD_ID": "codex-cloud-thread",
        "CODEX_CODE_REMOTE": "false",
        "CLAUDE_PROJECT_DIR": str(REPO_ROOT),
    }

    result = subprocess.run(
        [str(INSTALL_UV)],
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
    assert not (tmp_path / ".local" / "bin" / "uv").exists()


def test_codex_code_remote_true_passes_guard(tmp_path: Path) -> None:
    """CODEX_CODE_REMOTE=true passes the remote guard and runs uv sync."""
    pin = subprocess.check_output(
        ["python3", str(REPO_ROOT / "scripts" / "uv_pin.py"), "read"],
        cwd=REPO_ROOT,
        text=True,
        timeout=5,
    ).strip()

    bin_dir = tmp_path / ".local" / "bin"
    bin_dir.mkdir(parents=True)
    _make_fake_uv(bin_dir, pin)

    env = {
        "HOME": str(tmp_path),
        "PATH": f"{bin_dir}:{os.environ.get('PATH', '')}",
        "CODEX_HOME": str(tmp_path / ".codex"),
        "CODEX_THREAD_ID": "codex-cloud-thread",
        "CODEX_CODE_REMOTE": "true",
        "CLAUDE_PROJECT_DIR": str(REPO_ROOT),
    }

    result = subprocess.run(
        [str(INSTALL_UV)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )

    assert result.returncode == 0
    assert f"uv {pin}" in result.stderr
