"""Tests for ``scripts/preflight_github_secrets.py``.

Verifies that the PreToolUse gate:
- denies a GitHub MCP write whose body/title/nested field carries a secret,
- allows a clean body and an off-target tool,
- honors the ``pragma: allowlist secret`` opt-out,
- never echoes the matched secret value in the deny reason,
- folds the Codex connector tool name onto its Claude equivalent,
- fails open on malformed stdin (a hook bug must not wedge the session).
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import preflight_github_secrets as pgs

pytestmark = pytest.mark.shard_preflight

# A syntactically valid github-token literal (matches the github-token rule:
# gh[posru]_ + 36+ alnum). A dummy fixture, not a real credential.
_FAKE_TOKEN = "ghp_" + "0123456789abcdefghijklmnopqrstuvwxyzAB"


def _decision(d: dict | None) -> dict:
    assert d is not None
    return d["hookSpecificOutput"]


class TestIterStringFields:
    def test_collects_nested_strings_with_paths(self) -> None:
        fields = dict(pgs.iter_string_fields({"body": "x", "labels": ["a", "b"]}))
        assert fields["body"] == "x"
        assert fields["labels[0]"] == "a"
        assert fields["labels[1]"] == "b"

    def test_non_string_scalars_are_skipped(self) -> None:
        fields = list(pgs.iter_string_fields({"issue_number": 7, "state": "open"}))
        assert ("state", "open") in fields
        assert all(not isinstance(v, int) for _, v in fields)


class TestDecide:
    def test_secret_in_body_is_denied(self) -> None:
        hook = _decision(
            pgs.decide("mcp__github__create_pull_request", {"body": f"token: {_FAKE_TOKEN}"})
        )
        assert hook["permissionDecision"] == "deny"

    def test_clean_body_passes(self) -> None:
        assert pgs.decide("mcp__github__create_pull_request", {"body": "no secrets here"}) is None

    def test_off_target_tool_ignored(self) -> None:
        # A read tool is not in _TARGET_TOOLS even though it carries the token.
        assert pgs.decide("mcp__github__issue_read", {"body": _FAKE_TOKEN}) is None

    def test_secret_in_title_is_denied(self) -> None:
        assert pgs.decide("mcp__github__issue_write", {"title": _FAKE_TOKEN, "body": "ok"}) is not None

    def test_secret_in_nested_list_is_denied(self) -> None:
        d = pgs.decide("mcp__github__issue_write", {"body": "ok", "labels": ["fine", _FAKE_TOKEN]})
        assert d is not None

    def test_pragma_allowlist_passes(self) -> None:
        body = f"token = {_FAKE_TOKEN}  {pgs.PRAGMA_ALLOWLIST}"
        assert pgs.decide("mcp__github__issue_write", {"body": body}) is None

    def test_deny_reason_does_not_echo_secret(self) -> None:
        reason = _decision(
            pgs.decide("mcp__github__create_pull_request", {"body": _FAKE_TOKEN})
        )["permissionDecisionReason"]
        assert _FAKE_TOKEN not in reason
        assert "github-token" in reason
        assert "body" in reason

    def test_codex_connector_tool_is_denied(self) -> None:
        # canonical_github_tool folds the Codex name onto mcp__github__*.
        d = pgs.decide("mcp__codex_apps__github._create_pull_request", {"body": _FAKE_TOKEN})
        assert d is not None


class TestMain:
    def _run(self, payload: object, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        out, err = io.StringIO(), io.StringIO()
        monkeypatch.setattr("sys.stdout", out)
        monkeypatch.setattr("sys.stderr", err)
        pgs.main()
        return out.getvalue(), err.getvalue()

    def test_secret_produces_deny(self, monkeypatch: pytest.MonkeyPatch) -> None:
        out, _ = self._run(
            {"tool_name": "mcp__github__create_pull_request", "tool_input": {"body": _FAKE_TOKEN}},
            monkeypatch,
        )
        assert json.loads(out)["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_clean_produces_no_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        out, _ = self._run(
            {"tool_name": "mcp__github__create_pull_request", "tool_input": {"body": "clean"}},
            monkeypatch,
        )
        assert out == ""

    def test_malformed_json_fails_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))
        out, err = io.StringIO(), io.StringIO()
        monkeypatch.setattr("sys.stdout", out)
        monkeypatch.setattr("sys.stderr", err)
        assert pgs.main() == 0
        assert out.getvalue() == ""
        assert "malformed" in err.getvalue()
