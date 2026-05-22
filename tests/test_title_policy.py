"""Tests for ``scripts/title_policy.py``."""

from __future__ import annotations

import pytest

import title_policy


class TestIsAsciiTitle:
    @pytest.mark.parametrize(
        "title",
        [
            "",
            "ci(github): enable title policy validation",
            "fix: require Refs #155 in PR body",
            "docs: update ruleset smoke test",
        ],
    )
    def test_ascii_titles_pass(self, title: str) -> None:
        assert title_policy.is_ascii_title(title) is True

    @pytest.mark.parametrize(
        "title",
        [
            "ci: reject 日本語 titles",
            "ci: reject emoji \U0001f6a8",
            "ci: reject zero\u200bwidth",
            "ci: reject rtl \u202eoverride",
            "ci: reject fullwidth ＡＢＣ",
        ],
    )
    def test_non_ascii_titles_fail(self, title: str) -> None:
        assert title_policy.is_ascii_title(title) is False


class TestDescribeNonAscii:
    def test_reports_codepoint_positions(self) -> None:
        assert title_policy.describe_non_ascii("A\u200bB\u202e") == [
            "index 1: U+200B",
            "index 3: U+202E",
        ]

    def test_limit(self) -> None:
        assert title_policy.describe_non_ascii("あいう", limit=2) == [
            "index 0: U+3042",
            "index 1: U+3044",
        ]


class TestVerifyTitle:
    def test_ascii_exit_zero(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert title_policy.verify_title("docs: update", kind="issue") == 0
        out = capsys.readouterr().out
        assert "OK: issue title is ASCII-only." in out

    def test_non_ascii_exit_one(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        assert title_policy.verify_title(
            "ci: reject zero\u200bwidth",
            kind="pull_request",
        ) == 1
        out = capsys.readouterr().out
        assert "::error::pull_request title must be ASCII-only" in out
        assert "U+200B" in out


class TestCLI:
    def test_uses_title_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("TITLE", "ci: ascii only")
        assert title_policy.main(["verify", "--kind", "pull_request"]) == 0
        assert "OK: pull_request title is ASCII-only." in capsys.readouterr().out

    def test_title_arg_overrides_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("TITLE", "ci: ascii only")
        assert (
            title_policy.main(
                [
                    "verify",
                    "--kind",
                    "issue",
                    "--title",
                    "bad \U0001f6a8",
                ]
            )
            == 1
        )
        assert "U+1F6A8" in capsys.readouterr().out
