"""Tests for ``scripts/session_uv_local_pin.sh``.

Refs #1207. The script is a bash SessionStart hook; the tests drive it
end-to-end with fake ``uv``, fake ``setup_pinned_uv.sh``, and an isolated
``CLAUDE_PROJECT_DIR`` so each invocation is hermetic.
"""

from __future__ import annotations

import stat
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_preflight

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "session_uv_local_pin.sh"


def _make_executable(path: Path) -> None:
    path.chmod(path.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def _fake_uv(bin_dir: Path, version: str) -> None:
    """Drop an executable ``uv`` stub into *bin_dir* that prints *version*."""
    bin_dir.mkdir(parents=True, exist_ok=True)
    fake = bin_dir / "uv"
    fake.write_text(f'#!/usr/bin/env bash\necho "uv {version} (fake)"\n')
    _make_executable(fake)


def _stage_repo(tmp_path: Path, pin: str) -> Path:
    """Create a fake CLAUDE_PROJECT_DIR with pyproject.toml, a stub scripts/
    dir containing the real uv_pin.py, the real session_uv_local_pin.sh, and
    a stub setup_pinned_uv.sh that records its invocation.
    """
    project = tmp_path / "project"
    scripts = project / "scripts"
    scripts.mkdir(parents=True)
    (project / "pyproject.toml").write_text(f'[tool.uv]\nrequired-version = "=={pin}"\n')

    # Copy the real uv_pin.py + the script under test so they live alongside
    # each other (matching the production layout).
    (scripts / "uv_pin.py").write_bytes((REPO_ROOT / "scripts" / "uv_pin.py").read_bytes())
    # session_uv_local_pin.sh sources the shared PATH-persistence helper, so it
    # must live alongside the script under test in the staged scripts/ dir.
    (scripts / "_session_path.sh").write_bytes(
        (REPO_ROOT / "scripts" / "_session_path.sh").read_bytes()
    )
    (scripts / "session_uv_local_pin.sh").write_bytes(SCRIPT.read_bytes())
    _make_executable(scripts / "session_uv_local_pin.sh")

    # Stub setup_pinned_uv.sh that records its invocation. Real installer
    # would download from the network; tests must not.
    marker = project / "setup-called"
    stub = scripts / "setup_pinned_uv.sh"
    stub.write_text(
        "#!/usr/bin/env bash\n"
        f'touch "{marker}"\n'
        "echo setup-stub-ran >&2\n"
    )
    _make_executable(stub)
    return project


def _run(
    project: Path,
    *,
    uv_version_on_path: str | None,
    env_file: Path | None,
    remote: bool = False,
) -> subprocess.CompletedProcess[str]:
    """Run the script in an isolated environment.

    *uv_version_on_path* selects which fake uv (or none) is reachable
    through PATH. *env_file* is exported as ``CLAUDE_ENV_FILE`` so the
    PATH-export side effect is observable. *remote* toggles
    ``CLAUDE_CODE_REMOTE``.
    """
    bin_dir = project / "bin"
    if uv_version_on_path is not None:
        _fake_uv(bin_dir, uv_version_on_path)
    else:
        bin_dir.mkdir(parents=True, exist_ok=True)

    # PATH must contain bin_dir (for the fake uv) but NOT any other dir
    # that holds a real uv. The test runner's python is included so
    # ``python3 uv_pin.py`` resolves to a 3.11+ interpreter (tomllib);
    # macOS' /usr/bin/python3 is 3.9 and would fail. /usr/bin and /bin are
    # kept so awk, command, bash builtins remain reachable.
    python_bin = Path(sys.executable).parent
    env = {
        "PATH": f"{bin_dir}:{python_bin}:/usr/bin:/bin",
        "HOME": str(project / "home"),
        "CLAUDE_PROJECT_DIR": str(project),
        # Pin the workspace-local prefix into the project tree so a real
        # `~/.uv-pins/claude-md` is never touched by the test suite.
        "UV_PIN_DIR": str(project / "pinned"),
    }
    if env_file is not None:
        env["CLAUDE_ENV_FILE"] = str(env_file)
    if remote:
        env["CLAUDE_CODE_REMOTE"] = "true"

    (project / "home").mkdir(exist_ok=True)

    return subprocess.run(
        ["bash", str(project / "scripts" / "session_uv_local_pin.sh")],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


class TestRemoteGate:
    def test_remote_env_is_noop(self, tmp_path: Path) -> None:
        project = _stage_repo(tmp_path, "0.11.11")
        env_file = tmp_path / "claude-env"
        env_file.write_text("")

        result = _run(project, uv_version_on_path="0.11.16", env_file=env_file, remote=True)

        assert result.returncode == 0
        assert not (project / "setup-called").exists(), "setup_pinned_uv.sh must not run on remote"
        assert env_file.read_text() == "", "CLAUDE_ENV_FILE must not be touched on remote"


class TestFastPathAligned:
    def test_aligned_uv_skips_install_and_path_edit(self, tmp_path: Path) -> None:
        project = _stage_repo(tmp_path, "0.11.11")
        env_file = tmp_path / "claude-env"
        env_file.write_text("")

        result = _run(project, uv_version_on_path="0.11.11", env_file=env_file)

        assert result.returncode == 0, result.stderr
        assert not (project / "setup-called").exists(), "no install when aligned"
        assert env_file.read_text() == "", "no PATH edit when aligned"


class TestSlowPathMismatch:
    def test_drifted_uv_triggers_setup_and_path_export(self, tmp_path: Path) -> None:
        project = _stage_repo(tmp_path, "0.11.11")
        env_file = tmp_path / "claude-env"
        env_file.write_text("")

        # After the stub setup runs, a uv that DOES satisfy the pin needs to
        # be reachable inside the pinned prefix so the script can emit
        # `uv --version` at the end without crashing. The stub itself just
        # records the call; we drop the matching binary in place beforehand.
        _fake_uv(project / "pinned", "0.11.11")

        result = _run(project, uv_version_on_path="0.11.16", env_file=env_file)

        assert result.returncode == 0, result.stderr
        assert (project / "setup-called").exists(), "setup must run on mismatch"
        assert f'export PATH="{project / "pinned"}:$PATH"' in env_file.read_text()

    def test_missing_uv_triggers_setup_and_path_export(self, tmp_path: Path) -> None:
        project = _stage_repo(tmp_path, "0.11.11")
        env_file = tmp_path / "claude-env"
        env_file.write_text("")
        _fake_uv(project / "pinned", "0.11.11")

        result = _run(project, uv_version_on_path=None, env_file=env_file)

        assert result.returncode == 0, result.stderr
        assert (project / "setup-called").exists()
        assert f'export PATH="{project / "pinned"}:$PATH"' in env_file.read_text()


class TestFailureModes:
    def test_unreadable_pin_exits_zero_with_warning(self, tmp_path: Path) -> None:
        """A broken pyproject.toml must NOT wedge the session -- fail open
        with a stderr notice, exit 0. Same posture as other SessionStart
        hooks (refs scripts/check_session_branch.py).
        """
        project = _stage_repo(tmp_path, "0.11.11")
        (project / "pyproject.toml").write_text("[[[ not toml")

        result = _run(project, uv_version_on_path="0.11.16", env_file=None)

        assert result.returncode == 0
        assert "cannot read uv pin" in result.stderr

    def test_setup_failure_does_not_wedge_session(self, tmp_path: Path) -> None:
        """If setup_pinned_uv.sh fails (network down, prefix unwritable),
        the SessionStart hook must still exit 0 so the session can start.
        The next preflight_uv_version run will surface the unresolved drift.
        """
        project = _stage_repo(tmp_path, "0.11.11")
        env_file = tmp_path / "claude-env"
        env_file.write_text("")

        broken = project / "scripts" / "setup_pinned_uv.sh"
        broken.write_text("#!/usr/bin/env bash\nexit 7\n")
        _make_executable(broken)

        result = _run(project, uv_version_on_path="0.11.16", env_file=env_file)

        assert result.returncode == 0
        assert env_file.read_text() == "", "no PATH export when setup failed"
        assert "setup_pinned_uv.sh failed" in result.stderr


class TestEnvFileOptional:
    def test_missing_env_file_is_tolerated(self, tmp_path: Path) -> None:
        """`$CLAUDE_ENV_FILE` is harness-provided. If absent (manual run),
        the script must still install + export PATH within its own shell
        without crashing.
        """
        project = _stage_repo(tmp_path, "0.11.11")
        _fake_uv(project / "pinned", "0.11.11")

        result = _run(project, uv_version_on_path="0.11.16", env_file=None)

        assert result.returncode == 0, result.stderr
        assert (project / "setup-called").exists()
