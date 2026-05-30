"""Static contracts for Claude/Codex devcontainer runtime ergonomics."""

from __future__ import annotations

import json
import tomllib
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
    claude_settings = (REPO_ROOT / ".devcontainer/config/claude/settings.json").read_text(encoding="utf-8")
    agent_prompt = (REPO_ROOT / ".devcontainer/config/profile.d/claude-md-agent-prompt.sh").read_text(encoding="utf-8")

    assert "install_nix_binary gh-cli gh" in script
    assert '"Bash(*)"' in claude_settings
    assert '"mcp__github__*"' in claude_settings
    assert "/etc/profile.d/claude-md-agent-prompt.sh" in script
    assert "agent:repo(branch)" in agent_prompt


def test_codex_runtime_config_uses_supported_toml_keys() -> None:
    codex_toml = (REPO_ROOT / ".devcontainer/config/codex/config.toml").read_text(encoding="utf-8")

    assert 'approval_policy = "never"' in codex_toml
    assert "[mcp_servers.codex_apps]" not in codex_toml
    assert "[permissions]" not in codex_toml
    assert "allow = [" not in codex_toml


def test_codex_runtime_config_pretrusts_workspace() -> None:
    config_path = REPO_ROOT / ".devcontainer/config/codex/config.toml"
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))

    projects = config.get("projects")
    assert isinstance(projects, dict)
    workspace = projects.get("/workspaces/claude-md")
    assert isinstance(workspace, dict)
    assert workspace.get("trust_level") == "trusted"


def test_runbook_documents_existing_codex_volume_refresh() -> None:
    runbook = (REPO_ROOT / "docs/runbooks/devcontainers.md").read_text(encoding="utf-8")

    assert "bash .devcontainer/scripts/configure-agent-runtime.sh codex" in runbook
    assert "command -v bwrap" in runbook


def test_runbook_documents_codex_transport_timeout_diagnostics() -> None:
    runbook = (REPO_ROOT / "docs/runbooks/devcontainers.md").read_text(encoding="utf-8")

    assert "Falling back from WebSockets to HTTPS transport" in runbook
    assert "Conversation interrupted" in runbook
    assert "getent hosts api.openai.com auth.openai.com" in runbook
    assert "curl -I --max-time 20 https://api.openai.com" in runbook
    assert "HTTP/2 421" in runbook
    assert "cf-mitigated: challenge" in runbook
    assert "Set-Cookie" in runbook
    assert "DEVCONTAINER_APPLY_EGRESS_ALLOWLIST=0" in runbook


def test_flake_exposes_gh_cli_package_for_runtime_symlink() -> None:
    flake = (REPO_ROOT / "flake.nix").read_text(encoding="utf-8")

    assert "gh-cli = pkgs.gh;" in flake


def test_runtime_script_links_python3_for_hook_subprocesses() -> None:
    flake = (REPO_ROOT / "flake.nix").read_text(encoding="utf-8")
    script = (REPO_ROOT / ".devcontainer/scripts/configure-agent-runtime.sh").read_text(encoding="utf-8")

    assert "python-runtime = pkgs.python311;" in flake
    assert "install_nix_binary python-runtime python3" in script


def test_codex_runtime_installs_bubblewrap_for_sandbox() -> None:
    flake = (REPO_ROOT / "flake.nix").read_text(encoding="utf-8")
    script = (REPO_ROOT / ".devcontainer/scripts/configure-agent-runtime.sh").read_text(encoding="utf-8")

    assert "bubblewrap = pkgs.bubblewrap;" in flake
    assert "agentPackages.bubblewrap" in flake
    assert "install_nix_binary bubblewrap bwrap" in script


def test_devcontainer_publish_watches_runtime_script() -> None:
    workflow = (REPO_ROOT / ".github/workflows/publish-devcontainer-images.yml").read_text(encoding="utf-8")

    assert '".devcontainer/scripts/configure-agent-runtime.sh"' in workflow


def test_runbook_documents_persistent_session_reset() -> None:
    runbook = (REPO_ROOT / "docs/runbooks/devcontainers.md").read_text(encoding="utf-8")

    for agent in AGENTS:
        assert f"podman volume rm claude-md-{agent}-session claude-md-{agent}-gh" in runbook
