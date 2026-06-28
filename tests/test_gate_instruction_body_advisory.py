"""Tests for scripts/gate_instruction_body_advisory.py."""

from __future__ import annotations

import gate_instruction_body_advisory as adv
import pytest

pytestmark = pytest.mark.shard_preflight


def test_build_advice_none_when_no_instruction_paths() -> None:
    assert adv.build_advice(["scripts/foo.py", "tests/test_foo.py"]) is None
    assert adv.build_advice([]) is None


def test_build_advice_text_delta_for_generated_mirror_only() -> None:
    advice = adv.build_advice(["CLAUDE.md", "scripts/foo.py"])
    assert advice is not None
    assert "## Text delta" in advice
    # No .apm/instructions/** source staged -> no growth-ack mention.
    assert "text-growth-ack:" not in advice
    assert "CLAUDE.md" in advice


def test_build_advice_growth_ack_when_source_staged() -> None:
    advice = adv.build_advice(
        [".apm/instructions/master.instructions.md", "CLAUDE.md", "AGENTS.md"]
    )
    assert advice is not None
    assert "## Text delta" in advice
    assert "text-growth-ack:" in advice


def test_build_advice_is_ascii() -> None:
    advice = adv.build_advice([".apm/instructions/master.instructions.md"])
    assert advice is not None
    advice.encode("ascii")  # raises if non-ASCII slips in


def test_decide_silent_for_non_bash() -> None:
    assert adv.decide({"tool_name": "Edit", "tool_input": {}}) is None


def test_decide_silent_for_non_commit_bash() -> None:
    event = {"tool_name": "Bash", "tool_input": {"command": "git status"}}
    assert adv.decide(event) is None


def test_decide_silent_when_commit_tree_plumbing(monkeypatch: pytest.MonkeyPatch) -> None:
    # git commit-tree must not trip the detector.
    monkeypatch.setattr(adv, "_staged_files", lambda: ["CLAUDE.md"])
    event = {"tool_name": "Bash", "tool_input": {"command": "git commit-tree x"}}
    assert adv.decide(event) is None


def test_decide_emits_advisory_for_instruction_commit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        adv, "_staged_files", lambda: [".apm/instructions/master.instructions.md"]
    )
    event = {
        "tool_name": "Bash",
        "tool_input": {"command": "git add -A && git commit -m x"},
    }
    decision = adv.decide(event)
    assert decision is not None
    out = decision["hookSpecificOutput"]
    # Non-blocking: additionalContext, no permissionDecision.
    assert out["hookEventName"] == "PreToolUse"
    assert "permissionDecision" not in out
    assert "## Text delta" in out["additionalContext"]
    assert "text-growth-ack:" in out["additionalContext"]


def test_decide_silent_when_commit_has_no_instruction_files(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(adv, "_staged_files", lambda: ["scripts/foo.py"])
    event = {"tool_name": "Bash", "tool_input": {"command": "git commit -m x"}}
    assert adv.decide(event) is None


def test_staged_files_fail_open_on_git_error() -> None:
    def boom(*_a, **_kw):
        raise OSError("no git")

    assert adv._staged_files(runner=boom) == []
