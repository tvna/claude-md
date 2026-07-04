"""Tests for ``scripts/scan_review_in_progress_marker.py``.

Covers :func:`has_in_progress_marker`, :func:`run_verify`, and :func:`main`.
All tests are hermetic: the GitHub REST call is patched via
``scan_review_in_progress_marker.rest_json``; no real network call is made.

Refs #2312.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import patch

import pytest
import scan_review_in_progress_marker as gate
from _github_api import GitHubApiError

pytestmark = pytest.mark.shard_ci_ops

_CODEX_LOGIN = "chatgpt-codex-connector[bot]"


def _reaction(content: str, login: str) -> dict[str, Any]:
    return {"content": content, "user": {"login": login}}


# ---------------------------------------------------------------------------
# has_in_progress_marker
# ---------------------------------------------------------------------------


class TestHasInProgressMarker:
    def test_eyes_reaction_from_codex_login_detected(self) -> None:
        reactions = [_reaction("eyes", _CODEX_LOGIN)]
        assert gate.has_in_progress_marker(reactions) == _CODEX_LOGIN

    def test_eyes_reaction_from_bare_login_form_detected(self) -> None:
        # GraphQL delivers the bare slug (no "[bot]" suffix); both forms are
        # registered in .github/trusted_bots.toml (#1731 dual-form precedent).
        reactions = [_reaction("eyes", "chatgpt-codex-connector")]
        assert gate.has_in_progress_marker(reactions) == "chatgpt-codex-connector"

    def test_login_match_is_case_insensitive(self) -> None:
        reactions = [_reaction("eyes", _CODEX_LOGIN.upper())]
        assert gate.has_in_progress_marker(reactions) == _CODEX_LOGIN.upper()

    def test_no_reactions_returns_none(self) -> None:
        assert gate.has_in_progress_marker([]) is None

    def test_completed_marker_plus_one_returns_none(self) -> None:
        # PR #2309 / #2317 / #2319 (post-completion): the eyes reaction is
        # removed and replaced by a "+1" once the review finishes with no
        # suggestions. That is a completed state, not in-progress.
        reactions = [_reaction("+1", _CODEX_LOGIN)]
        assert gate.has_in_progress_marker(reactions) is None

    def test_eyes_reaction_from_untrusted_login_ignored(self) -> None:
        # An eyes reaction from an arbitrary human or unrelated bot is not the
        # Codex marker; this gate must not treat every 👀 as review-in-progress.
        reactions = [_reaction("eyes", "some-other-user")]
        assert gate.has_in_progress_marker(reactions) is None

    def test_malformed_reaction_entries_are_skipped(self) -> None:
        reactions: list[Any] = [
            "not-a-dict",
            {"content": "eyes"},  # missing "user"
            {"content": "eyes", "user": "not-a-dict"},
            {"content": "eyes", "user": {"login": 123}},
        ]
        assert gate.has_in_progress_marker(reactions) is None


# ---------------------------------------------------------------------------
# run_verify
# ---------------------------------------------------------------------------


class TestRunVerify:
    def test_marker_present_blocks(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch.object(gate, "fetch_reactions", return_value=[_reaction("eyes", _CODEX_LOGIN)]):
            code = gate.run_verify(repo="tvna/claude-md", pr_number="2319", token="tok")

        assert code == 1
        err = capsys.readouterr().err
        assert "::error::" in err
        assert "tvna/claude-md#2319" in err
        assert "review-in-progress-marker.md" in err

    def test_marker_absent_passes(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch.object(gate, "fetch_reactions", return_value=[]):
            code = gate.run_verify(repo="tvna/claude-md", pr_number="2314", token="tok")

        assert code == 0
        assert "OK:" in capsys.readouterr().err

    def test_completed_marker_passes(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch.object(gate, "fetch_reactions", return_value=[_reaction("+1", _CODEX_LOGIN)]):
            code = gate.run_verify(repo="tvna/claude-md", pr_number="2309", token="tok")

        assert code == 0
        assert "OK:" in capsys.readouterr().err

    def test_missing_repo_fails_open(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = gate.run_verify(repo=None, pr_number="1", token="tok")

        assert code == 0
        assert "::warning::" in capsys.readouterr().err

    def test_missing_pr_number_fails_open(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = gate.run_verify(repo="tvna/claude-md", pr_number=None, token="tok")

        assert code == 0
        assert "::warning::" in capsys.readouterr().err

    def test_missing_token_fails_open(self, capsys: pytest.CaptureFixture[str]) -> None:
        code = gate.run_verify(repo="tvna/claude-md", pr_number="1", token=None)

        assert code == 0
        assert "::warning::" in capsys.readouterr().err

    def test_api_error_fails_open(self, capsys: pytest.CaptureFixture[str]) -> None:
        with patch.object(
            gate,
            "fetch_reactions",
            side_effect=GitHubApiError(503, "GET", "/repos/x/y/issues/1/reactions", "server error"),
        ):
            code = gate.run_verify(repo="tvna/claude-md", pr_number="1", token="tok")

        assert code == 0
        assert "::warning::" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


class TestMain:
    def test_unknown_subcommand_exits_64(self) -> None:
        assert gate.main(["bogus"]) == 64

    def test_no_subcommand_exits_64(self) -> None:
        assert gate.main([]) == 64

    def test_verify_marker_present_exits_1(self, monkeypatch: pytest.MonkeyPatch) -> None:
        with patch.object(gate, "fetch_reactions", return_value=[_reaction("eyes", _CODEX_LOGIN)]):
            code = gate.main(["verify", "--repo", "tvna/claude-md", "--pr-number", "2319", "--token", "tok"])

        assert code == 1

    def test_verify_marker_absent_exits_0(self) -> None:
        with patch.object(gate, "fetch_reactions", return_value=[]):
            code = gate.main(["verify", "--repo", "tvna/claude-md", "--pr-number", "2314", "--token", "tok"])

        assert code == 0

    def test_verify_reads_env_defaults(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("REPO", "tvna/claude-md")
        monkeypatch.setenv("PR_NUMBER", "2319")
        monkeypatch.setenv("GH_TOKEN", "tok")
        with patch.object(gate, "fetch_reactions", return_value=[]) as mocked:
            code = gate.main(["verify"])

        assert code == 0
        mocked.assert_called_once_with("tvna/claude-md", "2319", token="tok")
