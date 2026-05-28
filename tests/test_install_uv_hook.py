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
