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
    # PATH binary; no repo path to resolve.
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


# ---------------------------------------------------------------------------
# _wrap_config defensive type checks (lines 112, 115, 118, 121)
# ---------------------------------------------------------------------------


def test_wrap_config_skips_non_list_groups() -> None:
    # hooks value is a string, not a list -> line 112 continue.
    result = gen._wrap_config({"hooks": {"SessionStart": "not-a-list"}})
    assert result["hooks"]["SessionStart"] == "not-a-list"


def test_wrap_config_skips_non_dict_group() -> None:
    # Group in list is a string, not a dict -> line 115 continue.
    result = gen._wrap_config({"hooks": {"PreToolUse": ["not-a-dict"]}})
    assert result["hooks"]["PreToolUse"] == ["not-a-dict"]


def test_wrap_config_skips_non_list_handlers() -> None:
    # Group is a dict but 'hooks' value is a string -> line 118 continue.
    result = gen._wrap_config({"hooks": {"PreToolUse": [{"hooks": "not-a-list"}]}})
    assert result["hooks"]["PreToolUse"][0]["hooks"] == "not-a-list"


def test_wrap_config_skips_non_dict_handler() -> None:
    # Handler in hooks list is a string -> line 121 continue.
    result = gen._wrap_config({"hooks": {"PreToolUse": [{"hooks": ["not-a-dict"]}]}})
    assert result["hooks"]["PreToolUse"][0]["hooks"] == ["not-a-dict"]


# ---------------------------------------------------------------------------
# render_targets input validation (lines 142, 147, 150, 154, 162)
# ---------------------------------------------------------------------------


def test_render_rejects_missing_targets_key() -> None:
    # 'targets' absent -> not a list -> line 142 raise ValueError.
    with pytest.raises(ValueError, match="non-empty list"):
        gen.render_targets({})


def test_render_rejects_non_dict_target_entry() -> None:
    # Target entry is a number, not a mapping -> line 147 raise ValueError.
    with pytest.raises(ValueError, match="must be a mapping"):
        gen.render_targets({"targets": [42]})


def test_render_rejects_non_string_agent() -> None:
    # 'agent' key is an int -> line 150 raise ValueError.
    with pytest.raises(ValueError, match="missing a string"):
        gen.render_targets({"targets": [{"agent": 42, "path": "x.json"}]})


def test_render_rejects_non_dict_config_value() -> None:
    # 'config' is a string -> line 154 raise ValueError.
    with pytest.raises(ValueError, match="must be a mapping"):
        gen.render_targets({"targets": [{"agent": "x", "config": "str", "path": "p"}]})


def test_render_rejects_target_without_string_path() -> None:
    # Target has no 'path' key -> line 162 raise ValueError.
    with pytest.raises(ValueError, match="missing a string 'path'"):
        gen.render_targets({"targets": [{"agent": "x", "config": {"hooks": {}}}]})


# ---------------------------------------------------------------------------
# _load_source error paths (lines 179-181, 184-186, 188-189)
# ---------------------------------------------------------------------------


def test_main_unreadable_source_exits_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # SOURCE does not exist -> OSError -> lines 179-181 -> SystemExit(2).
    monkeypatch.setattr(gen, "SOURCE", tmp_path / "nonexistent.json")
    with pytest.raises(SystemExit) as exc_info:
        gen.main([])
    assert exc_info.value.code == 2


def test_main_invalid_json_source_exits_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # SOURCE is not valid JSON -> lines 184-186 -> SystemExit(2).
    bad = tmp_path / "source.json"
    bad.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(gen, "SOURCE", bad)
    with pytest.raises(SystemExit) as exc_info:
        gen.main([])
    assert exc_info.value.code == 2


def test_main_non_dict_source_exits_2(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # SOURCE top-level is a list -> lines 188-189 -> SystemExit(2).
    bad = tmp_path / "source.json"
    bad.write_text("[1, 2, 3]", encoding="utf-8")
    monkeypatch.setattr(gen, "SOURCE", bad)
    with pytest.raises(SystemExit) as exc_info:
        gen.main([])
    assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# main() error and write paths (lines 204-206, 214-217, 223-225)
# ---------------------------------------------------------------------------


def test_main_render_value_error_returns_2(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    # render_targets raises ValueError -> lines 204-206 -> return 2.
    def _raise(_: object) -> None:
        raise ValueError("bad targets")

    monkeypatch.setattr(gen, "render_targets", _raise)
    rc = gen.main([])
    assert rc == 2
    assert "bad targets" in capsys.readouterr().err


def test_main_check_missing_rendered_file_returns_1(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # --check with a rendered path that doesn't exist -> lines 214-217 -> return 1.
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps({"targets": [{"agent": "x", "config": {"hooks": {}}, "path": "x.json"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(gen, "SOURCE", source)
    monkeypatch.setattr(gen, "REPO_ROOT", tmp_path)
    rc = gen.main(["--check"])
    assert rc == 1


def test_main_write_mode_creates_files(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    # Without --check, main writes rendered configs (lines 223-225).
    source = tmp_path / "source.json"
    source.write_text(
        json.dumps({"targets": [{"agent": "x", "config": {"hooks": {}}, "path": "x.json"}]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(gen, "SOURCE", source)
    monkeypatch.setattr(gen, "REPO_ROOT", tmp_path)
    rc = gen.main([])
    assert rc == 0
    assert (tmp_path / "x.json").exists()


# ---------------------------------------------------------------------------
# Permissions single-source compiler (RFC #2022 A-2)
# ---------------------------------------------------------------------------


def test_build_claude_permissions_matches_committed_settings() -> None:
    """The compiled block equals the committed .claude/settings.json permissions."""
    source = _load_source()
    committed = json.loads((ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert gen.build_claude_permissions(source) == committed["permissions"]


def test_build_claude_permissions_returns_none_without_section() -> None:
    assert gen.build_claude_permissions({"targets": []}) is None


def test_build_claude_permissions_concatenates_in_kind_order() -> None:
    source = {
        "permissions": {
            "allow": [{"intent": "a", "claude": ["Write(x)"], "claude_only": True, "rationale": "r", "issue": "u"}],
            "deny": [{"intent": "d", "claude": ["Bash(y)", "Bash(z)"], "realized_by": "scripts/h.py", "issue": "u"}],
        }
    }
    assert gen.build_claude_permissions(source) == {"allow": ["Write(x)"], "deny": ["Bash(y)", "Bash(z)"]}


def test_build_claude_permissions_rejects_non_mapping_section() -> None:
    with pytest.raises(ValueError, match="must be a mapping"):
        gen.build_claude_permissions({"permissions": ["nope"]})


def test_build_claude_permissions_rejects_intent_without_realization() -> None:
    bad = {"permissions": {"deny": [{"intent": "x", "claude": ["Bash(x)"], "issue": "u"}]}}
    with pytest.raises(ValueError, match="realized_by"):
        gen.build_claude_permissions(bad)


def test_build_claude_permissions_rejects_claude_only_without_rationale() -> None:
    bad = {"permissions": {"allow": [{"intent": "x", "claude": ["Write(x)"], "claude_only": True, "issue": "u"}]}}
    with pytest.raises(ValueError, match="rationale"):
        gen.build_claude_permissions(bad)


def test_build_claude_permissions_requires_issue() -> None:
    bad = {"permissions": {"deny": [{"intent": "x", "claude": ["Bash(x)"], "realized_by": "scripts/y.py"}]}}
    with pytest.raises(ValueError, match="issue"):
        gen.build_claude_permissions(bad)


def test_build_claude_permissions_rejects_unknown_kind() -> None:
    # A typo'd kind ('denny' instead of 'deny') must fail loudly, not silently
    # drop the guard (Codex review on PR #2037).
    bad = {"permissions": {"denny": [
        {"intent": "x", "claude": ["Bash(x)"], "realized_by": "scripts/y.py", "issue": "u"}]}}
    with pytest.raises(ValueError, match="unknown kind"):
        gen.build_claude_permissions(bad)


def test_build_claude_permissions_allows_underscore_doc_keys() -> None:
    # The '_comment' doc key is exempt from the unknown-kind guard.
    source = {"permissions": {"_comment": "note", "deny": [
        {"intent": "x", "claude": ["Bash(x)"], "realized_by": "scripts/y.py", "issue": "u"}]}}
    assert gen.build_claude_permissions(source) == {"deny": ["Bash(x)"]}


def test_build_claude_permissions_rejects_empty_claude_rules() -> None:
    bad = {"permissions": {"deny": [{"intent": "x", "claude": [], "realized_by": "scripts/y.py", "issue": "u"}]}}
    with pytest.raises(ValueError, match="non-empty list"):
        gen.build_claude_permissions(bad)


def test_rendered_claude_places_permissions_after_schema() -> None:
    source = _load_source()
    rendered = gen.render_targets(source)
    data = json.loads(rendered[".claude/settings.json"])
    assert list(data)[:2] == ["$schema", "permissions"]
    assert data["permissions"] == gen.build_claude_permissions(source)


def test_codex_devin_have_no_permissions_block() -> None:
    rendered = gen.render_targets(_load_source())
    for path in (".codex/hooks.json", ".devin/hooks.v1.json"):
        assert "permissions" not in json.loads(rendered[path])


def test_with_permissions_is_noop_when_none() -> None:
    config = {"$schema": "s", "hooks": {}}
    assert gen._with_permissions(config, None) is config


def test_with_permissions_leads_when_no_schema() -> None:
    result = gen._with_permissions({"hooks": {}}, {"deny": ["Bash(x)"]})
    assert next(iter(result)) == "permissions"


# ---------------------------------------------------------------------------
# Cross-platform permission parity gate (the reconcile-with-Codex drift gate)
# ---------------------------------------------------------------------------


def test_permission_parity_passes_on_committed_tree() -> None:
    source = _load_source()
    assert gen.verify_permission_parity(source, gen.render_targets(source)) == []


def test_permission_parity_ignores_source_without_permissions() -> None:
    assert gen.verify_permission_parity({"targets": []}, {}) == []


def test_permission_parity_skips_claude_only_intents() -> None:
    source = {"permissions": {"allow": [
        {"intent": "x", "claude": ["Write(x)"], "claude_only": True, "rationale": "r", "issue": "u"}]}}
    assert gen.verify_permission_parity(source, {".codex/hooks.json": "{}", ".devin/hooks.v1.json": "{}"}) == []


def test_permission_parity_flags_unwired_realized_by() -> None:
    source = {"permissions": {"deny": [
        {"intent": "x", "claude": ["Bash(x)"], "realized_by": "scripts/not_wired.py", "issue": "u"}]}}
    rendered = {".codex/hooks.json": "{}", ".devin/hooks.v1.json": "{}"}
    problems = gen.verify_permission_parity(source, rendered)
    assert len(problems) == 2
    assert all("not_wired.py" in p for p in problems)


def test_permission_parity_passes_when_realized_by_wired_in_both() -> None:
    source = {"permissions": {"deny": [
        {"intent": "x", "claude": ["Bash(x)"], "realized_by": "scripts/h.py", "issue": "u"}]}}
    wired = json.dumps({"hooks": {"PreToolUse": [{"hooks": [{"command": "python3 scripts/h.py"}]}]}})
    assert gen.verify_permission_parity(source, {".codex/hooks.json": wired, ".devin/hooks.v1.json": wired}) == []


def test_main_check_fails_on_permission_parity_drift(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """--check fails when a deny intent's realized_by hook is not wired cross-platform."""
    source_obj = {
        "permissions": {"deny": [
            {"intent": "x", "claude": ["Bash(x)"], "realized_by": "scripts/missing.py", "issue": "u"}]},
        "targets": [
            {"agent": "claude", "path": ".claude/settings.json", "config": {"$schema": "s", "hooks": {}}},
            {"agent": "codex", "path": ".codex/hooks.json", "config": {"hooks": {}}},
            {"agent": "devin", "path": ".devin/hooks.v1.json", "mirror": "codex"},
        ],
    }
    source = tmp_path / "source.json"
    source.write_text(json.dumps(source_obj), encoding="utf-8")
    monkeypatch.setattr(gen, "SOURCE", source)
    monkeypatch.setattr(gen, "REPO_ROOT", tmp_path)
    # Materialize the rendered tree so the stale check passes and ONLY parity fails.
    for rel, text in gen.render_targets(source_obj).items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    assert gen.main(["--check"]) == 1


def test_main_check_passes_when_parity_holds(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A realized_by hook wired into codex (and mirrored devin) passes --check."""
    source_obj = {
        "permissions": {"deny": [
            {"intent": "x", "claude": ["Bash(x)"], "realized_by": "scripts/wired.py", "issue": "u"}]},
        "targets": [
            {"agent": "claude", "path": ".claude/settings.json", "config": {"$schema": "s", "hooks": {}}},
            {
                "agent": "codex",
                "path": ".codex/hooks.json",
                "config": {"hooks": {"PreToolUse": [{"hooks": [{"command": "python3 scripts/wired.py"}]}]}},
            },
            {"agent": "devin", "path": ".devin/hooks.v1.json", "mirror": "codex"},
        ],
    }
    source = tmp_path / "source.json"
    source.write_text(json.dumps(source_obj), encoding="utf-8")
    monkeypatch.setattr(gen, "SOURCE", source)
    monkeypatch.setattr(gen, "REPO_ROOT", tmp_path)
    for rel, text in gen.render_targets(source_obj).items():
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text, encoding="utf-8")
    assert gen.main(["--check"]) == 0
