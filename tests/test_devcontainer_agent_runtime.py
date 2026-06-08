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
        assert f"source=${{localEnv:HOME}}/.config/gh,target=/home/{agent}/.config/gh,type=bind,consistency=cached" in mounts


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
    # The GitHub MCP server binary backs the Docker-less stdio launch path (#1063).
    assert "install_nix_binary github-mcp-server github-mcp-server" in script
    assert '"Bash(*)"' in claude_settings
    assert '"mcp__github__*"' in claude_settings
    assert "/etc/profile.d/claude-md-agent-prompt.sh" in script
    assert "agent:repo(branch)" in agent_prompt


def test_runtime_provisions_rtk_for_claude_pretooluse_hook() -> None:
    script = (REPO_ROOT / ".devcontainer/scripts/configure-agent-runtime.sh").read_text(encoding="utf-8")
    claude_settings = load_json(REPO_ROOT / ".devcontainer/config/claude/settings.json")

    # rtk must be symlinked to /usr/local/bin so the PreToolUse hook resolves it.
    assert "install_nix_binary rtk-cli rtk" in script

    # The claude config declares the rtk auto-rewrite PreToolUse Bash hook.
    hooks = claude_settings.get("hooks")
    assert isinstance(hooks, dict)
    pre_tool_use = hooks.get("PreToolUse")
    assert isinstance(pre_tool_use, list)
    rtk_commands = [
        inner.get("command")
        for entry in pre_tool_use
        if isinstance(entry, dict) and entry.get("matcher") == "Bash"
        for inner in (entry.get("hooks") or [])
        if isinstance(inner, dict)
    ]
    assert "rtk hook claude" in rtk_commands


def test_codex_runtime_config_uses_supported_toml_keys() -> None:
    codex_toml = (REPO_ROOT / ".devcontainer/config/codex/config.toml").read_text(encoding="utf-8")

    assert 'approval_policy = "never"' in codex_toml
    assert "[mcp_servers.codex_apps]" not in codex_toml
    assert "[permissions]" not in codex_toml
    assert "allow = [" not in codex_toml


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


def test_runtime_provisions_ccusage_for_both_agents() -> None:
    """ccusage must be on PATH for both agents, not Claude only.

    The PR-body Resource Consumption section
    (scripts/session_resource_report.py) shells out to ``ccusage`` to report
    per-session token/cost. It previously installed only for the claude agent
    (``if [[ "$agent" == "claude" ]]``) and the codex devShell omitted it, so
    Codex sessions had no ccusage and the section could not be generated there.
    This guards the both-agents provisioning from regressing. Refs #1467.
    """
    flake = (REPO_ROOT / "flake.nix").read_text(encoding="utf-8")
    script = (REPO_ROOT / ".devcontainer/scripts/configure-agent-runtime.sh").read_text(encoding="utf-8")

    # The pinned ccusage derivation exists and the symlink runs at runtime.
    assert "ccusage-cli = pkgs.stdenvNoCC.mkDerivation" in flake
    assert "install_nix_binary ccusage-cli ccusage" in script

    # The install must not be gated to the claude agent any more.
    assert 'if [[ "$agent" == "claude" ]]; then\n  install_nix_binary ccusage-cli ccusage' not in script

    # Both agent devShells expose ccusage-cli so `nix develop` has it too.
    for shell_name in ("claude", "codex"):
        block = flake.split(f'{shell_name} = mkAgentShell "{shell_name}"', 1)[1].split("];", 1)[0]
        assert "agentPackages.ccusage-cli" in block, (
            f"{shell_name} devShell is missing agentPackages.ccusage-cli"
        )


def test_codex_devcontainer_permits_seccomp_for_bwrap() -> None:
    config = load_json(REPO_ROOT / ".devcontainer" / "codex" / "devcontainer.json")
    run_args = config.get("runArgs", [])
    assert isinstance(run_args, list)
    assert "--security-opt=seccomp=unconfined" in run_args
    runbook = (REPO_ROOT / "docs/runbooks/devcontainers.md").read_text(encoding="utf-8")
    assert "seccomp=unconfined" in runbook


def test_devcontainer_publish_watches_runtime_script() -> None:
    workflow = (REPO_ROOT / ".github/workflows/publish-devcontainer-images.yml").read_text(encoding="utf-8")

    assert '".devcontainer/scripts/configure-agent-runtime.sh"' in workflow


def test_runbook_documents_persistent_session_reset() -> None:
    runbook = (REPO_ROOT / "docs/runbooks/devcontainers.md").read_text(encoding="utf-8")

    for agent in AGENTS:
        assert f"podman volume rm claude-md-{agent}-session" in runbook


def test_gh_config_permission_check_script_exists_and_is_executable() -> None:
    script = REPO_ROOT / ".devcontainer/scripts/check-gh-config-permissions.sh"
    assert script.exists(), "check-gh-config-permissions.sh is missing"
    assert script.stat().st_mode & 0o111, "check-gh-config-permissions.sh is not executable"


def test_entrypoints_run_gh_config_permission_check_before_container_start() -> None:
    for agent in AGENTS:
        config = load_json(REPO_ROOT / ".devcontainer" / agent / "devcontainer.json")
        initialize = config.get("initializeCommand", "")
        assert isinstance(initialize, str)
        assert "check-gh-config-permissions.sh ${HOME}/.config/gh" in initialize
        assert initialize.index("check-gh-config-permissions.sh") < initialize.index("ensure-agent-image.sh")


def test_entrypoints_do_not_check_gh_bind_mount_modes_at_poststart() -> None:
    for agent in AGENTS:
        config = load_json(REPO_ROOT / ".devcontainer" / agent / "devcontainer.json")
        post_start = config.get("postStartCommand", "")
        assert isinstance(post_start, str)
        assert "check-gh-config-permissions.sh" not in post_start
        assert f"/home/{agent}/.config/gh" not in post_start


def test_gh_config_permission_check_is_host_platform_aware() -> None:
    script = (REPO_ROOT / ".devcontainer/scripts/check-gh-config-permissions.sh").read_text(encoding="utf-8")

    assert "stat -f '%Lp'" in script
    assert "stat -c '%a'" in script
    assert "chmod 700 $(display_path" in script
    assert "chmod 600 $(display_path" in script


def test_runbook_documents_gh_bind_mount_security() -> None:
    runbook = (REPO_ROOT / "docs/runbooks/devcontainers.md").read_text(encoding="utf-8")

    assert "chmod 700 ~/.config/gh" in runbook
    assert "chmod 600 ~/.config/gh/hosts.yml" in runbook
    assert "host-side" in runbook
    assert "gh auth status" in runbook
    assert "read-write" in runbook


def test_trivy_scan_skips_nix_store_links_hardlink_farm() -> None:
    # The published images are Trivy-scanned in publish-devcontainer-images.yml;
    # its secret scanner walks /nix/store/.links (the Nix store optimisation
    # hardlink farm) and reports findings (e.g. a HIGH "Asymmetric Private Key")
    # against the .links/<hash> path. The scan-side skip prunes that subtree
    # deterministically; building-time removal proved ineffective in the
    # published image (the rm did not persist). Refs #1473, #1348.
    workflow = (REPO_ROOT / ".github/workflows/publish-devcontainer-images.yml").read_text(encoding="utf-8")
    # The scanner now runs as a digest-pinned `docker run` (#1276), so the skip
    # is the Trivy CLI flag form rather than the trivy-action `skip-dirs:` input.
    assert "--skip-dirs nix/store/.links" in workflow

    # Guard against the reverted build-time approach silently coming back: the
    # farm must not be deleted in the Feature install (it shares inodes with the
    # real store paths and removing it would surface the secret at its real path).
    install = (REPO_ROOT / ".devcontainer/images/features/agent-user/install.sh").read_text(encoding="utf-8")
    assert "rm -rf /nix/store/.links" not in install


def test_prebuild_runs_agent_user_feature_last() -> None:
    # The agent-user Feature finalizes the agent user/group/sudoers to uid 0, so
    # it must run last in the build: after common-utils and the nix Feature have
    # populated users and the store, with no postCreateCommand running afterwards
    # in `devcontainer build`. Guard that ordering invariant for both prebuild
    # configs. Refs #1348.
    for agent in AGENTS:
        config = load_json(REPO_ROOT / ".devcontainer" / "images" / agent / "devcontainer.json")
        order = config.get("overrideFeatureInstallOrder")
        assert isinstance(order, list)
        assert order[-1] == "../features/agent-user"
