from __future__ import annotations

import io
import json
import unittest.mock as mock
import urllib.error
import urllib.request
from typing import Any

import issue_closure_fast_path as subject
import pytest

pytestmark = pytest.mark.shard_preflight

_TOKEN = "test-token"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, data: Any, status: int = 200) -> None:
        self.status = status
        self._body = json.dumps(data).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *args: object) -> None:
        pass


def _opener(data: Any, status: int = 200) -> Any:
    resp = _FakeResponse(data, status)

    def fake(req: urllib.request.Request) -> _FakeResponse:
        return resp

    return fake


def _event(tool_name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    return {"tool_name": tool_name, "tool_input": tool_input}


def _close_input(issue_number: int | str = 187) -> dict[str, Any]:
    return {
        "owner": "tvna",
        "repo": "claude-md",
        "issue_number": issue_number,
        "state": "closed",
    }


# ---------------------------------------------------------------------------
# _extract_close_target
# ---------------------------------------------------------------------------


def test_extract_close_target_returns_tuple_on_close() -> None:
    result = subject._extract_close_target("mcp__github__issue_write", _close_input())
    assert result == ("tvna", "claude-md", 187)


def test_extract_close_target_string_issue_number() -> None:
    result = subject._extract_close_target("mcp__github__issue_write", _close_input("42"))
    assert result == ("tvna", "claude-md", 42)


def test_extract_close_target_returns_none_wrong_tool() -> None:
    assert subject._extract_close_target("mcp__github__create_pull_request", _close_input()) is None


def test_extract_close_target_returns_none_not_closed() -> None:
    inp = {**_close_input(), "state": "open"}
    assert subject._extract_close_target("mcp__github__issue_write", inp) is None


def test_extract_close_target_returns_none_missing_owner() -> None:
    inp = {**_close_input()}
    del inp["owner"]
    assert subject._extract_close_target("mcp__github__issue_write", inp) is None


def test_extract_close_target_returns_none_missing_issue_number() -> None:
    inp = {**_close_input()}
    del inp["issue_number"]
    assert subject._extract_close_target("mcp__github__issue_write", inp) is None


def test_extract_close_target_returns_none_invalid_issue_number() -> None:
    inp = {**_close_input(), "issue_number": "not-a-number"}
    assert subject._extract_close_target("mcp__github__issue_write", inp) is None


# ---------------------------------------------------------------------------
# _format_context
# ---------------------------------------------------------------------------


def test_format_context_no_prs_warns() -> None:
    msg = subject._format_context("tvna", "claude-md", 187, [])
    assert "WARNING" in msg
    assert "No merged PRs" in msg
    assert "tvna/claude-md#187" in msg


def test_format_context_one_pr_ok() -> None:
    prs = [{"number": 200, "title": "fix: resolve #187", "html_url": "https://github.com/tvna/claude-md/pull/200", "closed_at": "2026-05-01T10:00:00Z"}]
    msg = subject._format_context("tvna", "claude-md", 187, prs)
    assert "FAST-PATH OK" in msg
    assert "https://github.com/tvna/claude-md/pull/200" in msg
    assert "fix: resolve #187" in msg


def test_format_context_multiple_prs_lists_all() -> None:
    prs = [
        {"number": 200, "title": "PR A", "html_url": "https://github.com/tvna/claude-md/pull/200", "closed_at": "2026-04-01"},
        {"number": 201, "title": "PR B", "html_url": "https://github.com/tvna/claude-md/pull/201", "closed_at": "2026-04-02"},
    ]
    msg = subject._format_context("tvna", "claude-md", 187, prs)
    assert "2 merged PR" in msg
    assert "pull/200" in msg
    assert "pull/201" in msg


# ---------------------------------------------------------------------------
# decide
# ---------------------------------------------------------------------------


def test_decide_returns_advisory_no_prs() -> None:
    out = subject.decide(
        "mcp__github__issue_write",
        _close_input(),
        opener=_opener({"items": []}),
        token=_TOKEN,
    )
    assert out is not None
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "WARNING" in ctx


def test_decide_returns_advisory_one_pr() -> None:
    pr = {"number": 200, "title": "fix: close #187", "html_url": "https://github.com/tvna/claude-md/pull/200", "closed_at": "2026-05-01T10:00:00Z"}

    out = subject.decide(
        "mcp__github__issue_write",
        _close_input(),
        opener=_opener({"items": [pr]}),
        token=_TOKEN,
    )
    assert out is not None
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "FAST-PATH OK" in ctx
    assert "pull/200" in ctx


def test_decide_returns_none_on_api_error() -> None:
    out = subject.decide(
        "mcp__github__issue_write",
        _close_input(),
        opener=_opener({}, status=422),
        token=_TOKEN,
    )
    assert out is None


def test_decide_returns_none_for_non_close_tool() -> None:
    out = subject.decide(
        "mcp__github__create_pull_request",
        {"owner": "tvna", "repo": "claude-md"},
        opener=_opener({"items": []}),
        token=_TOKEN,
    )
    assert out is None


def test_decide_returns_none_for_open_state() -> None:
    inp = {**_close_input(), "state": "open"}
    out = subject.decide(
        "mcp__github__issue_write",
        inp,
        opener=_opener({"items": []}),
        token=_TOKEN,
    )
    assert out is None


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def test_main_writes_json_on_close(capsys: pytest.CaptureFixture[str]) -> None:
    pr = {"number": 99, "title": "fix: #187", "html_url": "https://github.com/tvna/claude-md/pull/99", "closed_at": "2026-05-01"}
    event = _event("mcp__github__issue_write", _close_input())

    original_decide = subject.decide

    def patched_decide(tool_name: str, tool_input: dict[str, Any], **kw: Any) -> dict[str, Any] | None:
        return original_decide(
            tool_name,
            tool_input,
            opener=_opener({"items": [pr]}),
            token=_TOKEN,
        )

    with mock.patch.object(subject, "decide", patched_decide), \
         mock.patch("sys.stdin", io.StringIO(json.dumps(event))):
        subject.main()

    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert "hookSpecificOutput" in data
    assert "FAST-PATH OK" in data["hookSpecificOutput"]["additionalContext"]


def test_main_empty_stdin_no_output(capsys: pytest.CaptureFixture[str]) -> None:
    with mock.patch("sys.stdin", io.StringIO("")):
        subject.main()
    captured = capsys.readouterr()
    assert captured.out == ""


def test_main_malformed_json_no_crash(capsys: pytest.CaptureFixture[str]) -> None:
    with mock.patch("sys.stdin", io.StringIO("{bad json")):
        subject.main()
    captured = capsys.readouterr()
    assert captured.out == ""


def test_main_non_dict_event_no_output(capsys: pytest.CaptureFixture[str]) -> None:
    with mock.patch("sys.stdin", io.StringIO("[1, 2, 3]")):
        subject.main()
    assert capsys.readouterr().out == ""


def test_main_non_dict_tool_input_treated_as_empty(capsys: pytest.CaptureFixture[str]) -> None:
    event = json.dumps({"tool_name": "mcp__github__close_issue", "tool_input": "not-a-dict"})
    with mock.patch("sys.stdin", io.StringIO(event)):
        subject.main()
    assert capsys.readouterr().out == ""


class TestSearchMergedPrs:
    def test_exception_returns_none(self) -> None:
        def bad_opener(req: urllib.request.Request) -> None:
            raise OSError("network error")

        result = subject._search_merged_prs("o", "r", 1, opener=bad_opener, token=_TOKEN)
        assert result is None

    def test_non_200_returns_none(self) -> None:
        result = subject._search_merged_prs(
            "o", "r", 1,
            opener=_opener({}, status=404),
            token=_TOKEN,
        )
        assert result is None

    def test_items_parsed_correctly(self) -> None:
        obj = {"number": 5, "title": "t", "html_url": "u", "closed_at": "2026-01-01"}
        result = subject._search_merged_prs(
            "o", "r", 1,
            opener=_opener({"items": [obj]}),
            token=_TOKEN,
        )
        assert result is not None
        assert len(result) == 1
        assert result[0]["number"] == 5

    def test_non_dict_items_skipped(self) -> None:
        result = subject._search_merged_prs(
            "o", "r", 1,
            opener=_opener({"items": ["not-a-dict", {"number": 2}]}),
            token=_TOKEN,
        )
        assert result is not None
        assert len(result) == 1

    def test_no_token_returns_none(self) -> None:
        result = subject._search_merged_prs("o", "r", 1, token="")
        assert result is None


class TestExtractCloseTarget:
    def test_missing_repo_returns_none(self) -> None:
        result = subject._extract_close_target("mcp__github__update_issue", {"owner": "o", "state": "closed"})
        assert result is None
