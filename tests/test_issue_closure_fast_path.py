from __future__ import annotations

import io
import json
import subprocess
import unittest.mock as mock
from typing import Any

import issue_closure_fast_path as subject
import pytest

pytestmark = pytest.mark.shard_preflight


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _completed(data: Any, returncode: int = 0) -> subprocess.CompletedProcess[str]:
    if isinstance(data, str):
        stdout = data
    else:
        # jq --jq outputs one JSON object per line
        if isinstance(data, list):
            stdout = "\n".join(json.dumps(item) for item in data)
        else:
            stdout = json.dumps(data)
    return subprocess.CompletedProcess(["gh"], returncode, stdout=stdout, stderr="")


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
    def runner(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        return _completed("", returncode=0)

    out = subject.decide("mcp__github__issue_write", _close_input(), runner=runner)
    assert out is not None
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "WARNING" in ctx


def test_decide_returns_advisory_one_pr() -> None:
    pr = {"number": 200, "title": "fix: close #187", "html_url": "https://github.com/tvna/claude-md/pull/200", "closed_at": "2026-05-01T10:00:00Z"}

    def runner(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        return _completed([pr])

    out = subject.decide("mcp__github__issue_write", _close_input(), runner=runner)
    assert out is not None
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert "FAST-PATH OK" in ctx
    assert "pull/200" in ctx


def test_decide_returns_none_on_api_error() -> None:
    def runner(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:
        return _completed("", returncode=1)

    out = subject.decide("mcp__github__issue_write", _close_input(), runner=runner)
    assert out is None


def test_decide_returns_none_for_non_close_tool() -> None:
    def runner(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:  # pragma: no cover
        return _completed([])

    out = subject.decide("mcp__github__create_pull_request", {"owner": "tvna", "repo": "claude-md"}, runner=runner)
    assert out is None


def test_decide_returns_none_for_open_state() -> None:
    def runner(cmd: list[str], **kw: Any) -> subprocess.CompletedProcess[str]:  # pragma: no cover
        return _completed([])

    inp = {**_close_input(), "state": "open"}
    out = subject.decide("mcp__github__issue_write", inp, runner=runner)
    assert out is None


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def test_main_writes_json_on_close(capsys: pytest.CaptureFixture[str]) -> None:
    pr = {"number": 99, "title": "fix: #187", "html_url": "https://github.com/tvna/claude-md/pull/99", "closed_at": "2026-05-01"}
    event = _event("mcp__github__issue_write", _close_input())

    original_decide = subject.decide

    def patched_decide(tool_name: str, tool_input: dict[str, Any], **kw: Any) -> dict[str, Any] | None:
        def runner(cmd: list[str], **inner_kw: Any) -> subprocess.CompletedProcess[str]:
            return _completed([pr])
        return original_decide(tool_name, tool_input, runner=runner)

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
