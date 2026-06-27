"""Tests for the SessionStart prek installer shell guard.

scripts/install-prek.sh provisions the prek (j178/prek) git-hook runner that
.githooks/pre-commit execs (core.hooksPath=.githooks; ADR-0001), so the first
`git commit` in a fresh remote clone is not blocked on a missing runner (the
friction recorded in retro #2098). prek is a uv-managed tool, so the installer
runs `uv tool install prek` rather than a release download + sha256 verify.

These tests pin the contract that does not require network egress:
- the remote gate (silent no-op off-remote, for both signals),
- the idempotent skip when a prek is already on PATH (no `uv tool install`),
- fail-open when uv is absent (skip, exit 0, never wedge startup), and
- the SessionStart registration.
The live `uv tool install prek` path (PyPI egress) is exercised at session
start, not in CI. Refs #2098.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_ci_ops
REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_PREK = REPO_ROOT / "scripts" / "install-prek.sh"
CLAUDE_SETTINGS = REPO_ROOT / ".claude" / "settings.json"

# A PATH with the basic coreutils the script needs (dirname) but neither uv nor
# prek (both live under ~/.local/bin, deliberately excluded).
_MINIMAL_PATH = "/usr/bin:/bin"


def _make_fake_prek(bin_dir: Path) -> Path:
    """Stub prek binary that succeeds for any invocation."""
    fake = bin_dir / "prek"
    fake.write_text("#!/usr/bin/env bash\nexit 0\n")
    fake.chmod(0o755)
    return fake


def _run(env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [str(INSTALL_PREK)],
        cwd=REPO_ROOT,
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_script_is_executable() -> None:
    assert INSTALL_PREK.exists()
    assert os.access(INSTALL_PREK, os.X_OK)


def test_local_environment_is_silent_noop(tmp_path: Path) -> None:
    """No remote signal -> silent no-op, no install."""
    result = _run({"HOME": str(tmp_path), "PATH": os.environ.get("PATH", "")})
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""
    assert not (tmp_path / ".local" / "bin" / "prek").exists()


def test_remote_false_is_silent_noop(tmp_path: Path) -> None:
    result = _run(
        {
            "HOME": str(tmp_path),
            "PATH": os.environ.get("PATH", ""),
            "CLAUDE_CODE_REMOTE": "false",
        }
    )
    assert result.returncode == 0
    assert result.stdout == ""
    assert result.stderr == ""


def test_remote_true_reuses_prek_already_on_path(tmp_path: Path) -> None:
    """prek already on PATH -> idempotent skip, no `uv tool install`."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    _make_fake_prek(bin_dir)
    result = _run(
        {
            "HOME": str(tmp_path),
            "PATH": f"{bin_dir}:{_MINIMAL_PATH}",
            "CLAUDE_CODE_REMOTE": "true",
        }
    )
    assert result.returncode == 0
    assert "already present" in result.stderr


def test_codex_remote_signal_also_triggers(tmp_path: Path) -> None:
    """The dual gate fires under CODEX_CODE_REMOTE too (not just Claude)."""
    bin_dir = tmp_path / "fakebin"
    bin_dir.mkdir()
    _make_fake_prek(bin_dir)
    result = _run(
        {
            "HOME": str(tmp_path),
            "PATH": f"{bin_dir}:{_MINIMAL_PATH}",
            "CODEX_CODE_REMOTE": "true",
        }
    )
    assert result.returncode == 0
    assert "already present" in result.stderr


def test_remote_true_without_uv_fails_open(tmp_path: Path) -> None:
    """prek absent and uv absent -> skip (exit 0), never wedge startup."""
    result = _run(
        {
            "HOME": str(tmp_path),
            "PATH": _MINIMAL_PATH,
            "CLAUDE_CODE_REMOTE": "true",
        }
    )
    assert result.returncode == 0
    assert "uv not on PATH" in result.stderr
    assert not (tmp_path / ".local" / "bin" / "prek").exists()


def test_session_start_registers_install_prek() -> None:
    data = json.loads(CLAUDE_SETTINGS.read_text(encoding="utf-8"))
    session_start = data["hooks"]["SessionStart"]
    commands: list[str] = []
    for group in session_start:
        for handler in group.get("hooks", []):
            cmd = handler.get("command")
            if isinstance(cmd, str):
                commands.append(cmd)
    assert any("scripts/install-prek.sh" in cmd for cmd in commands)
