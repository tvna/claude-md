"""Tests for ``scripts/gate_irreversible_bash.py``.

Verifies that:
- High-confidence irreversible Bash idioms (rm -rf, git push --force, find
  -delete, dd of=, mkfs, shred, truncate -s) are denied.
- Benign and safer variants (rm without both flags, git push, git push
  --force-with-lease, a quoted mention, non-destructive readers) pass through.
- The ``# irreversible-ack`` opt-in marker allows an otherwise-denied command.
- Detection is command-position aware across shell segments.
- Non-Bash tools are ignored.
- The stdin -> stdout boundary works end-to-end, and malformed stdin fails
  open (exit 0, no decision emitted).
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gate_irreversible_bash as gib

pytestmark = pytest.mark.shard_preflight


class TestDecideDenied:
    @pytest.mark.parametrize(
        "command",
        [
            "rm -rf build",
            "rm -fr /tmp/scratch",
            "rm -r -f dir",
            "rm --recursive --force dir",
            "/bin/rm -rf node_modules",
            "git push --force origin main",
            "git push -f",
            "find . -name '*.tmp' -delete",
            "dd if=/dev/zero of=/dev/sda",
            "mkfs.ext4 /dev/sdb1",
            "shred -u secret.txt",
            "truncate -s 0 app.log",
            # command-position aware: destructive op in a later segment
            "ls && rm -rf build",
            "echo cleaning | rm -rf y",
        ],
    )
    def test_irreversible_is_denied(self, command: str) -> None:
        decision = gib.decide("Bash", {"command": command})
        assert decision is not None
        assert decision["permissionDecision"] == "deny"
        assert "irreversible-op-guard" in decision["decisionReason"]

    def test_deny_reason_offers_ack_and_dryrun(self) -> None:
        decision = gib.decide("Bash", {"command": "rm -rf build"})
        assert decision is not None
        reason = decision["decisionReason"]
        assert "# irreversible-ack" in reason
        assert "dry-run" in reason


class TestDecideAllowed:
    @pytest.mark.parametrize(
        "command",
        [
            # rm without BOTH recursive and force
            "rm file.txt",
            "rm -r dir",
            "rm -f file",
            # safer / non-forced git push
            "git push origin main",
            "git push --force-with-lease origin main",
            # mention only; leading command is echo, not rm
            "echo 'rm -rf /'",
            'echo "git push --force"',
            # non-destructive readers / listers
            "ls -la",
            "cat README.md",
            "git status",
            "find . -name '*.py'",
            "dd if=/dev/zero bs=1M count=1",
            # empty / whitespace
            "",
            "   ",
        ],
    )
    def test_safe_commands_pass_through(self, command: str) -> None:
        assert gib.decide("Bash", {"command": command}) is None

    @pytest.mark.parametrize(
        "command",
        [
            "rm -rf build # irreversible-ack",
            "git push --force origin main  # irreversible-ack",
        ],
    )
    def test_ack_marker_allows(self, command: str) -> None:
        assert gib.decide("Bash", {"command": command}) is None


class TestDecideOtherTools:
    @pytest.mark.parametrize(
        "tool_name", ["Read", "Edit", "Write", "mcp__github__issue_write", "Glob"]
    )
    def test_other_tools_ignored(self, tool_name: str) -> None:
        assert gib.decide(tool_name, {"command": "rm -rf /"}) is None


class TestMainBoundary:
    def test_main_denies_irreversible(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        event = {"tool_name": "Bash", "tool_input": {"command": "rm -rf build"}}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
        rc = gib.main([])
        assert rc == 0
        decision = json.loads(capsys.readouterr().out)
        assert decision["permissionDecision"] == "deny"

    def test_main_passes_through_safe(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        event = {"tool_name": "Bash", "tool_input": {"command": "ls -la"}}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
        rc = gib.main([])
        assert rc == 0
        assert capsys.readouterr().out == ""

    def test_main_fails_open_on_malformed_stdin(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO("{not json"))
        rc = gib.main([])
        assert rc == 0
        assert capsys.readouterr().out == ""

    def test_main_ignores_missing_tool_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"foo": "bar"})))
        assert gib.main([]) == 0

    def test_main_tolerates_non_dict_tool_input(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        event = {"tool_name": "Bash", "tool_input": "not-a-dict"}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
        rc = gib.main([])
        assert rc == 0
        assert capsys.readouterr().out == ""
