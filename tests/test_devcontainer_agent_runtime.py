"""Static contracts for Claude/Codex devcontainer runtime ergonomics."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parents[1]
AGENTS = ("claude", "codex")


def load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_local_entrypoints_persist_agent_and_gh_sessions() -> None:
    for agent in AGENTS:
        config = load_json(REPO_ROOT / ".devcontainer" / agent / "devcontainer.json")
        mounts = config.get("mounts")
        assert isinstance(mounts, list)
        assert f"source=claude-md-{agent}-session,target=/home/{agent}/.{agent},type=volume" in mounts
        assert f"source=claude-md-{agent}-gh,target=/home/{agent}/.config/gh,type=volume" in mounts


def test_entrypoints_run_runtime_configuration() -> None:
    for path in [
        *(REPO_ROOT / ".devcontainer" / agent / "devcontainer.json" for agent in AGENTS),
        *(REPO_ROOT / ".devcontainer" / "images" / agent / "devcontainer.json" for agent in AGENTS),
    ]:
        config = load_json(path)
        post_create = config.get("postCreateCommand")
        assert isinstance(post_create, str)
        assert "bash .devcontainer/scripts/configure-agent-runtime.sh" in post_create


def test_runtime_script_installs_gh_and_container_scoped_defaults() -> None:
    script = (REPO_ROOT / ".devcontainer/scripts/configure-agent-runtime.sh").read_text(encoding="utf-8")

    assert "install_nix_binary gh-cli gh" in script
    assert '"Bash(*)"' in script
    assert '"mcp__github__*"' in script
    assert "/etc/profile.d/claude-md-agent-prompt.sh" in script
    assert "agent:repo(branch)" in script


def test_codex_runtime_config_uses_supported_toml_keys() -> None:
    script = (REPO_ROOT / ".devcontainer/scripts/configure-agent-runtime.sh").read_text(encoding="utf-8")

    start = script.index('tee "$home_dir/.codex/config.toml"')
    heredoc_start = script.index("<<'TOML'", start)
    toml_start = script.index("\n", heredoc_start) + 1
    toml_end = script.index("\nTOML", toml_start)
    codex_toml = script[toml_start:toml_end]

    assert 'approval_policy = "never"' in codex_toml
    assert "[permissions]" not in codex_toml
    assert "allow = [" not in codex_toml


def test_flake_exposes_gh_cli_package_for_runtime_symlink() -> None:
    flake = (REPO_ROOT / "flake.nix").read_text(encoding="utf-8")

    assert "gh-cli = pkgs.gh;" in flake


def test_devcontainer_publish_watches_runtime_script() -> None:
    workflow = (REPO_ROOT / ".github/workflows/publish-devcontainer-images.yml").read_text(encoding="utf-8")

    assert '".devcontainer/scripts/configure-agent-runtime.sh"' in workflow


def test_runbook_documents_persistent_session_reset() -> None:
    runbook = (REPO_ROOT / "docs/runbooks/devcontainers.md").read_text(encoding="utf-8")

    for agent in AGENTS:
        assert f"podman volume rm claude-md-{agent}-session claude-md-{agent}-gh" in runbook
