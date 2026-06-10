"""Tests for ``scripts/gate_merge_safety.py``.

Verifies that:
- A clean, mergeable PR passes through (no deny -> merge allowed).
- Every other mergeable_state (dirty/behind/blocked/unstable/unknown/draft/...)
  is denied with a state-specific remediation.
- mergeable != True is denied even when the state string is "clean".
- The gate is fail-closed: missing owner/repo/pullNumber, a missing GH_TOKEN,
  or an API failure each deny rather than pass through.
- Non-merge tools are ignored.
- merge_pull_request is wired to this gate in the generated agent configs and
  the source of truth, for both claude and codex.
- The stdin/stdout boundary works end-to-end and fails open on a parse error.
"""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import gate_merge_safety as gms
import pytest

pytestmark = pytest.mark.shard_preflight

ROOT = Path(__file__).resolve().parents[1]
CLAUDE_SETTINGS = ROOT / ".claude" / "settings.json"
CODEX_HOOKS = ROOT / ".codex" / "hooks.json"
SOURCE = ROOT / "scripts" / "agent_hooks_source.json"

_MERGE_TOOL = "mcp__github__merge_pull_request"
_VALID_INPUT = {"owner": "tvna", "repo": "claude-md", "pullNumber": 42}


def _poller(state: str, mergeable: Any = True):
    """Return a fake mergeability poller yielding a fixed state."""

    def poll(owner: str, repo: str, pr_number: str, *, token: str = "", **_: Any) -> dict[str, Any]:
        return {"mergeable": mergeable, "mergeable_state": state}

    return poll


def _deny_reason(decision: dict[str, Any] | None) -> str:
    assert decision is not None
    out = decision["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    return out["permissionDecisionReason"]


# ---------------------------------------------------------------------------
# decide() -- allow path
# ---------------------------------------------------------------------------


class TestAllow:
    def test_clean_and_mergeable_passes_through(self) -> None:
        decision = gms.decide(_MERGE_TOOL, dict(_VALID_INPUT), token="tok", poller=_poller("clean"))
        assert decision is None

    def test_pull_number_as_decimal_string_allowed(self) -> None:
        tool_input = {"owner": "tvna", "repo": "claude-md", "pullNumber": "42"}
        decision = gms.decide(_MERGE_TOOL, tool_input, token="tok", poller=_poller("clean"))
        assert decision is None

    def test_non_merge_tool_is_ignored(self) -> None:
        assert gms.decide("mcp__github__create_pull_request", {}, token="tok") is None
        assert gms.decide("Bash", {"command": "ls"}, token="tok") is None


# ---------------------------------------------------------------------------
# decide() -- deny paths (unsafe state)
# ---------------------------------------------------------------------------


class TestDenyUnsafeState:
    @pytest.mark.parametrize(
        "state",
        ["dirty", "behind", "blocked", "unstable", "draft", "unknown"],
    )
    def test_known_unsafe_states_denied_with_remediation(self, state: str) -> None:
        decision = gms.decide(_MERGE_TOOL, dict(_VALID_INPUT), token="tok", poller=_poller(state))
        reason = _deny_reason(decision)
        assert f"mergeable_state={state!r}" in reason or state in reason
        assert "tvna/claude-md#42" in reason

    def test_unrecognised_state_denied_with_generic_remediation(self) -> None:
        decision = gms.decide(_MERGE_TOOL, dict(_VALID_INPUT), token="tok", poller=_poller("has_hooks"))
        reason = _deny_reason(decision)
        assert "mergeable_state=clean" in reason  # generic remediation mentions the only allowed state

    def test_mergeable_false_denied_even_when_state_clean(self) -> None:
        decision = gms.decide(
            _MERGE_TOOL, dict(_VALID_INPUT), token="tok", poller=_poller("clean", mergeable=False)
        )
        _deny_reason(decision)

    def test_mergeable_none_denied(self) -> None:
        decision = gms.decide(
            _MERGE_TOOL, dict(_VALID_INPUT), token="tok", poller=_poller("clean", mergeable=None)
        )
        _deny_reason(decision)


# ---------------------------------------------------------------------------
# decide() -- fail-closed paths
# ---------------------------------------------------------------------------


class TestFailClosed:
    @pytest.mark.parametrize(
        "tool_input",
        [
            {},
            {"owner": "tvna", "repo": "claude-md"},
            {"owner": "tvna", "pullNumber": 42},
            {"repo": "claude-md", "pullNumber": 42},
            {"owner": "tvna", "repo": "claude-md", "pullNumber": "not-a-number"},
            {"owner": "tvna", "repo": "claude-md", "pullNumber": True},
            {"owner": "", "repo": "claude-md", "pullNumber": 42},
        ],
    )
    def test_bad_input_is_denied(self, tool_input: dict[str, Any]) -> None:
        decision = gms.decide(_MERGE_TOOL, tool_input, token="tok", poller=_poller("clean"))
        reason = _deny_reason(decision)
        assert "owner/repo/pullNumber" in reason

    def test_missing_token_is_denied(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)

        def _explode(*_: Any, **__: Any) -> dict[str, Any]:
            raise AssertionError("poller must not be called without a token")

        decision = gms.decide(_MERGE_TOOL, dict(_VALID_INPUT), token="", poller=_explode)
        reason = _deny_reason(decision)
        assert "GH_TOKEN" in reason

    def test_api_failure_is_denied(self) -> None:
        def poll(*_: Any, **__: Any) -> None:
            return None

        decision = gms.decide(_MERGE_TOOL, dict(_VALID_INPUT), token="tok", poller=poll)
        reason = _deny_reason(decision)
        assert "failed" in reason or "timed out" in reason


# ---------------------------------------------------------------------------
# Wiring: source of truth and generated configs
# ---------------------------------------------------------------------------


class TestWiring:
    def _pretooluse_matchers_invoking(self, config_path: Path, script: str) -> list[str]:
        data = json.loads(config_path.read_text(encoding="utf-8"))
        pre = data.get("hooks", {}).get("PreToolUse", [])
        matchers: list[str] = []
        for group in pre:
            if not isinstance(group, dict):
                continue
            handlers = group.get("hooks", [])
            if any(script in (h.get("command", "")) for h in handlers if isinstance(h, dict)):
                matchers.append(group.get("matcher", ""))
        return matchers

    def test_claude_settings_gate_wired_on_merge(self) -> None:
        matchers = self._pretooluse_matchers_invoking(CLAUDE_SETTINGS, "scripts/gate_merge_safety.py")
        assert any("merge_pull_request" in m for m in matchers), matchers

    def test_codex_hooks_gate_wired_on_merge(self) -> None:
        matchers = self._pretooluse_matchers_invoking(CODEX_HOOKS, "scripts/gate_merge_safety.py")
        assert any("merge_pull_request" in m for m in matchers), matchers

    def test_source_of_truth_gate_wired_for_both_agents(self) -> None:
        data = json.loads(SOURCE.read_text(encoding="utf-8"))
        agents_with_gate: set[str] = set()
        for target in data.get("targets", []):
            config = target.get("config")
            if not isinstance(config, dict):
                continue
            pre = config.get("hooks", {}).get("PreToolUse", [])
            for group in pre:
                handlers = group.get("hooks", []) if isinstance(group, dict) else []
                if any(
                    "gate_merge_safety.py" in h.get("command", "")
                    and "merge_pull_request" in group.get("matcher", "")
                    for h in handlers
                    if isinstance(h, dict)
                ):
                    agents_with_gate.add(target.get("agent", ""))
        assert {"claude", "codex"} <= agents_with_gate, agents_with_gate


# ---------------------------------------------------------------------------
# main() stdin/stdout boundary
# ---------------------------------------------------------------------------


class TestMain:
    def _run(self, payload: object, monkeypatch: pytest.MonkeyPatch) -> tuple[str, str]:
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        gms.main()
        return stdout_buf.getvalue(), stderr_buf.getvalue()

    def test_non_merge_tool_produces_no_output(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout, _ = self._run(
            {"tool_name": "mcp__github__create_pull_request", "tool_input": {}}, monkeypatch
        )
        assert stdout == ""

    def test_merge_without_token_denies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)
        stdout, _ = self._run(
            {"tool_name": _MERGE_TOOL, "tool_input": dict(_VALID_INPUT)}, monkeypatch
        )
        decision = json.loads(stdout)
        assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_merge_bad_input_denies(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout, _ = self._run({"tool_name": _MERGE_TOOL, "tool_input": {}}, monkeypatch)
        decision = json.loads(stdout)
        assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"

    def test_empty_stdin_is_handled(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        stdout_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        rc = gms.main()
        assert rc == 0
        assert stdout_buf.getvalue() == ""

    def test_malformed_json_fails_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("{bad json"))
        stdout_buf = io.StringIO()
        stderr_buf = io.StringIO()
        monkeypatch.setattr("sys.stdout", stdout_buf)
        monkeypatch.setattr("sys.stderr", stderr_buf)
        rc = gms.main()
        assert rc == 0
        assert stdout_buf.getvalue() == ""
        assert "malformed" in stderr_buf.getvalue()

    def test_missing_tool_name_fails_open(self, monkeypatch: pytest.MonkeyPatch) -> None:
        stdout, stderr = self._run({"tool_input": {}}, monkeypatch)
        assert stdout == ""
        assert "tool_name" in stderr


def test_main_block_exits_via_runpy(monkeypatch: pytest.MonkeyPatch) -> None:
    import runpy

    monkeypatch.setattr("sys.stdin", type("Input", (), {"read": lambda self: ""})())
    with pytest.raises(SystemExit) as exc_info:
        runpy.run_module("gate_merge_safety", run_name="__main__")
    assert exc_info.value.code == 0
