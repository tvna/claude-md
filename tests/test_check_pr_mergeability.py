from __future__ import annotations

import io
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


# ---------------------------------------------------------------------------
# Raw-body / raising opener helpers (for REST-layer error paths)
# ---------------------------------------------------------------------------


class _RawResponse:
    """Response-like object returning arbitrary (possibly non-JSON) bytes."""

    def __init__(self, body: bytes, status: int = 200) -> None:
        self.status = status
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> _RawResponse:
        return self

    def __exit__(self, *args: object) -> None:
        pass


def _raw_opener(body: bytes, status: int = 200) -> Any:
    def fake(req: urllib.request.Request) -> _RawResponse:
        return _RawResponse(body, status)

    return fake


def _raising_opener() -> Any:
    def fake(req: urllib.request.Request) -> _RawResponse:
        raise ValueError("boom")  # not an HTTPError/URLError -> propagates past apply_call

    return fake


# ---------------------------------------------------------------------------
# _rest_get
# ---------------------------------------------------------------------------


class TestRestGet:
    def test_no_token_returns_none(self) -> None:
        assert subject._rest_get("user", token="") is None

    def test_exception_returns_none(self) -> None:
        assert subject._rest_get("user", token=_TOKEN, opener=_raising_opener()) is None

    def test_bad_json_returns_none(self) -> None:
        assert subject._rest_get("user", token=_TOKEN, opener=_raw_opener(b"not json")) is None

    def test_non_dict_json_returns_none(self) -> None:
        assert subject._rest_get("user", token=_TOKEN, opener=_raw_opener(b"[1, 2]")) is None

    def test_success_returns_dict(self) -> None:
        assert subject._rest_get("user", token=_TOKEN, opener=_opener({"login": "tvna"})) == {"login": "tvna"}


# ---------------------------------------------------------------------------
# _rest_get_list
# ---------------------------------------------------------------------------


class TestRestGetList:
    def test_no_token_returns_none(self) -> None:
        assert subject._rest_get_list("repos/o/r/pulls", token="") is None

    def test_exception_returns_none(self) -> None:
        assert subject._rest_get_list("repos/o/r/pulls", token=_TOKEN, opener=_raising_opener()) is None

    def test_non_2xx_returns_none(self) -> None:
        # 404 makes apply_call stop retrying immediately (4xx); helper returns None.
        assert subject._rest_get_list("repos/o/r/pulls", token=_TOKEN, opener=_raw_opener(b"[]", status=404)) is None

    def test_bad_json_returns_none(self) -> None:
        assert subject._rest_get_list("repos/o/r/pulls", token=_TOKEN, opener=_raw_opener(b"nope")) is None

    def test_non_list_json_returns_none(self) -> None:
        assert subject._rest_get_list("repos/o/r/pulls", token=_TOKEN, opener=_raw_opener(b'{"a": 1}')) is None

    def test_success_returns_list(self) -> None:
        assert subject._rest_get_list("repos/o/r/pulls", token=_TOKEN, opener=_opener([1, 2])) == [1, 2]


# ---------------------------------------------------------------------------
# _detect_repo
# ---------------------------------------------------------------------------


class TestDetectRepo:
    def test_from_env_var(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("GITHUB_REPOSITORY", "tvna/claude-md")
        assert subject._detect_repo() == "tvna/claude-md"

    def test_from_git_remote_when_env_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

        class _Result:
            returncode = 0
            stdout = "git@github.com:tvna/claude-md.git\n"

        monkeypatch.setattr(subject.subprocess, "run", lambda *a, **k: _Result())
        assert subject._detect_repo() == "tvna/claude-md"

    def test_none_when_remote_nonzero(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

        class _Result:
            returncode = 1
            stdout = ""

        monkeypatch.setattr(subject.subprocess, "run", lambda *a, **k: _Result())
        assert subject._detect_repo() is None

    def test_none_on_subprocess_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)

        def _boom(*a: object, **k: object) -> None:
            raise OSError("git missing")

        monkeypatch.setattr(subject.subprocess, "run", _boom)
        assert subject._detect_repo() is None


# ---------------------------------------------------------------------------
# _extract_pr_info — structured fallbacks and _walk list branch
# ---------------------------------------------------------------------------


def test_extract_pr_info_structured_string_number() -> None:
    event = {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"owner": "o", "repo": "r"},
        "tool_response": {"pull_request_number": "123"},
    }
    assert subject._extract_pr_info(event) == ("o", "r", "123")


def test_extract_pr_info_walks_nested_list() -> None:
    event = {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {"owner": "o", "repo": "r"},
        "tool_response": {"items": [{"pr_number": 7}]},
    }
    assert subject._extract_pr_info(event) == ("o", "r", "7")


# ---------------------------------------------------------------------------
# decide_post_tool_use — owner/repo undetermined branch
# ---------------------------------------------------------------------------


def test_decide_skips_when_owner_repo_missing() -> None:
    event = {
        "tool_name": "mcp__github__create_pull_request",
        "tool_input": {},
        "tool_response": {"number": 9},
    }
    result = subject.decide_post_tool_use(event, token=_TOKEN)
    assert result is not None
    ctx = result["hookSpecificOutput"]["additionalContext"]
    assert "owner/repo could not be" in ctx


# ---------------------------------------------------------------------------
# _list_open_prs
# ---------------------------------------------------------------------------


class TestListOpenPrs:
    def test_empty_without_token(self) -> None:
        assert subject._list_open_prs(token="") == []

    def test_empty_when_user_lookup_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(subject, "_rest_get", lambda *a, **k: None)
        assert subject._list_open_prs(token=_TOKEN) == []

    def test_empty_when_login_missing(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(subject, "_rest_get", lambda *a, **k: {"no_login": True})
        assert subject._list_open_prs(token=_TOKEN) == []

    def test_empty_when_repo_undetected(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(subject, "_rest_get", lambda *a, **k: {"login": "tvna"})
        monkeypatch.setattr(subject, "_detect_repo", lambda: None)
        assert subject._list_open_prs(token=_TOKEN) == []

    def test_empty_when_pulls_lookup_fails(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(subject, "_rest_get", lambda *a, **k: {"login": "tvna"})
        monkeypatch.setattr(subject, "_detect_repo", lambda: "tvna/claude-md")
        monkeypatch.setattr(subject, "_rest_get_list", lambda *a, **k: None)
        assert subject._list_open_prs(token=_TOKEN) == []

    def test_filters_to_session_user(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(subject, "_rest_get", lambda *a, **k: {"login": "tvna"})
        monkeypatch.setattr(subject, "_detect_repo", lambda: "tvna/claude-md")
        prs = [
            {"number": 1, "user": {"login": "someone-else"}},
            "not-a-dict",
            {
                "number": 2,
                "html_url": "https://github.com/tvna/claude-md/pull/2",
                "user": {"login": "tvna"},
                "head": {"repo": {"name": "claude-md", "owner": {"login": "tvna"}}},
            },
        ]
        monkeypatch.setattr(subject, "_rest_get_list", lambda *a, **k: prs)
        out = subject._list_open_prs(token=_TOKEN)
        assert len(out) == 1
        assert out[0]["number"] == 2


# ---------------------------------------------------------------------------
# run_session_start — per-PR skip branches
# ---------------------------------------------------------------------------


def test_session_start_skips_entry_without_number(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(subject, "_list_open_prs", lambda **k: [{"headRepositoryOwner": {"login": "o"}}])
    subject.run_session_start(token=_TOKEN, sleeper=lambda _: None)
    assert capsys.readouterr().out == ""


def test_session_start_skips_entry_without_owner_repo(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        subject,
        "_list_open_prs",
        lambda **k: [{"number": 5, "headRepositoryOwner": {}, "headRepository": {}}],
    )
    subject.run_session_start(token=_TOKEN, sleeper=lambda _: None)
    assert capsys.readouterr().out == ""


def test_session_start_skips_when_poll_returns_none(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setattr(
        subject,
        "_list_open_prs",
        lambda **k: [
            {
                "number": 5,
                "url": "https://github.com/tvna/claude-md/pull/5",
                "headRepositoryOwner": {"login": "tvna"},
                "headRepository": {"name": "claude-md"},
            }
        ],
    )
    monkeypatch.setattr(subject, "_poll_mergeability", lambda *a, **k: None)
    subject.run_session_start(token=_TOKEN, sleeper=lambda _: None)
    assert capsys.readouterr().out == ""


# ---------------------------------------------------------------------------
# main() — stdin error paths (PostToolUse mode)
# ---------------------------------------------------------------------------


def test_main_malformed_stdin_is_fail_open(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO("not json {{{"))
    rc = subject.main([])
    assert rc == 0
    assert capsys.readouterr().out == ""


def test_main_non_dict_stdin_is_fail_open(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr("sys.stdin", io.StringIO('"a string"'))
    rc = subject.main([])
    assert rc == 0
    assert capsys.readouterr().out == ""
