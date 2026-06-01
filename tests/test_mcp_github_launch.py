"""Tests for ``scripts/mcp_github_launch.sh``.

The wrapper is the launch command for the local GitHub MCP server (#1063). The
security-critical contract verified here:

* the minted token reaches the container by *environment* (``-e NAME`` with no
  value), never on the command line where ``ps`` could read it,
* a missing App credential fails loudly naming the variable and never starts
  the container,
* a mint failure aborts before the container starts.

``docker`` and the token minter are stubbed via the ``MCP_GITHUB_DOCKER`` and
``MCP_GITHUB_MINT`` seams the wrapper exposes, so the test needs neither real
Docker nor real GitHub credentials.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_default

WRAPPER = Path(__file__).resolve().parents[1] / "scripts" / "mcp_github_launch.sh"


def _write_docker_stub(path: Path, record: Path) -> None:
    """A fake `docker` that records its argv and the token env, then exits 0."""
    path.write_text(
        "#!/usr/bin/env bash\n"
        f'{{ echo "ARGV:$*"; echo "TOKENENV:${{GITHUB_PERSONAL_ACCESS_TOKEN:-<unset>}}"; }} > "{record}"\n'
        "exit 0\n"
    )
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def _base_env(extra: dict[str, str]) -> dict[str, str]:
    env = {"PATH": "/usr/bin:/bin"}
    env.update(extra)
    return env


def test_token_passed_by_env_not_argv(tmp_path: Path) -> None:
    record = tmp_path / "record.txt"
    docker_stub = tmp_path / "docker"
    _write_docker_stub(docker_stub, record)

    env = _base_env(
        {
            "GITHUB_APP_ID": "1",
            "GITHUB_APP_INSTALLATION_ID": "2",
            "GITHUB_APP_PRIVATE_KEY": "pem-text",
            "MCP_GITHUB_DOCKER": str(docker_stub),
            "MCP_GITHUB_MINT": "printf SECRET_TOKEN",
            "MCP_GITHUB_IMAGE": "example/image",
        }
    )
    result = subprocess.run(["bash", str(WRAPPER)], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr

    recorded = record.read_text()
    # The token must arrive via the environment...
    assert "TOKENENV:SECRET_TOKEN" in recorded
    # ...and never on the argument vector.
    assert "SECRET_TOKEN" not in recorded.split("ARGV:", 1)[1].split("\n", 1)[0]
    assert "run -i --rm -e GITHUB_PERSONAL_ACCESS_TOKEN example/image" in recorded


@pytest.mark.parametrize("missing", ["GITHUB_APP_ID", "GITHUB_APP_INSTALLATION_ID", "GITHUB_APP_PRIVATE_KEY"])
def test_missing_credential_fails_loudly_without_launch(tmp_path: Path, missing: str) -> None:
    record = tmp_path / "record.txt"
    docker_stub = tmp_path / "docker"
    _write_docker_stub(docker_stub, record)

    creds = {
        "GITHUB_APP_ID": "1",
        "GITHUB_APP_INSTALLATION_ID": "2",
        "GITHUB_APP_PRIVATE_KEY": "pem-text",
    }
    del creds[missing]
    env = _base_env(
        {
            **creds,
            "MCP_GITHUB_DOCKER": str(docker_stub),
            "MCP_GITHUB_MINT": "printf SECRET_TOKEN",
        }
    )
    result = subprocess.run(["bash", str(WRAPPER)], env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert missing in result.stderr
    assert not record.exists(), "container must not start when a credential is missing"


def test_mint_failure_aborts_before_launch(tmp_path: Path) -> None:
    record = tmp_path / "record.txt"
    docker_stub = tmp_path / "docker"
    _write_docker_stub(docker_stub, record)

    env = _base_env(
        {
            "GITHUB_APP_ID": "1",
            "GITHUB_APP_INSTALLATION_ID": "2",
            "GITHUB_APP_PRIVATE_KEY": "pem-text",
            "MCP_GITHUB_DOCKER": str(docker_stub),
            "MCP_GITHUB_MINT": "false",
        }
    )
    result = subprocess.run(["bash", str(WRAPPER)], env=env, capture_output=True, text=True)
    assert result.returncode == 1
    assert "mint" in result.stderr.lower()
    assert not record.exists()


def test_wrapper_is_executable() -> None:
    mode = WRAPPER.stat().st_mode
    assert mode & stat.S_IXUSR, "launch wrapper must be executable"
    assert os.access(WRAPPER, os.X_OK)
