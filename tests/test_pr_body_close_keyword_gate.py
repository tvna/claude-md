"""Tests for ``scripts/pr_body_close_keyword_gate.py``.

Mirrors the structure of ``tests/test_preflight_non_ascii.py``: pure
functions tested in isolation, then the stdin/stdout boundary of
:func:`main` with monkeypatched ``sys.stdin`` / ``os.environ``.

The ``scripts/`` directory is on ``sys.path`` via ``pythonpath`` under
``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

import io
import json
import urllib.error
from typing import Any

import pr_body_close_keyword_gate as gate
import pytest

# ---------------------------------------------------------------------------
# classify_action
# ---------------------------------------------------------------------------


class TestClassifyAction:
    @pytest.mark.parametrize(
        "body, expected_numbers",
        [
            ("Refs #1\n", [1]),
            ("Refs #1", [1]),
            ("refs #42\n", [42]),
            ("  Refs #99\n", [99]),
            ("\tRefs #7\n", [7]),
            ("Refs #1\nRefs #2\n", [1, 2]),
            ("Refs #2\nRefs #1\n", [1, 2]),  # sorted-unique
            ("Refs #1\nRefs #1\n", [1]),  # dedup
        ],
    )
    def test_refs_only_needs_label_check(
        self, body: str, expected_numbers: list[int]
    ) -> None:
        action, numbers = gate.classify_action(body)
        assert action == "needs_label_check"
        assert numbers == expected_numbers

    @pytest.mark.parametrize(
        "body",
        [
            "Closes #1\n",
            "Fixes #1\n",
            "Resolves #1\n",
            "closes #1\n",
            "RESOLVES #99\n",
            "Refs #1\nCloses #2\n",
            "Closes #2\nRefs #1\n",
        ],
    )
    def test_closing_keyword_passes(self, body: str) -> None:
        action, numbers = gate.classify_action(body)
        assert action == "pass"
        assert numbers == []

    @pytest.mark.parametrize(
        "marker",
        [
            "<!-- partial -->",
            "<!--partial-->",
            "<!--   PARTIAL   -->",
            "<!-- Partial -->",
        ],
    )
    def test_partial_marker_passes_even_with_refs_only(
        self, marker: str
    ) -> None:
        body = f"Refs #214\n\n{marker}\n"
        action, numbers = gate.classify_action(body)
        assert action == "pass"
        assert numbers == []

    @pytest.mark.parametrize(
        "body",
        [
            "",
            "no refs at all\n",
            "see Refs #5 above\n",  # mid-line, rejected by line-anchored regex
            "References #6\n",  # word-boundary: not 'Refs'
        ],
    )
    def test_no_refs_returns_skip(self, body: str) -> None:
        action, numbers = gate.classify_action(body)
        assert action == "skip"
        assert numbers == []

    def test_html_commented_closes_does_not_count(self) -> None:
        body = "<!-- Closes #999 -->\nRefs #1\n"
        action, numbers = gate.classify_action(body)
        assert action == "needs_label_check"
        assert numbers == [1]


# ---------------------------------------------------------------------------
# fetch_labels
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status: int, body: bytes) -> None:
        self.status = status
        self._body = body

    def __enter__(self) -> _FakeResponse:
        return self

    def __exit__(self, *_a: Any) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class TestFetchLabels:
    def _opener_returning(self, status: int, body: bytes):
        def _opener(_request, *_a, **_k):
            return _FakeResponse(status, body)

        return _opener

    def test_returns_label_names_on_200(self) -> None:
        body = json.dumps(
            {
                "labels": [
                    {"name": "type:tracking"},
                    {"name": "layer:meta"},
                ]
            }
        ).encode()
        result = gate.fetch_labels(
            "owner",
            "repo",
            42,
            token="t",
            opener=self._opener_returning(200, body),
            sleeper=lambda _s: None,
        )
        assert result == ["type:tracking", "layer:meta"]

    def test_empty_labels_returns_empty_list(self) -> None:
        body = json.dumps({"labels": []}).encode()
        result = gate.fetch_labels(
            "owner",
            "repo",
            42,
            token="t",
            opener=self._opener_returning(200, body),
            sleeper=lambda _s: None,
        )
        assert result == []

    def test_string_label_entries_are_accepted(self) -> None:
        body = json.dumps({"labels": ["type:tracking", "layer:meta"]}).encode()
        result = gate.fetch_labels(
            "owner",
            "repo",
            42,
            token="t",
            opener=self._opener_returning(200, body),
            sleeper=lambda _s: None,
        )
        assert result == ["type:tracking", "layer:meta"]

    def test_404_returns_none(self) -> None:
        def _opener(request, *_a, **_k):
            raise urllib.error.HTTPError(
                url=request.full_url,
                code=404,
                msg="Not Found",
                hdrs=None,
                fp=io.BytesIO(b'{"message":"Not Found"}'),
            )

        result = gate.fetch_labels(
            "owner",
            "repo",
            42,
            token="t",
            opener=_opener,
            sleeper=lambda _s: None,
        )
        assert result is None

    @pytest.mark.parametrize("code", [401, 403, 429])
    def test_named_4xx_returns_none(self, code: int) -> None:
        def _opener(request, *_a, **_k):
            raise urllib.error.HTTPError(
                url=request.full_url,
                code=code,
                msg="error",
                hdrs=None,
                fp=io.BytesIO(b'{"message":"err"}'),
            )

        result = gate.fetch_labels(
            "owner",
            "repo",
            42,
            token="t",
            opener=_opener,
            sleeper=lambda _s: None,
        )
        assert result is None

    def test_500_returns_none_after_retry(self) -> None:
        calls: list[int] = []

        def _opener(request, *_a, **_k):
            calls.append(1)
            raise urllib.error.HTTPError(
                url=request.full_url,
                code=500,
                msg="Server Error",
                hdrs=None,
                fp=io.BytesIO(b"oops"),
            )

        result = gate.fetch_labels(
            "owner",
            "repo",
            42,
            token="t",
            opener=_opener,
            sleeper=lambda _s: None,
        )
        assert result is None
        # apply_call retries up to 3 times on 5xx -- verify the path is taken.
        assert len(calls) == 3

    def test_url_error_returns_none(self) -> None:
        def _opener(_request, *_a, **_k):
            raise urllib.error.URLError("network unreachable")

        result = gate.fetch_labels(
            "owner",
            "repo",
            42,
            token="t",
            opener=_opener,
            sleeper=lambda _s: None,
        )
        assert result is None

    def test_non_json_body_returns_none(self) -> None:
        result = gate.fetch_labels(
            "owner",
            "repo",
            42,
            token="t",
            opener=self._opener_returning(200, b"not json"),
            sleeper=lambda _s: None,
        )
        assert result is None

    def test_labels_field_missing_returns_none(self) -> None:
        body = json.dumps({"number": 42}).encode()
        result = gate.fetch_labels(
            "owner",
            "repo",
            42,
            token="t",
            opener=self._opener_returning(200, body),
            sleeper=lambda _s: None,
        )
        assert result is None


# ---------------------------------------------------------------------------
# all_tracking
# ---------------------------------------------------------------------------


class TestAllTracking:
    def test_all_tracking_returns_true(self) -> None:
        assert gate.all_tracking(
            {216: ["type:tracking", "layer:meta"], 219: ["type:tracking"]}
        ) is True

    def test_one_missing_label_returns_false(self) -> None:
        assert gate.all_tracking(
            {216: ["type:tracking"], 214: ["type:fix"]}
        ) is False

    def test_none_entry_returns_false(self) -> None:
        assert gate.all_tracking({216: None}) is False

    def test_empty_dict_returns_false(self) -> None:
        assert gate.all_tracking({}) is False


# ---------------------------------------------------------------------------
# decide
# ---------------------------------------------------------------------------


def _make_input(
    *,
    body: Any = "Refs #205\n",
    owner: str = "tvna",
    repo: str = "claude-md",
) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    if owner is not None:
        payload["owner"] = owner
    if repo is not None:
        payload["repo"] = repo
    if body is not None:
        payload["body"] = body
    return payload


class TestDecide:
    def test_off_target_tool_returns_none(self) -> None:
        decision = gate.decide(
            "mcp__github__add_issue_comment",
            _make_input(),
            token_getter=lambda: "t",
            label_getter=lambda *_a: ["type:fix"],
        )
        assert decision is None

    def test_body_missing_returns_none(self) -> None:
        payload = _make_input(body=None)
        decision = gate.decide(
            "mcp__github__create_pull_request",
            payload,
            token_getter=lambda: "t",
            label_getter=lambda *_a: ["type:fix"],
        )
        assert decision is None

    def test_body_not_string_returns_none(self) -> None:
        decision = gate.decide(
            "mcp__github__create_pull_request",
            _make_input(body=12345),
            token_getter=lambda: "t",
            label_getter=lambda *_a: ["type:fix"],
        )
        assert decision is None

    def test_closing_keyword_returns_none(self) -> None:
        decision = gate.decide(
            "mcp__github__create_pull_request",
            _make_input(body="Closes #205\n"),
            token_getter=lambda: "t",
            label_getter=lambda *_a: ["type:fix"],
        )
        assert decision is None

    def test_partial_marker_returns_none(self) -> None:
        decision = gate.decide(
            "mcp__github__create_pull_request",
            _make_input(body="Refs #205\n\n<!-- partial -->\n"),
            token_getter=lambda: "t",
            label_getter=lambda *_a: ["type:fix"],
        )
        assert decision is None

    def test_no_refs_returns_none(self) -> None:
        decision = gate.decide(
            "mcp__github__create_pull_request",
            _make_input(body="prose only\n"),
            token_getter=lambda: "t",
            label_getter=lambda *_a: ["type:fix"],
        )
        assert decision is None

    def test_refs_only_with_tracking_label_returns_none(self) -> None:
        decision = gate.decide(
            "mcp__github__create_pull_request",
            _make_input(body="Refs #216\n"),
            token_getter=lambda: "t",
            label_getter=lambda *_a: ["type:tracking", "layer:meta"],
        )
        assert decision is None

    def test_refs_only_partial_tracking_denies(self) -> None:
        labels = {216: ["type:tracking"], 214: ["type:fix"]}
        decision = gate.decide(
            "mcp__github__create_pull_request",
            _make_input(body="Refs #216\nRefs #214\n"),
            token_getter=lambda: "t",
            label_getter=lambda _o, _r, n: labels[n],
        )
        assert decision is not None
        out = decision["hookSpecificOutput"]
        assert out["hookEventName"] == "PreToolUse"
        assert out["permissionDecision"] == "deny"
        reason = out["permissionDecisionReason"]
        assert "PR body uses only 'Refs' for #214, #216" in reason
        assert "type:tracking" in reason
        assert "<!-- partial -->" in reason
        assert "See #216." in reason

    def test_refs_only_label_lookup_failed_denies_with_note(self) -> None:
        decision = gate.decide(
            "mcp__github__create_pull_request",
            _make_input(body="Refs #205\n"),
            token_getter=lambda: "t",
            label_getter=lambda *_a: None,
        )
        assert decision is not None
        reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
        assert "label lookup" in reason
        assert "#205" in reason

    def test_refs_only_no_token_denies_with_gh_token_note(self) -> None:
        decision = gate.decide(
            "mcp__github__create_pull_request",
            _make_input(body="Refs #205\n"),
            token_getter=lambda: None,
            label_getter=lambda *_a: pytest.fail(
                "label_getter must not be called when token is missing"
            ),
        )
        assert decision is not None
        reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
        assert "GH_TOKEN" in reason
        assert "#205" in reason

    def test_refs_only_empty_string_token_denies(self) -> None:
        decision = gate.decide(
            "mcp__github__create_pull_request",
            _make_input(body="Refs #205\n"),
            token_getter=lambda: "",
            label_getter=lambda *_a: pytest.fail(
                "label_getter must not be called when token is empty"
            ),
        )
        assert decision is not None
        reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
        assert "GH_TOKEN" in reason

    def test_owner_missing_returns_none_fail_open(self) -> None:
        payload = {"repo": "claude-md", "body": "Refs #205\n"}
        decision = gate.decide(
            "mcp__github__create_pull_request",
            payload,
            token_getter=lambda: "t",
            label_getter=lambda *_a: ["type:fix"],
        )
        # owner/repo malformed -- fail-open, server gate is backstop.
        assert decision is None

    def test_repo_missing_returns_none_fail_open(self) -> None:
        payload = {"owner": "tvna", "body": "Refs #205\n"}
        decision = gate.decide(
            "mcp__github__create_pull_request",
            payload,
            token_getter=lambda: "t",
            label_getter=lambda *_a: ["type:fix"],
        )
        assert decision is None

    def test_update_pull_request_also_gated(self) -> None:
        decision = gate.decide(
            "mcp__github__update_pull_request",
            _make_input(body="Refs #205\n"),
            token_getter=lambda: None,
            label_getter=lambda *_a: [],
        )
        assert decision is not None


# ---------------------------------------------------------------------------
# main: stdin/stdout boundary
# ---------------------------------------------------------------------------


class TestMain:
    def _set_stdin(
        self, monkeypatch: pytest.MonkeyPatch, payload: Any
    ) -> None:
        text = json.dumps(payload) if not isinstance(payload, str) else payload
        monkeypatch.setattr("sys.stdin", io.StringIO(text))

    def test_refs_only_no_token_writes_deny_json_exit_zero(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("GH_TOKEN", raising=False)
        monkeypatch.delenv("GITHUB_TOKEN", raising=False)
        self._set_stdin(
            monkeypatch,
            {
                "tool_name": "mcp__github__create_pull_request",
                "tool_input": {
                    "owner": "tvna",
                    "repo": "claude-md",
                    "body": "Refs #205\n",
                    "title": "fix(x): y",
                },
            },
        )
        assert gate.main() == 0
        out = capsys.readouterr().out
        decision = json.loads(out)
        assert decision["hookSpecificOutput"]["hookEventName"] == "PreToolUse"
        assert decision["hookSpecificOutput"]["permissionDecision"] == "deny"
        reason = decision["hookSpecificOutput"]["permissionDecisionReason"]
        assert "#205" in reason
        assert "GH_TOKEN" in reason

    def test_closing_keyword_no_output_exit_zero(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._set_stdin(
            monkeypatch,
            {
                "tool_name": "mcp__github__create_pull_request",
                "tool_input": {
                    "owner": "tvna",
                    "repo": "claude-md",
                    "body": "Closes #205\n",
                },
            },
        )
        assert gate.main() == 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == ""

    def test_partial_marker_no_output(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._set_stdin(
            monkeypatch,
            {
                "tool_name": "mcp__github__create_pull_request",
                "tool_input": {
                    "owner": "tvna",
                    "repo": "claude-md",
                    "body": "Refs #205\n<!-- partial -->\n",
                },
            },
        )
        assert gate.main() == 0
        assert capsys.readouterr().out == ""

    def test_invalid_json_exit_zero_no_decision(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._set_stdin(monkeypatch, "not json {")
        assert gate.main() == 0
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "::error::" in captured.err

    def test_empty_stdin_exit_zero(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._set_stdin(monkeypatch, "")
        assert gate.main() == 0
        assert capsys.readouterr().out == ""

    def test_missing_tool_input_exit_zero(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._set_stdin(monkeypatch, {"tool_name": "x"})
        assert gate.main() == 0
        assert capsys.readouterr().out == ""

    def test_off_target_tool_no_output(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        self._set_stdin(
            monkeypatch,
            {
                "tool_name": "mcp__github__add_issue_comment",
                "tool_input": {
                    "owner": "tvna",
                    "repo": "claude-md",
                    "body": "Refs #205\n",
                },
            },
        )
        assert gate.main() == 0
        assert capsys.readouterr().out == ""

    def test_refs_only_with_token_consults_label_getter(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "fake-token")

        seen: list[tuple[str, str, int]] = []

        def _fake_fetch(owner, repo, number, *, token, **_kw):
            seen.append((owner, repo, number))
            assert token == "fake-token"
            return ["type:tracking"]

        monkeypatch.setattr(gate, "fetch_labels", _fake_fetch)
        self._set_stdin(
            monkeypatch,
            {
                "tool_name": "mcp__github__create_pull_request",
                "tool_input": {
                    "owner": "tvna",
                    "repo": "claude-md",
                    "body": "Refs #216\n",
                },
            },
        )
        assert gate.main() == 0
        assert seen == [("tvna", "claude-md", 216)]
        assert capsys.readouterr().out == ""

    def test_refs_only_with_token_non_tracking_denies(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("GH_TOKEN", "fake-token")
        monkeypatch.setattr(
            gate, "fetch_labels", lambda *_a, **_k: ["type:fix"]
        )
        self._set_stdin(
            monkeypatch,
            {
                "tool_name": "mcp__github__create_pull_request",
                "tool_input": {
                    "owner": "tvna",
                    "repo": "claude-md",
                    "body": "Refs #214\n",
                },
            },
        )
        assert gate.main() == 0
        decision = json.loads(capsys.readouterr().out)
        out = decision["hookSpecificOutput"]
        assert out["permissionDecision"] == "deny"
        assert "#214" in out["permissionDecisionReason"]
