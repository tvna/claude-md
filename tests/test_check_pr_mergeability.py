from __future__ import annotations

import json
import urllib.request
from typing import Any

import check_pr_mergeability as subject
import pytest

pytestmark = pytest.mark.shard_preflight

_TOKEN = "test-token"


# ---------------------------------------------------------------------------
# Fake opener helpers
# ---------------------------------------------------------------------------


class _FakeResponse:
    """Minimal urllib response-like object for testing."""

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
    """Return a fake opener that always responds with *data*."""
    resp = _FakeResponse(data, status)

    def fake(req: urllib.request.Request) -> _FakeResponse:
        return resp

    return fake


def _seq_opener(responses: list[Any], status: int = 200) -> Any:
    """Return a fake opener that cycles through *responses* in order."""
    queue = list(responses)

    def fake(req: urllib.request.Request) -> _FakeResponse:
        data = queue.pop(0) if queue else responses[-1]
        return _FakeResponse(data, status)

    return fake


def _url_opener(url_map: dict[str, Any]) -> Any:
    """Return a fake opener dispatching based on URL substrings."""

    def fake(req: urllib.request.Request) -> _FakeResponse:
        for pattern, data in url_map.items():
            if pattern in req.full_url:
                return _FakeResponse(data)
        raise ValueError(f"unexpected URL: {req.full_url}")

    return fake


def _pr_event(tool_name: str, response: Any, tool_input: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "tool_name": tool_name,
        "tool_response": response,
        "tool_input": tool_input or {"owner": "tvna", "repo": "claude-md"},
    }


# ---------------------------------------------------------------------------
# _extract_pr_info
# ---------------------------------------------------------------------------


def test_extract_pr_info_from_url_in_response() -> None:
    event = _pr_event(
        "mcp__github__create_pull_request",
        {"html_url": "https://github.com/tvna/claude-md/pull/99"},
    )
    owner, repo, number = subject._extract_pr_info(event)

    assert owner == "tvna"
    assert repo == "claude-md"
    assert number == "99"


def test_extract_pr_info_from_number_in_response() -> None:
    event = _pr_event(
        "mcp__github__create_pull_request",
        {"number": 42},
    )
    owner, repo, number = subject._extract_pr_info(event)

    assert number == "42"
    assert owner == "tvna"
    assert repo == "claude-md"


def test_extract_pr_info_returns_none_when_missing() -> None:
    event = _pr_event("mcp__github__create_pull_request", {})
    owner, repo, number = subject._extract_pr_info(event)

    assert number is None


# ---------------------------------------------------------------------------
# decide_post_tool_use — target tool filtering
# ---------------------------------------------------------------------------


def test_decide_ignores_non_target_tool() -> None:
    event = _pr_event("mcp__github__update_pull_request", {"number": 1})
    assert subject.decide_post_tool_use(event) is None


def test_decide_handles_update_pull_request_branch() -> None:
    event = _pr_event(
        "mcp__github__update_pull_request_branch",
        {"html_url": "https://github.com/tvna/claude-md/pull/10"},
    )
    result = subject.decide_post_tool_use(
        event,
        opener=_opener({"mergeable": True, "mergeable_state": "clean"}),
        token=_TOKEN,
        sleeper=lambda _: None,
    )

    assert result is not None
    ctx = result["hookSpecificOutput"]["additionalContext"]
    assert "clean" in ctx


# ---------------------------------------------------------------------------
# decide_post_tool_use — mergeability states
# ---------------------------------------------------------------------------


def test_decide_returns_dirty_warning() -> None:
    event = _pr_event(
        "mcp__github__create_pull_request",
        {"html_url": "https://github.com/tvna/claude-md/pull/5"},
    )
    result = subject.decide_post_tool_use(
        event,
        opener=_opener({"mergeable": False, "mergeable_state": "dirty"}),
        token=_TOKEN,
        sleeper=lambda _: None,
    )

    assert result is not None
    ctx = result["hookSpecificOutput"]["additionalContext"]
    assert "MERGE CONFLICT" in ctx
    assert "dirty" in ctx


def test_decide_returns_clean_ok() -> None:
    event = _pr_event(
        "mcp__github__create_pull_request",
        {"html_url": "https://github.com/tvna/claude-md/pull/7"},
    )
    result = subject.decide_post_tool_use(
        event,
        opener=_opener({"mergeable": True, "mergeable_state": "clean"}),
        token=_TOKEN,
        sleeper=lambda _: None,
    )

    assert result is not None
    ctx = result["hookSpecificOutput"]["additionalContext"]
    assert "clean" in ctx
    assert "MERGE CONFLICT" not in ctx


def test_decide_returns_blocked_advisory() -> None:
    event = _pr_event(
        "mcp__github__create_pull_request",
        {"html_url": "https://github.com/tvna/claude-md/pull/8"},
    )
    result = subject.decide_post_tool_use(
        event,
        opener=_opener({"mergeable": True, "mergeable_state": "blocked"}),
        token=_TOKEN,
        sleeper=lambda _: None,
    )

    assert result is not None
    ctx = result["hookSpecificOutput"]["additionalContext"]
    assert "blocked" in ctx


def test_decide_polls_until_mergeable_non_null() -> None:
    responses = [
        {"mergeable": None, "mergeable_state": "unknown"},
        {"mergeable": None, "mergeable_state": "unknown"},
        {"mergeable": True, "mergeable_state": "clean"},
    ]
    sleeps: list[float] = []

    event = _pr_event(
        "mcp__github__create_pull_request",
        {"html_url": "https://github.com/tvna/claude-md/pull/9"},
    )
    result = subject.decide_post_tool_use(
        event,
        opener=_seq_opener(responses),
        token=_TOKEN,
        sleeper=sleeps.append,
    )

    assert len(sleeps) == 2
    assert result is not None
    assert "clean" in result["hookSpecificOutput"]["additionalContext"]


def test_decide_times_out_gracefully() -> None:
    event = _pr_event(
        "mcp__github__create_pull_request",
        {"html_url": "https://github.com/tvna/claude-md/pull/11"},
    )
    result = subject.decide_post_tool_use(
        event,
        opener=_opener({"mergeable": None, "mergeable_state": "unknown"}),
        token=_TOKEN,
        sleeper=lambda _: None,
    )

    assert result is not None
    ctx = result["hookSpecificOutput"]["additionalContext"]
    assert "timed out" in ctx


def test_decide_skips_when_no_pr_number() -> None:
    event = _pr_event("mcp__github__create_pull_request", {})
    result = subject.decide_post_tool_use(event, token=_TOKEN)

    assert result is not None
    ctx = result["hookSpecificOutput"]["additionalContext"]
    assert "skipped" in ctx


def test_decide_skips_when_api_fails() -> None:
    event = _pr_event(
        "mcp__github__create_pull_request",
        {"html_url": "https://github.com/tvna/claude-md/pull/12"},
    )
    result = subject.decide_post_tool_use(
        event,
        opener=_opener({}, status=422),
        token=_TOKEN,
        sleeper=lambda _: None,
    )

    assert result is not None
    ctx = result["hookSpecificOutput"]["additionalContext"]
    assert "failed" in ctx


# ---------------------------------------------------------------------------
# run_session_start
# ---------------------------------------------------------------------------


def _pr_list_entry(number: int) -> dict[str, Any]:
    return {
        "number": number,
        "html_url": f"https://github.com/tvna/claude-md/pull/{number}",
        "user": {"login": "tvna"},
        "head": {
            "sha": "abc123",
            "repo": {"name": "claude-md", "owner": {"login": "tvna"}},
        },
    }


def test_session_start_emits_banner_for_dirty_pr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(subject, "_detect_repo", lambda: "tvna/claude-md")

    pr_list = [_pr_list_entry(55)]
    url_map = {
        "api.github.com/user": {"login": "tvna"},
        "/pulls?": pr_list,
        "/pulls/55": {"mergeable": False, "mergeable_state": "dirty"},
    }

    subject.run_session_start(
        opener=_url_opener(url_map),
        token=_TOKEN,
        sleeper=lambda _: None,
    )

    out = capsys.readouterr().out
    assert "MERGE CONFLICT WARNING" in out
    assert "pull/55" in out


def test_session_start_silent_when_all_clean(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(subject, "_detect_repo", lambda: "tvna/claude-md")

    pr_list = [_pr_list_entry(60)]
    url_map = {
        "api.github.com/user": {"login": "tvna"},
        "/pulls?": pr_list,
        "/pulls/60": {"mergeable": True, "mergeable_state": "clean"},
    }

    subject.run_session_start(
        opener=_url_opener(url_map),
        token=_TOKEN,
        sleeper=lambda _: None,
    )

    out = capsys.readouterr().out
    assert out == ""


def test_session_start_emits_banner_for_behind_pr(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(subject, "_detect_repo", lambda: "tvna/claude-md")

    pr_list = [_pr_list_entry(70)]
    url_map = {
        "api.github.com/user": {"login": "tvna"},
        "/pulls?": pr_list,
        "/pulls/70": {"mergeable": True, "mergeable_state": "behind"},
    }

    subject.run_session_start(
        opener=_url_opener(url_map),
        token=_TOKEN,
        sleeper=lambda _: None,
    )

    out = capsys.readouterr().out
    assert "OUT-OF-DATE WARNING" in out
    assert "pull/70" in out
    assert "MERGE CONFLICT" not in out


def test_session_start_emits_both_banners_for_dirty_and_behind(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(subject, "_detect_repo", lambda: "tvna/claude-md")

    pr_list = [_pr_list_entry(71), _pr_list_entry(72)]
    states: dict[str, str] = {"71": "dirty", "72": "behind"}

    def smart_opener(req: urllib.request.Request) -> _FakeResponse:
        url = req.full_url
        if "api.github.com/user" in url:
            return _FakeResponse({"login": "tvna"})
        if "/pulls?" in url:
            return _FakeResponse(pr_list)
        for num, state in states.items():
            if f"/pulls/{num}" in url:
                mergeable = state != "dirty"
                return _FakeResponse({"mergeable": mergeable, "mergeable_state": state})
        raise ValueError(f"unexpected URL: {url}")

    subject.run_session_start(
        opener=smart_opener,
        token=_TOKEN,
        sleeper=lambda _: None,
    )

    out = capsys.readouterr().out
    assert "MERGE CONFLICT WARNING" in out
    assert "OUT-OF-DATE WARNING" in out
    assert "pull/71" in out
    assert "pull/72" in out


def test_session_start_silent_when_no_open_prs(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(subject, "_detect_repo", lambda: "tvna/claude-md")

    url_map = {
        "api.github.com/user": {"login": "tvna"},
        "/pulls?": [],
    }

    subject.run_session_start(
        opener=_url_opener(url_map),
        token=_TOKEN,
        sleeper=lambda _: None,
    )

    out = capsys.readouterr().out
    assert out == ""


def test_session_start_silent_when_no_token(capsys: pytest.CaptureFixture[str]) -> None:
    subject.run_session_start(token="", sleeper=lambda _: None)
    assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# main() entry point
# ---------------------------------------------------------------------------


def test_main_session_start_mode(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    called: list[bool] = []

    def fake_run_session_start(**_: Any) -> None:
        called.append(True)

    monkeypatch.setattr(subject, "run_session_start", fake_run_session_start)

    rc = subject.main(["session-start"])
    assert rc == 0
    assert called == [True]


def test_main_posttooluse_mode_emits_json(monkeypatch: pytest.MonkeyPatch) -> None:
    import io

    event = _pr_event(
        "mcp__github__create_pull_request",
        {"html_url": "https://github.com/tvna/claude-md/pull/77"},
    )
    stdin_data = json.dumps(event)

    output: list[str] = []
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin_data))
    monkeypatch.setattr("sys.stdout", type("FakeOut", (), {"write": lambda self, s: output.append(s)})())
    monkeypatch.setattr(
        subject,
        "_poll_mergeability",
        lambda *a, **kw: {"mergeable": True, "mergeable_state": "clean"},
    )

    rc = subject.main([])
    assert rc == 0
    assert output
    parsed = json.loads("".join(output))
    assert "hookSpecificOutput" in parsed
