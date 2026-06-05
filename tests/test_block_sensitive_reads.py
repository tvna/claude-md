"""Tests for ``scripts/block_sensitive_reads.py``.

Verifies that:
- Read-tool access to credential paths (.env, *.pem, *.key, SSH/cloud creds)
  is denied.
- Bash read commands targeting those paths are denied, while a benign mention
  (no reader) and non-sensitive reads pass through.
- Non-Read/Bash tools are ignored.
- The deny reason never contains file content (only the path metadata).
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
import block_sensitive_reads as bsr

pytestmark = pytest.mark.shard_preflight


class TestIsSensitivePath:
    @pytest.mark.parametrize(
        "path",
        [
            ".env",
            ".env.local",
            ".env.production",
            "config/.env",
            "deploy/server.pem",
            "secrets/app.key",
            "credentials",
            "credentials.json",
            "/home/user/.aws/credentials",
            "~/.ssh/id_rsa",
            "/root/.ssh/id_ed25519",
            "~/.gnupg/secring.gpg",
            "~/.config/gcloud/application_default_credentials.json",
        ],
    )
    def test_sensitive_paths_match(self, path: str) -> None:
        assert bsr.is_sensitive_path(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "README.md",
            "src/app.py",
            ".github/workflows/ci.yml",
            "environment.txt",
            "docs/keyboard.md",
            "config/settings.json",
            "notes/credential-policy.md/summary.txt",
        ],
    )
    def test_benign_paths_do_not_match(self, path: str) -> None:
        assert bsr.is_sensitive_path(path) is False

    @pytest.mark.parametrize("path", ["", "   ", "'\"  "])
    def test_empty_path_is_not_sensitive(self, path: str) -> None:
        assert bsr.is_sensitive_path(path) is False

    def test_allowlisted_path_is_not_sensitive(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A path that matches a pattern but is a reviewed non-secret fixture.
        monkeypatch.setattr(
            bsr, "ALLOWLIST_PATHS", frozenset({"tests/fixtures/sample.key"})
        )
        assert bsr.is_sensitive_path("tests/fixtures/sample.key") is False
        # An unrelated *.key still matches.
        assert bsr.is_sensitive_path("secrets/other.key") is True


class TestDecideRead:
    @pytest.mark.parametrize(
        "path",
        [".env", "deploy/server.pem", "~/.ssh/id_rsa", "secrets/app.key"],
    )
    def test_read_sensitive_is_denied(self, path: str) -> None:
        decision = bsr.decide("Read", {"file_path": path})
        assert decision is not None
        assert decision["permissionDecision"] == "deny"
        assert "credential-read-guard" in decision["decisionReason"]

    @pytest.mark.parametrize("path", ["README.md", "src/app.py"])
    def test_read_benign_passes_through(self, path: str) -> None:
        assert bsr.decide("Read", {"file_path": path}) is None


class TestDecideBash:
    @pytest.mark.parametrize(
        "command",
        [
            "cat .env",
            "less deploy/server.pem",
            "grep SECRET .env.production",
            "head ~/.aws/credentials",
            "cat .env | grep TOKEN",
            "sed -n '1p' secrets/app.key",
            "base64 ~/.ssh/id_ed25519",
        ],
    )
    def test_bash_read_of_sensitive_is_denied(self, command: str) -> None:
        decision = bsr.decide("Bash", {"command": command})
        assert decision is not None
        assert decision["permissionDecision"] == "deny"

    @pytest.mark.parametrize(
        "command",
        [
            # sensitive token but no reader command -> not a read, pass through
            "echo .env",
            "ls -la ~/.ssh",
            # reader command but no sensitive target -> pass through
            "cat README.md",
            "grep TODO src/app.py",
            "git status",
            # empty / whitespace command -> no tokens, pass through
            "",
            "   ",
        ],
    )
    def test_bash_benign_passes_through(self, command: str) -> None:
        assert bsr.decide("Bash", {"command": command}) is None

    def test_bash_unbalanced_quote_falls_back_to_split(self) -> None:
        # shlex.split raises ValueError on the unbalanced quote; the whitespace
        # fallback still tokenizes the reader and the sensitive target.
        decision = bsr.decide("Bash", {"command": "cat 'app.key"})
        assert decision is not None
        assert decision["permissionDecision"] == "deny"


class TestDecideOtherTools:
    @pytest.mark.parametrize(
        "tool_name", ["Edit", "Write", "mcp__github__issue_write", "Glob"]
    )
    def test_other_tools_ignored(self, tool_name: str) -> None:
        assert bsr.decide(tool_name, {"file_path": ".env"}) is None


class TestNoContentLeak:
    def test_deny_reason_contains_path_not_content(self) -> None:
        # The guard must never open the file; the reason carries the path only.
        decision = bsr.decide("Read", {"file_path": "secrets/app.key"})
        assert decision is not None
        assert "secrets/app.key" in decision["decisionReason"]


class TestMainBoundary:
    def test_main_denies_sensitive_read(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        event = {"tool_name": "Read", "tool_input": {"file_path": ".env"}}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
        rc = bsr.main([])
        assert rc == 0
        out = capsys.readouterr().out
        decision = json.loads(out)
        assert decision["permissionDecision"] == "deny"

    def test_main_passes_through_benign(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        event = {"tool_name": "Read", "tool_input": {"file_path": "README.md"}}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
        rc = bsr.main([])
        assert rc == 0
        assert capsys.readouterr().out == ""

    def test_main_fails_open_on_malformed_stdin(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO("{not json"))
        rc = bsr.main([])
        assert rc == 0
        assert capsys.readouterr().out == ""

    def test_main_ignores_missing_tool_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"foo": "bar"})))
        assert bsr.main([]) == 0

    def test_main_tolerates_non_dict_tool_input(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        event = {"tool_name": "Read", "tool_input": "not-a-dict"}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
        rc = bsr.main([])
        assert rc == 0
        assert capsys.readouterr().out == ""
