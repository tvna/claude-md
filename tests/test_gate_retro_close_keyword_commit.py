"""Tests for ``scripts/gate_retro_close_keyword_commit.py``.

Verifies that a ``git commit`` whose message closes a retrospective issue is
denied before the commit is made, while non-retro closes, keyword-free
commits, the ack marker, and every fail-open boundary pass through. Refs
#2114, #2103.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import gate_retro_close_keyword_commit as g

pytestmark = pytest.mark.shard_preflight

_RETRO_TITLE = "chore(auto-retro): review PR #2103 repair loops"
_IMPL_TITLE = "feat(harness): add a gate"


def _event(command: str) -> dict[str, object]:
    return {"tool_name": "Bash", "tool_input": {"command": command}}


def _decide(
    command: str,
    *,
    titles: dict[int, str] | None = None,
    repo: str | None = "tvna/claude-md",
    token: str | None = "tok",  # noqa: S107 -- test stub value, not a secret
) -> dict[str, Any] | None:
    titles = titles or {}
    return g.decide(
        _event(command),
        repo_getter=lambda: repo,
        token_getter=lambda: token,
        title_getter=lambda _o, _r, n: titles.get(n),
    )


# ---------------------------------------------------------------------------
# message / ref extraction
# ---------------------------------------------------------------------------
class TestClosingRefs:
    @pytest.mark.parametrize(
        "command, expected",
        [
            ('git commit -m "Closes #2011"', [2011]),
            ('git commit -m "subject" -m "body Closes #2011"', [2011]),
            ('git commit -mCloses\\ #2011', [2011]),
            ('git commit --message="Fixes #2011"', [2011]),
            ('git commit --message "Resolves #2011"', [2011]),
            ('git commit -am "Closes #2011"', [2011]),
            ('git add -A && git commit -m "Closes #2011"', [2011]),
            ('git commit -m "no keyword #2011"', []),
            ('git commit -m "Refs #2011"', []),
            ('git commit -m "fixes the bug, see #2011"', []),
            ('git status', []),
        ],
    )
    def test_closing_refs(self, command: str, expected: list[int]) -> None:
        assert g._closing_refs(command) == expected

    def test_segment_stops_at_operator(self) -> None:
        # A trailing chained command's flags must not leak into the message.
        assert g._closing_refs('git commit -m "x" && echo "Closes #2011"') == []


# ---------------------------------------------------------------------------
# decide
# ---------------------------------------------------------------------------
class TestDecide:
    def test_deny_when_message_closes_retro(self) -> None:
        decision = _decide('git commit -m "Closes #2011"', titles={2011: _RETRO_TITLE})
        assert decision is not None
        reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
        assert "#2011" in reason
        assert g._ACK_MARKER in reason

    def test_none_when_closes_non_retro(self) -> None:
        assert _decide('git commit -m "Closes #2119"', titles={2119: _IMPL_TITLE}) is None

    def test_none_when_no_closing_keyword(self) -> None:
        assert _decide('git commit -m "ordinary subject"', titles={2011: _RETRO_TITLE}) is None

    def test_none_when_ack_marker(self) -> None:
        assert (
            _decide('git commit -m "Closes #2011" # retro-close-ack', titles={2011: _RETRO_TITLE})
            is None
        )

    def test_none_when_not_bash(self) -> None:
        assert g.decide(
            {"tool_name": "Edit", "tool_input": {}},
            repo_getter=lambda: "tvna/claude-md",
            token_getter=lambda: "t",
            title_getter=lambda _o, _r, _n: _RETRO_TITLE,
        ) is None

    def test_none_when_not_git_commit(self) -> None:
        assert _decide('git log -m "Closes #2011"', titles={2011: _RETRO_TITLE}) is None

    def test_none_when_commit_tree(self) -> None:
        assert _decide('git commit-tree -m "Closes #2011"', titles={2011: _RETRO_TITLE}) is None

    def test_fail_open_when_no_token(self) -> None:
        assert _decide('git commit -m "Closes #2011"', titles={2011: _RETRO_TITLE}, token=None) is None

    def test_fail_open_when_no_repo(self) -> None:
        assert _decide('git commit -m "Closes #2011"', titles={2011: _RETRO_TITLE}, repo=None) is None

    def test_fail_open_when_title_lookup_fails(self) -> None:
        # title_getter returns None -> lookup failed -> fail-open.
        assert _decide('git commit -m "Closes #2011"', titles={}) is None

    def test_deny_only_for_retro_among_mixed(self) -> None:
        decision = _decide(
            'git commit -m "Closes #2119" -m "Closes #2011"',
            titles={2119: _IMPL_TITLE, 2011: _RETRO_TITLE},
        )
        assert decision is not None
        reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
        assert "#2011" in reason
        assert "#2119" not in reason


# ---------------------------------------------------------------------------
# stdin/stdout boundary
# ---------------------------------------------------------------------------
class TestMain:
    def test_fail_open_on_bad_stdin(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(sys, "stdin", io.StringIO("not json"))
        assert g.main([]) == 0
        assert capsys.readouterr().out == ""

    def test_pass_through_on_non_bash(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        event = {"tool_name": "Read", "tool_input": {}}
        monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(event)))
        assert g.main([]) == 0
        assert capsys.readouterr().out == ""
