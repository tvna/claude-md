"""Tests for ``scripts/pr_body_close_keyword_advisory.py``.

The ``scripts/`` directory is on ``sys.path`` via ``pythonpath`` under
``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

import io
import json

import pytest

import pr_body_close_keyword_advisory as hook


# ---------------------------------------------------------------------------
# build_advisory: pure-function classification
# ---------------------------------------------------------------------------


class TestBuildAdvisory:
    @pytest.mark.parametrize(
        "body",
        [
            "Refs #1",
            "Refs #1\n",
            "refs #42\n",
            "  Refs #99\n",
            "Refs #1\nRefs #2\n",
        ],
    )
    def test_refs_only_returns_advisory(self, body: str) -> None:
        msg = hook.build_advisory(body)
        assert msg is not None
        assert msg.startswith("ADVISORY:")
        assert "Refs" in msg
        assert "Closes" in msg
        assert "See #216." in msg

    @pytest.mark.parametrize(
        "body",
        [
            "Closes #1\n",
            "Fixes #1\n",
            "Resolves #1\n",
            "closes #1\n",
            "Refs #1\nCloses #2\n",  # mixed -> at least one closing keyword
        ],
    )
    def test_closing_keyword_present_returns_none(self, body: str) -> None:
        assert hook.build_advisory(body) is None

    @pytest.mark.parametrize(
        "body",
        [
            "",
            "no refs at all\n",
            "see #5 mid-line, not a ref\n",
            "References #6\n",  # word-boundary: not 'Refs'
        ],
    )
    def test_no_refs_returns_none(self, body: str) -> None:
        # No advisory: a separate CI gate handles 'body has no ref at all'.
        assert hook.build_advisory(body) is None

    def test_partial_marker_suppresses_advisory(self) -> None:
        assert (
            hook.build_advisory("Refs #214\n\n<!-- partial -->\n") is None
        )

    @pytest.mark.parametrize(
        "marker",
        [
            "<!-- partial -->",
            "<!--partial-->",
            "<!--   PARTIAL   -->",
            "<!-- Partial -->",
        ],
    )
    def test_partial_marker_variants(self, marker: str) -> None:
        assert hook.build_advisory(f"Refs #1\n\n{marker}\n") is None

    def test_html_commented_closes_does_not_count(self) -> None:
        # ``<!-- Closes #999 -->`` is stripped before classification, so
        # the remaining body has only ``Refs #1`` -> advisory fires.
        msg = hook.build_advisory("<!-- Closes #999 -->\nRefs #1\n")
        assert msg is not None
        assert "#1" in msg
        assert "#999" not in msg

    def test_advisory_numbers_sorted_and_unique(self) -> None:
        body = "Refs #10\nRefs #2\nRefs #10\nRefs #100\n"
        msg = hook.build_advisory(body)
        assert msg is not None
        assert "#2, #10, #100" in msg


# ---------------------------------------------------------------------------
# main: stdin JSON -> stderr/exit-code contract
# ---------------------------------------------------------------------------


class TestMain:
    def test_refs_only_emits_advisory_to_stderr_exit_zero(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        payload = {
            "tool_name": "mcp__github__create_pull_request",
            "tool_input": {"body": "Refs #214\n", "title": "fix(x): y"},
        }
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        assert hook.main() == 0
        err = capsys.readouterr().err
        assert err.startswith("ADVISORY:")
        assert "#214" in err

    def test_closes_keyword_no_advisory_exit_zero(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        payload = {"tool_input": {"body": "Closes #1\n"}}
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        assert hook.main() == 0
        assert capsys.readouterr().err == ""

    def test_partial_marker_no_advisory(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        payload = {"tool_input": {"body": "Refs #1\n<!-- partial -->\n"}}
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        assert hook.main() == 0
        assert capsys.readouterr().err == ""

    def test_invalid_json_exit_zero_silent(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO("not json {"))
        assert hook.main() == 0
        assert capsys.readouterr().err == ""

    def test_empty_stdin_exit_zero_silent(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(""))
        assert hook.main() == 0
        assert capsys.readouterr().err == ""

    def test_missing_tool_input_exit_zero_silent(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps({})))
        assert hook.main() == 0
        assert capsys.readouterr().err == ""

    def test_missing_body_field_exit_zero_silent(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        payload = {"tool_input": {"title": "no body field"}}
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        assert hook.main() == 0
        assert capsys.readouterr().err == ""

    def test_body_not_string_exit_zero_silent(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        payload = {"tool_input": {"body": 12345}}
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        assert hook.main() == 0
        assert capsys.readouterr().err == ""

    def test_tool_input_not_object_exit_zero_silent(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        payload = {"tool_input": "not an object"}
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        assert hook.main() == 0
        assert capsys.readouterr().err == ""

    def test_advisory_does_not_block_exit_is_zero(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # Pins the advisory contract: even when the advisory fires, the
        # hook MUST exit 0 so the tool call is not blocked. The CI gate
        # is the enforcement layer.
        payload = {"tool_input": {"body": "Refs #1\n"}}
        monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(payload)))
        exit_code = hook.main()
        assert exit_code == 0
        assert "ADVISORY:" in capsys.readouterr().err
