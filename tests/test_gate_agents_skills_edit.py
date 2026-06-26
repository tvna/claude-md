"""Tests for ``scripts/gate_agents_skills_edit.py``.

Verifies that:
- ``Edit`` / ``Write`` / ``MultiEdit`` / ``NotebookEdit`` calls targeting an
  APM-managed prefix (``.agents/skills/``, ``.claude/skills/``) are denied,
  across relative, ``./``-prefixed, and absolute path forms.
- Edits to any other path (including the sibling ``.agents/skillset/``) pass.
- ``Bash`` commands that WRITE to a managed path are denied; a redirection
  target, or a mutating command (cp/mv/rm/tee/sed/...) carrying a managed path.
- ``Bash`` commands that only READ a managed path, or write elsewhere, pass.
- Non-Edit/Bash tools are ignored.
- The deny reason names the blocked path and the `apm compile` change path.
- The stdin -> stdout boundary works end-to-end, and malformed stdin fails
  open (exit 0, no decision emitted).
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gate_agents_skills_edit as gase

pytestmark = pytest.mark.shard_preflight


def _deny_reason(decision: dict[str, Any]) -> str:
    return str(decision["hookSpecificOutput"]["permissionDecisionReason"])


def _is_deny(decision: dict[str, Any] | None) -> bool:
    return (
        decision is not None
        and decision.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
    )


class TestMatchedPrefix:
    @pytest.mark.parametrize(
        "path,expected",
        [
            (".agents/skills/brainstorming/SKILL.md", ".agents/skills/"),
            (".claude/skills/brainstorming/SKILL.md", ".claude/skills/"),
            ("./.agents/skills/x.md", ".agents/skills/"),
            ("././.claude/skills/x.md", ".claude/skills/"),
            ("/home/user/claude-md/.agents/skills/x.md", ".agents/skills/"),
            ("'/repo/.claude/skills/x.md'", ".claude/skills/"),
        ],
    )
    def test_managed_paths_match(self, path: str, expected: str) -> None:
        assert gase.matched_prefix(path) == expected

    @pytest.mark.parametrize(
        "path",
        [
            ".agents/skillset/x.md",  # sibling dir, not skills/
            ".claude/settings.json",
            ".agents/instructions/x.md",
            "scripts/gate_agents_skills_edit.py",
            "/repo.agents/skills/x.md",  # no slash before .agents
            "docs/standards/apm-managed-paths.md",
            "",
        ],
    )
    def test_unmanaged_paths_do_not_match(self, path: str) -> None:
        assert gase.matched_prefix(path) is None


class TestDecideEditDenied:
    @pytest.mark.parametrize(
        "tool,key,path",
        [
            ("Edit", "file_path", ".agents/skills/brainstorming/SKILL.md"),
            ("Write", "file_path", ".claude/skills/brainstorming/SKILL.md"),
            ("MultiEdit", "file_path", "./.agents/skills/x.md"),
            ("Write", "file_path", "/home/user/claude-md/.claude/skills/x.md"),
            ("NotebookEdit", "notebook_path", ".agents/skills/x.ipynb"),
        ],
    )
    def test_edit_on_managed_path_denied(self, tool: str, key: str, path: str) -> None:
        decision = gase.decide(tool, {key: path})
        assert _is_deny(decision)
        assert decision is not None
        reason = _deny_reason(decision)
        assert path in reason
        assert "apm compile" in reason


class TestDecideEditAllowed:
    @pytest.mark.parametrize(
        "path",
        [
            "scripts/foo.py",
            ".claude/settings.json",
            ".agents/skillset/x.md",
            "docs/standards/apm-managed-paths.md",
            "/tmp/claude-plans/plan.md",
        ],
    )
    def test_edit_on_other_path_passes(self, path: str) -> None:
        assert gase.decide("Edit", {"file_path": path}) is None

    def test_edit_without_path_passes(self) -> None:
        assert gase.decide("Edit", {}) is None


class TestDecideBashDenied:
    @pytest.mark.parametrize(
        "command",
        [
            # redirection targets
            "echo x > .agents/skills/brainstorming/SKILL.md",
            "cat tmpl >> .claude/skills/x.md",
            "printf '%s' y >.agents/skills/x.md",
            # mutating commands carrying a managed path argument
            "cp /tmp/x .agents/skills/x.md",
            "mv old.md .claude/skills/new.md",
            "rm .agents/skills/brainstorming/SKILL.md",
            "sed -i 's/a/b/' .claude/skills/x.md",
            "tee .agents/skills/x.md",
            "touch .claude/skills/new.md",
            "install -m644 src .agents/skills/x.md",
            # command-position aware: write in a later segment / piped to tee
            "ls && cp a .agents/skills/x.md",
            "cat tmpl | tee .claude/skills/x.md",
            # absolute path argument
            "rm /home/user/claude-md/.agents/skills/x.md",
        ],
    )
    def test_bash_write_to_managed_path_denied(self, command: str) -> None:
        decision = gase.decide("Bash", {"command": command})
        assert _is_deny(decision)
        assert decision is not None
        reason = _deny_reason(decision)
        assert "apm compile" in reason


class TestDecideBashAllowed:
    @pytest.mark.parametrize(
        "command",
        [
            # reads of a managed path are allowed
            "cat .agents/skills/brainstorming/SKILL.md",
            "grep -r foo .claude/skills/",
            "ls -la .agents/skills/",
            "head .claude/skills/x.md",
            # writes elsewhere
            "echo x > scripts/out.py",
            "cp a b",
            "rm -rf build",
            # mention only; managed path is not a write target of a mutator
            "echo '.agents/skills/x.md is generated'",
            # sibling directory
            "cp a .agents/skillset/x.md",
            # empty
            "",
            "   ",
        ],
    )
    def test_bash_safe_commands_pass(self, command: str) -> None:
        assert gase.decide("Bash", {"command": command}) is None


class TestDecideOtherTools:
    @pytest.mark.parametrize("tool_name", ["Read", "Glob", "Grep", "mcp__github__issue_write"])
    def test_other_tools_ignored(self, tool_name: str) -> None:
        assert gase.decide(tool_name, {"file_path": ".agents/skills/x.md"}) is None


class TestManagedWriteTargets:
    def test_dedupes_targets_in_order(self) -> None:
        command = "cp a .agents/skills/x.md && rm .agents/skills/x.md"
        assert gase.managed_write_targets(command) == [".agents/skills/x.md"]

    def test_no_targets_for_read(self) -> None:
        assert gase.managed_write_targets("cat .claude/skills/x.md") == []


class TestMainBoundary:
    def test_main_denies_managed_edit(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        event = {
            "tool_name": "Write",
            "tool_input": {"file_path": ".agents/skills/x.md"},
        }
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
        rc = gase.main([])
        assert rc == 0
        decision = json.loads(capsys.readouterr().out)
        assert _is_deny(decision)

    def test_main_denies_managed_bash_write(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": "cp a .claude/skills/x.md"},
        }
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
        rc = gase.main([])
        assert rc == 0
        decision = json.loads(capsys.readouterr().out)
        assert _is_deny(decision)

    def test_main_passes_through_safe_edit(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        event = {"tool_name": "Edit", "tool_input": {"file_path": "scripts/foo.py"}}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
        rc = gase.main([])
        assert rc == 0
        assert capsys.readouterr().out == ""

    def test_main_fails_open_on_malformed_stdin(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO("{not json"))
        rc = gase.main([])
        assert rc == 0
        assert capsys.readouterr().out == ""

    def test_main_ignores_missing_tool_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"foo": "bar"})))
        assert gase.main([]) == 0
