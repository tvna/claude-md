"""Tests for ``scripts/scan_hook_coverage_drift.py``.

Refs #615. Verifies that the drift gate correctly detects when a Claude
hook script is absent from Codex coverage and passes when all hooks are
covered or allowlisted.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import scan_hook_coverage_drift as shcd

pytestmark = pytest.mark.shard_preflight

REPO_ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------------------
# collect_claude_hooks
# ---------------------------------------------------------------------------


def _make_claude_settings(hooks: dict[str, Any]) -> dict[str, Any]:
    return {"hooks": hooks}


def _make_codex_hooks(hooks: dict[str, Any]) -> dict[str, Any]:
    return {"hooks": hooks}


def _claude_group(command: str, matcher: str | None = None) -> dict[str, Any]:
    group: dict[str, Any] = {"hooks": [{"type": "command", "command": command}]}
    if matcher is not None:
        group["matcher"] = matcher
    return group


def _codex_group(command: str, matcher: str | None = None) -> dict[str, Any]:
    group: dict[str, Any] = {"hooks": [{"type": "command", "command": command}]}
    if matcher is not None:
        group["matcher"] = matcher
    return group


def test_collect_claude_hooks_extracts_script_references() -> None:
    settings = _make_claude_settings(
        {
            "SessionStart": [_claude_group("python3 scripts/plan_language_context.py")],
            "PreToolUse": [],
            "PostToolUse": [],
        }
    )
    hooks = shcd.collect_claude_hooks(settings)
    assert shcd.HookEntry(event="SessionStart", script="plan_language_context") in hooks


def test_collect_claude_hooks_skips_non_script_commands() -> None:
    settings = _make_claude_settings(
        {
            "SessionStart": [_claude_group("scripts/install-uv.sh")],
            "PreToolUse": [],
            "PostToolUse": [],
        }
    )
    hooks = shcd.collect_claude_hooks(settings)
    assert not hooks


def test_collect_claude_hooks_skips_superpowers() -> None:
    settings = _make_claude_settings(
        {
            "SessionStart": [
                {
                    "matcher": "startup",
                    "hooks": [{"type": "command", "command": "scripts/some_apm.py"}],
                    "_apm_source": "superpowers",
                }
            ],
            "PreToolUse": [],
            "PostToolUse": [],
        }
    )
    hooks = shcd.collect_claude_hooks(settings)
    assert not hooks


def test_collect_claude_hooks_multiple_events() -> None:
    settings = _make_claude_settings(
        {
            "SessionStart": [_claude_group("python3 scripts/plan_language_context.py")],
            "PreToolUse": [_claude_group("python3 scripts/preflight_non_ascii.py")],
            "PostToolUse": [_claude_group("python3 scripts/plan_approval_gate.py")],
        }
    )
    hooks = shcd.collect_claude_hooks(settings)
    assert shcd.HookEntry(event="SessionStart", script="plan_language_context") in hooks
    assert shcd.HookEntry(event="PreToolUse", script="preflight_non_ascii") in hooks
    assert shcd.HookEntry(event="PostToolUse", script="plan_approval_gate") in hooks


# ---------------------------------------------------------------------------
# collect_codex_hooks
# ---------------------------------------------------------------------------


def test_collect_codex_hooks_extracts_script_references() -> None:
    data = _make_codex_hooks(
        {
            "SessionStart": [_codex_group("python3 scripts/plan_language_context.py")],
            "PreToolUse": [],
            "PostToolUse": [],
        }
    )
    hooks = shcd.collect_codex_hooks(data)
    assert shcd.HookEntry(event="SessionStart", script="plan_language_context") in hooks


# ---------------------------------------------------------------------------
# find_drift
# ---------------------------------------------------------------------------


def test_find_drift_empty_when_fully_covered() -> None:
    claude = {shcd.HookEntry(event="SessionStart", script="plan_language_context")}
    codex = {shcd.HookEntry(event="SessionStart", script="plan_language_context")}
    assert shcd.find_drift(claude, codex, {}) == []


def test_find_drift_detects_missing_hook() -> None:
    claude = {shcd.HookEntry(event="PreToolUse", script="preflight_non_ascii")}
    codex: set[shcd.HookEntry] = set()
    missing = shcd.find_drift(claude, codex, {})
    assert len(missing) == 1
    assert missing[0].script == "preflight_non_ascii"


def test_find_drift_allowlist_suppresses_missing() -> None:
    claude = {shcd.HookEntry(event="PostToolUse", script="plan_approval_gate")}
    codex: set[shcd.HookEntry] = set()
    allowlist = {"plan_approval_gate": "No Codex Write tool equivalent."}
    assert shcd.find_drift(claude, codex, allowlist) == []


def test_find_drift_codex_script_in_different_event_is_still_missing() -> None:
    """Coverage in a different event does not count as coverage."""
    claude = {shcd.HookEntry(event="PreToolUse", script="preflight_non_ascii")}
    codex = {shcd.HookEntry(event="PostToolUse", script="preflight_non_ascii")}
    missing = shcd.find_drift(claude, codex, {})
    assert len(missing) == 1


def test_find_drift_codex_extra_hooks_are_ignored() -> None:
    claude: set[shcd.HookEntry] = set()
    codex = {shcd.HookEntry(event="PreToolUse", script="preflight_codex_github_footer")}
    assert shcd.find_drift(claude, codex, {}) == []


# ---------------------------------------------------------------------------
# collect_installers
# ---------------------------------------------------------------------------


def test_collect_installers_extracts_installer_names() -> None:
    settings = _make_claude_settings(
        {
            "SessionStart": [
                _claude_group("scripts/install-uv.sh"),
                _claude_group("scripts/install-bun.sh"),
            ],
            "PreToolUse": [],
            "PostToolUse": [],
        }
    )
    assert shcd.collect_installers(settings) == {"install-uv", "install-bun"}


def test_collect_installers_ignores_non_installer_shell_scripts() -> None:
    settings = _make_claude_settings(
        {
            "SessionStart": [_claude_group("scripts/session_uv_local_pin.sh")],
            "PreToolUse": [],
            "PostToolUse": [],
        }
    )
    assert shcd.collect_installers(settings) == set()


# ---------------------------------------------------------------------------
# find_installer_parity_violations (three-way parity, per-agent exemptions)
# ---------------------------------------------------------------------------


def _by_agent(claude: set[str], codex: set[str], devin: set[str]) -> dict[str, set[str]]:
    return {"claude": claude, "codex": codex, "devin": devin}


def test_parity_clean_when_installer_on_all_three_agents() -> None:
    shared = {"install-uv", "install-bun"}
    assert shcd.find_installer_parity_violations(_by_agent(shared, shared, shared), {}) == []


def test_parity_flags_bun_style_claude_only_miss() -> None:
    """Reproduces the original bun gap: present in claude, missing from codex+devin."""
    violations = shcd.find_installer_parity_violations(
        _by_agent({"install-uv", "install-bun"}, {"install-uv"}, {"install-uv"}), {}
    )
    assert len(violations) == 1
    assert "install-bun" in violations[0]
    assert "codex" in violations[0] and "devin" in violations[0]


def test_parity_flags_installer_missing_from_devin_only() -> None:
    """Devin is checked directly: a broken mirror (codex has it, devin does not) fails."""
    violations = shcd.find_installer_parity_violations(
        _by_agent({"install-uv"}, {"install-uv"}, set()), {}
    )
    assert len(violations) == 1
    assert "install-uv" in violations[0] and "devin" in violations[0]


def test_parity_exemption_with_matching_agents_suppresses_gap() -> None:
    exemptions = {
        "install-rtk": {"agents": ["claude"], "rationale": "claude-only by design", "issue": 1}
    }
    violations = shcd.find_installer_parity_violations(
        _by_agent({"install-uv", "install-rtk"}, {"install-uv"}, {"install-uv"}), exemptions
    )
    assert violations == []


def test_parity_stale_exemption_fails_when_declared_set_mismatches_reality() -> None:
    """Declared claude-only but actually wired everywhere -> stale exemption fails."""
    shared = {"install-uv", "install-rtk"}
    exemptions = {
        "install-rtk": {"agents": ["claude"], "rationale": "claude-only by design", "issue": 1}
    }
    violations = shcd.find_installer_parity_violations(_by_agent(shared, shared, shared), exemptions)
    assert len(violations) == 1
    assert "stale" in violations[0] and "install-rtk" in violations[0]


def test_parity_dangling_exemption_for_unwired_installer_fails() -> None:
    exemptions = {
        "install-ghost": {"agents": ["claude"], "rationale": "x", "issue": 1}
    }
    shared = {"install-uv"}
    violations = shcd.find_installer_parity_violations(_by_agent(shared, shared, shared), exemptions)
    assert any("install-ghost" in v and "no agent" in v for v in violations)


def test_validate_exemption_rejects_malformed_specs() -> None:
    assert shcd.validate_exemption("install-x", "just a string")  # not a mapping
    assert shcd.validate_exemption("install-x", {"agents": [], "rationale": "r", "issue": 1})
    assert shcd.validate_exemption(
        "install-x", {"agents": ["mars"], "rationale": "r", "issue": 1}
    )  # unknown agent
    assert shcd.validate_exemption(
        "install-x", {"agents": ["claude", "codex", "devin"], "rationale": "r", "issue": 1}
    )  # all agents -> no exemption needed
    assert shcd.validate_exemption(
        "install-x", {"agents": ["claude"], "rationale": "  ", "issue": 1}
    )  # blank rationale
    assert shcd.validate_exemption(
        "install-x", {"agents": ["claude"], "rationale": "r", "issue": "1"}
    )  # issue not int
    assert shcd.validate_exemption(
        "install-x", {"agents": ["claude"], "rationale": "r", "issue": True}
    )  # bool is not a valid issue int
    # A well-formed strict-subset contract validates.
    assert shcd.validate_exemption(
        "install-x", {"agents": ["claude"], "rationale": "r", "issue": 1}
    ) == ""


def test_real_configs_are_parity_clean_with_shipped_exemptions() -> None:
    """The shipped configs + exemptions must keep three-way parity clean."""
    by_agent = {
        "claude": shcd.collect_installers(
            json.loads((REPO_ROOT / ".claude" / "settings.json").read_text(encoding="utf-8"))
        ),
        "codex": shcd.collect_installers(
            json.loads((REPO_ROOT / ".codex" / "hooks.json").read_text(encoding="utf-8"))
        ),
        "devin": shcd.collect_installers(
            json.loads((REPO_ROOT / ".devin" / "hooks.v1.json").read_text(encoding="utf-8"))
        ),
    }
    assert (
        shcd.find_installer_parity_violations(by_agent, shcd.INSTALLER_PARITY_EXEMPTIONS) == []
    )
    # install-bun is deliberately NOT exempted, so a regression to claude-only
    # would be caught.
    assert "install-bun" not in shcd.INSTALLER_PARITY_EXEMPTIONS


# ---------------------------------------------------------------------------
# cmd_verify via fixtures
# ---------------------------------------------------------------------------


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data), encoding="utf-8")


def _verify_paths(tmp_path: Path) -> tuple[Path, Path, Path]:
    """Return (claude, codex, devin) fixture paths under *tmp_path*."""
    return (
        tmp_path / "settings.json",
        tmp_path / "hooks.json",
        tmp_path / "hooks.v1.json",
    )


def _run_verify(claude_path: Path, codex_path: Path, devin_path: Path) -> int:
    return shcd.main(
        [
            "verify",
            "--claude",
            str(claude_path),
            "--codex",
            str(codex_path),
            "--devin",
            str(devin_path),
        ]
    )


def test_cmd_verify_passes_on_full_coverage(tmp_path: Path) -> None:
    claude_path, codex_path, devin_path = _verify_paths(tmp_path)
    _write_json(
        claude_path,
        _make_claude_settings(
            {
                "SessionStart": [_claude_group("python3 scripts/plan_language_context.py")],
                "PreToolUse": [],
                "PostToolUse": [],
            }
        ),
    )
    codex_data = _make_codex_hooks(
        {
            "SessionStart": [_codex_group("python3 scripts/plan_language_context.py")],
            "PreToolUse": [],
            "PostToolUse": [],
        }
    )
    _write_json(codex_path, codex_data)
    _write_json(devin_path, codex_data)

    assert _run_verify(claude_path, codex_path, devin_path) == 0


def test_cmd_verify_fails_on_missing_hook(tmp_path: Path) -> None:
    claude_path, codex_path, devin_path = _verify_paths(tmp_path)
    _write_json(
        claude_path,
        _make_claude_settings(
            {
                "SessionStart": [],
                "PreToolUse": [
                    _claude_group(
                        "python3 scripts/preflight_non_ascii.py",
                        matcher="^mcp__github__create_pull_request$",
                    )
                ],
                "PostToolUse": [],
            }
        ),
    )
    empty = _make_codex_hooks({"SessionStart": [], "PreToolUse": [], "PostToolUse": []})
    _write_json(codex_path, empty)
    _write_json(devin_path, empty)

    assert _run_verify(claude_path, codex_path, devin_path) == 1


def test_cmd_verify_passes_with_allowlisted_gap(tmp_path: Path) -> None:
    claude_path, codex_path, devin_path = _verify_paths(tmp_path)
    _write_json(
        claude_path,
        _make_claude_settings(
            {
                "SessionStart": [],
                "PreToolUse": [],
                "PostToolUse": [_claude_group("python3 scripts/plan_approval_gate.py")],
            }
        ),
    )
    empty = _make_codex_hooks({"SessionStart": [], "PreToolUse": [], "PostToolUse": []})
    _write_json(codex_path, empty)
    _write_json(devin_path, empty)

    assert _run_verify(claude_path, codex_path, devin_path) == 0


def test_cmd_verify_fails_on_claude_only_installer(tmp_path: Path) -> None:
    """Regression for #1607: install-bun wired into claude only must fail.

    Reproduces the original miss where install-bun.sh was provisioned for the
    claude agent only while codex/devin lacked the Mermaid-gate runtime, and
    scan_hook_coverage_drift still passed because shell installers were never
    compared.
    """
    claude_path, codex_path, devin_path = _verify_paths(tmp_path)
    _write_json(
        claude_path,
        _make_claude_settings(
            {
                "SessionStart": [
                    _claude_group("scripts/install-uv.sh"),
                    _claude_group("scripts/install-bun.sh"),
                ],
                "PreToolUse": [],
                "PostToolUse": [],
            }
        ),
    )
    # codex + devin carry install-uv only, so install-uv stays at parity and
    # install-bun is the lone claude-only gap the gate must flag.
    uv_only = _make_codex_hooks(
        {
            "SessionStart": [_codex_group("scripts/install-uv.sh")],
            "PreToolUse": [],
            "PostToolUse": [],
        }
    )
    _write_json(codex_path, uv_only)
    _write_json(devin_path, uv_only)

    assert _run_verify(claude_path, codex_path, devin_path) == 1


def test_cmd_verify_passes_when_installer_shared_across_agents(tmp_path: Path) -> None:
    """The same installer wired into all three agents passes the parity check."""
    claude_path, codex_path, devin_path = _verify_paths(tmp_path)
    shared = _make_claude_settings(
        {
            "SessionStart": [
                _claude_group("scripts/install-uv.sh"),
                _claude_group("scripts/install-bun.sh"),
            ],
            "PreToolUse": [],
            "PostToolUse": [],
        }
    )
    for path in (claude_path, codex_path, devin_path):
        _write_json(path, shared)

    assert _run_verify(claude_path, codex_path, devin_path) == 0


# ---------------------------------------------------------------------------
# Real config files
# ---------------------------------------------------------------------------


def test_real_config_files_pass_drift_check() -> None:
    """Current .claude, .codex, and .devin configs must pass the gate."""
    rc = shcd.main(
        [
            "verify",
            "--claude",
            str(REPO_ROOT / ".claude" / "settings.json"),
            "--codex",
            str(REPO_ROOT / ".codex" / "hooks.json"),
            "--devin",
            str(REPO_ROOT / ".devin" / "hooks.v1.json"),
        ]
    )
    assert rc == 0


# ---------------------------------------------------------------------------
# _collect_hooks() defensive isinstance guards
# ---------------------------------------------------------------------------


def test_collect_claude_hooks_non_dict_hooks_section() -> None:
    settings: dict[str, object] = {"hooks": "not-a-dict"}
    assert shcd.collect_claude_hooks(settings) == set()


def test_collect_claude_hooks_non_list_event_groups() -> None:
    settings: dict[str, object] = {"hooks": {"SessionStart": "not-a-list", "PreToolUse": [], "PostToolUse": []}}
    assert shcd.collect_claude_hooks(settings) == set()


def test_collect_claude_hooks_non_dict_group_entry() -> None:
    settings: dict[str, object] = {"hooks": {"SessionStart": ["not-a-dict"], "PreToolUse": [], "PostToolUse": []}}
    assert shcd.collect_claude_hooks(settings) == set()


def test_collect_claude_hooks_non_list_handlers() -> None:
    settings: dict[str, object] = {
        "hooks": {
            "SessionStart": [{"hooks": "not-a-list"}],
            "PreToolUse": [],
            "PostToolUse": [],
        }
    }
    assert shcd.collect_claude_hooks(settings) == set()


def test_collect_claude_hooks_non_dict_handler_entry() -> None:
    settings: dict[str, object] = {
        "hooks": {
            "SessionStart": [{"hooks": ["not-a-dict"]}],
            "PreToolUse": [],
            "PostToolUse": [],
        }
    }
    assert shcd.collect_claude_hooks(settings) == set()


def test_collect_claude_hooks_non_str_command() -> None:
    settings: dict[str, object] = {
        "hooks": {
            "SessionStart": [{"hooks": [{"type": "command", "command": 123}]}],
            "PreToolUse": [],
            "PostToolUse": [],
        }
    }
    assert shcd.collect_claude_hooks(settings) == set()


def test_main_block_exits_via_runpy(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy
    import sys

    monkeypatch.setattr(sys, "argv", ["scan_hook_coverage_drift", "--help"])
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("scan_hook_coverage_drift", run_name="__main__")
    assert exc_info.value.code == 0
