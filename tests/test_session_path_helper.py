"""Tests for the shared SessionStart PATH-persistence helper.

scripts/_session_path.sh is sourced by the three SessionStart provisioning
scripts (install-uv.sh, install-rtk.sh, session_uv_local_pin.sh). It holds the
single `persist_session_path <dir>` routine those scripts previously each
reimplemented. These tests pin the behaviour that refactor must preserve:

* dir absent from PATH + $CLAUDE_ENV_FILE set -> append the export line and
  prefix PATH in the current process;
* dir already on PATH -> no env-file write, PATH unchanged (idempotent);
* $CLAUDE_ENV_FILE unset -> still prefix PATH, just no persistence write;
* empty dir -> fail loud (non-zero), never widen PATH with an empty element.

Refs #1230.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_ci_ops
REPO_ROOT = Path(__file__).resolve().parents[1]
HELPER = REPO_ROOT / "scripts" / "_session_path.sh"
BASH = str(Path("/bin/bash") if Path("/bin/bash").exists() else shutil.which("bash") or "bash")


def _run(dir_arg: str, *, path: str, env_file: str | None) -> subprocess.CompletedProcess[str]:
    """Source the helper, call persist_session_path, print the resulting PATH."""
    env = {"PATH": path}
    if env_file is not None:
        env["CLAUDE_ENV_FILE"] = env_file
    script = (
        "set -euo pipefail\n"
        f'. "{HELPER}"\n'
        f'persist_session_path "{dir_arg}"\n'
        'printf "PATH=%s\\n" "$PATH"\n'
    )
    return subprocess.run(
        [BASH, "-c", script],
        env=env,
        check=False,
        capture_output=True,
        text=True,
        timeout=10,
    )


def test_appends_and_exports_when_absent(tmp_path: Path) -> None:
    env_file = tmp_path / "env"
    new_dir = "/opt/pin/bin"
    result = _run(new_dir, path="/usr/bin:/bin", env_file=str(env_file))

    assert result.returncode == 0, result.stderr
    # Persisted for the session.
    assert env_file.read_text(encoding="utf-8") == f'export PATH="{new_dir}:$PATH"\n'
    # Exported into the current process, taking precedence.
    assert "PATH=/opt/pin/bin:/usr/bin:/bin" in result.stdout


def test_idempotent_when_already_on_path(tmp_path: Path) -> None:
    env_file = tmp_path / "env"
    existing = "/opt/pin/bin"
    result = _run(existing, path=f"{existing}:/usr/bin", env_file=str(env_file))

    assert result.returncode == 0, result.stderr
    # No persistence write, PATH unchanged.
    assert not env_file.exists() or env_file.read_text(encoding="utf-8") == ""
    assert "PATH=/opt/pin/bin:/usr/bin" in result.stdout


def test_exports_without_env_file(tmp_path: Path) -> None:
    new_dir = "/opt/pin/bin"
    result = _run(new_dir, path="/usr/bin:/bin", env_file=None)

    assert result.returncode == 0, result.stderr
    assert "PATH=/opt/pin/bin:/usr/bin:/bin" in result.stdout


def test_empty_dir_fails_loud(tmp_path: Path) -> None:
    env_file = tmp_path / "env"
    result = _run("", path="/usr/bin:/bin", env_file=str(env_file))

    assert result.returncode == 2
    assert "refusing to add an empty directory" in result.stderr
    assert not env_file.exists() or env_file.read_text(encoding="utf-8") == ""


def test_helper_is_not_a_provisioning_installer() -> None:
    """The helper name must not match scan_provisioning_hook_serial's regex.

    That gate flags ``install_<name>.sh`` entries; ``_session_path.sh`` is a
    sourced library, not an installer, so it must stay outside that pattern.
    """
    assert re.search(r"install_\w+\.sh", HELPER.name) is None


def test_session_start_scripts_source_the_helper() -> None:
    for script in ("install-uv.sh", "install-rtk.sh", "session_uv_local_pin.sh"):
        text = (REPO_ROOT / "scripts" / script).read_text(encoding="utf-8")
        assert "_session_path.sh" in text, f"{script} does not source the helper"
        assert "persist_session_path" in text, f"{script} does not call the helper"


def test_helper_does_not_redefine_path_inline() -> None:
    """The three scripts must not keep a private copy of the persistence block."""
    for script in ("install-uv.sh", "install-rtk.sh", "session_uv_local_pin.sh"):
        text = (REPO_ROOT / "scripts" / script).read_text(encoding="utf-8")
        assert "persist_path()" not in text, f"{script} still defines persist_path()"


def test_script_exists() -> None:
    assert HELPER.exists()
