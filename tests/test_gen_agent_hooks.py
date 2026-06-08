"""Tests for the agent hook config generator.

Covers the working-directory-independence wrapper logic and the render/drift
contract that keeps ``.claude/settings.json``, ``.codex/hooks.json`` and
``.devin/hooks.v1.json`` in sync with ``scripts/agent_hooks_source.json``.
"""

from __future__ import annotations

import json
from pathlib import Path

import gen_agent_hooks as gen
import pytest

pytestmark = pytest.mark.shard_preflight

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "scripts" / "agent_hooks_source.json"
GENERATED = (
    ".claude/settings.json",
    ".codex/hooks.json",
    ".devin/hooks.v1.json",
)


def _load_source() -> dict[str, object]:
    return json.loads(SOURCE.read_text(encoding="utf-8"))


# --- wrapper unit behaviour -------------------------------------------------


def test_wrap_command_prefixes_repo_script() -> None:
    wrapped = gen.wrap_command("python3 scripts/check_hooks_path.py")
    assert wrapped == gen.HOOK_CWD_PREFIX + "python3 scripts/check_hooks_path.py"


def test_wrap_command_handles_bare_shell_script() -> None:
    assert gen.wrap_command("scripts/install-uv.sh") == gen.HOOK_CWD_PREFIX + "scripts/install-uv.sh"


def test_wrap_command_is_idempotent() -> None:
    once = gen.wrap_command("python3 scripts/foo.py")
    assert gen.wrap_command(once) == once


def test_wrap_command_leaves_non_script_commands_untouched() -> None:
    # PATH binary -- no repo path to resolve.
    assert gen.wrap_command("rtk hook claude") == "rtk hook claude"
    # APM/superpowers passthrough is already location-independent.
    plugin = '"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd" session-start'
    assert gen.wrap_command(plugin) == plugin


def test_wrap_command_never_uses_claude_project_dir() -> None:
    """Refs #783: $CLAUDE_PROJECT_DIR is unset in the FleetView remote env."""
    assert "CLAUDE_PROJECT_DIR" not in gen.HOOK_CWD_PREFIX


def test_unwrap_is_inverse_of_wrap() -> None:
    for command in (
        "python3 scripts/foo.py",
        "scripts/install-uv.sh",
        "uv run python3 scripts/gen_mcp_json.py",
        "python3 scripts/check_pr_mergeability.py session-start",
    ):
        assert gen.unwrap_command(gen.wrap_command(command)) == command


def test_unwrap_leaves_unwrapped_commands_untouched() -> None:
    assert gen.unwrap_command("python3 scripts/foo.py") == "python3 scripts/foo.py"


def test_command_needs_wrap() -> None:
    assert gen.command_needs_wrap("python3 scripts/foo.py")
    assert gen.command_needs_wrap("scripts/install-uv.sh")
    assert not gen.command_needs_wrap("rtk hook claude")
    assert not gen.command_needs_wrap('"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd" x')


# --- render / mirror contract ----------------------------------------------


def test_render_targets_covers_all_generated_files() -> None:
    rendered = gen.render_targets(_load_source())
    assert set(rendered) == set(GENERATED)


def test_render_devin_mirrors_codex() -> None:
    rendered = gen.render_targets(_load_source())
    assert rendered[".devin/hooks.v1.json"] == rendered[".codex/hooks.json"]


def test_every_rendered_script_command_is_wrapped() -> None:
    rendered = gen.render_targets(_load_source())
    for text in rendered.values():
        data = json.loads(text)
        for groups in data["hooks"].values():
            for group in groups:
                for handler in group.get("hooks", []):
                    command = handler.get("command", "")
                    if gen.command_needs_wrap(gen.unwrap_command(command)):
                        assert command.startswith(gen.HOOK_CWD_PREFIX), command


def test_render_is_idempotent() -> None:
    once = gen.render_targets(_load_source())
    # Re-running the generator over already-wrapped commands must not double-wrap.
    for text in once.values():
        data = json.loads(text)
        for groups in data["hooks"].values():
            for group in groups:
                for handler in group.get("hooks", []):
                    command = handler.get("command", "")
                    assert gen.HOOK_CWD_PREFIX not in gen.unwrap_command(command)


# --- drift gate (the recurrence-prevention contract) ------------------------


def test_committed_configs_match_render() -> None:
    """The committed agent configs must equal a fresh render of the source.

    This is the same invariant ``gen_agent_hooks.py --check`` enforces in
    pre-commit and CI: it fails the moment a hook config is hand-edited (and
    so could ship a CWD-relative command) instead of regenerated.
    """
    rendered = gen.render_targets(_load_source())
    for rel, text in rendered.items():
        assert (ROOT / rel).read_text(encoding="utf-8") == text, (
            f"{rel} is out of sync with scripts/agent_hooks_source.json; " f"run python3 scripts/gen_agent_hooks.py"
        )


def test_check_passes_on_committed_tree() -> None:
    assert gen.main(["--check"]) == 0


def test_render_rejects_target_without_config_or_mirror() -> None:
    bad = {"targets": [{"agent": "x", "path": ".x.json"}]}
    with pytest.raises(ValueError, match="neither 'config' nor 'mirror'"):
        gen.render_targets(bad)


def test_render_rejects_mirror_to_unknown_agent() -> None:
    bad = {
        "targets": [
            {"agent": "codex", "path": ".codex/hooks.json", "config": {"hooks": {}}},
            {"agent": "devin", "path": ".devin/hooks.v1.json", "mirror": "nope"},
        ]
    }
    with pytest.raises(ValueError, match="mirror"):
        gen.render_targets(bad)
