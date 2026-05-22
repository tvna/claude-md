"""Tests for ``scripts/issue_link.py``.

The ``scripts/`` directory is added to ``sys.path`` via the
``pythonpath`` key under ``[tool.pytest.ini_options]`` in
``pyproject.toml``.
"""

from __future__ import annotations

import subprocess

import pytest

import issue_link


# ---------------------------------------------------------------------------
# strip_html_comments
# ---------------------------------------------------------------------------


class TestStripHtmlComments:
    def test_empty(self) -> None:
        assert issue_link.strip_html_comments("") == ""

    def test_no_comments(self) -> None:
        assert issue_link.strip_html_comments("Refs #1\n") == "Refs #1\n"

    def test_single_line_comment(self) -> None:
        assert (
            issue_link.strip_html_comments("a <!-- x --> b") == "a  b"
        )

    def test_multi_line_comment(self) -> None:
        src = "head\n<!-- line1\nline2\nline3 -->\ntail\n"
        assert issue_link.strip_html_comments(src) == "head\n\ntail\n"

    def test_multiple_comments(self) -> None:
        src = "<!-- a -->X<!-- b -->Y<!-- c -->"
        assert issue_link.strip_html_comments(src) == "XY"

    def test_non_greedy(self) -> None:
        # Two separate comments must NOT be coalesced into one match.
        src = "<!-- one --> keep me <!-- two -->"
        assert issue_link.strip_html_comments(src) == " keep me "

    def test_commented_ref_kills_the_keyword(self) -> None:
        """An HTML-commented `Refs #N` must not survive into extract_refs."""
        src = "<!-- Refs #999 -->\nbody text\n"
        cleaned = issue_link.strip_html_comments(src)
        assert issue_link.extract_refs(cleaned) == []


# ---------------------------------------------------------------------------
# extract_refs
# ---------------------------------------------------------------------------


class TestExtractRefs:
    def test_empty(self) -> None:
        assert issue_link.extract_refs("") == []

    def test_no_refs(self) -> None:
        assert issue_link.extract_refs("Just prose with #5 mentioned.") == []

    def test_single_refs(self) -> None:
        assert issue_link.extract_refs("Refs #42\n") == [42]

    def test_each_keyword(self) -> None:
        for kw in ("Refs", "Closes", "Fixes", "Resolves"):
            body = f"{kw} #7\n"
            assert issue_link.extract_refs(body) == [7], kw

    def test_case_insensitive(self) -> None:
        for kw in ("refs", "REFS", "Refs", "rEfS"):
            body = f"{kw} #7\n"
            assert issue_link.extract_refs(body) == [7], kw

    def test_leading_whitespace_allowed(self) -> None:
        assert issue_link.extract_refs("    Refs #3\n") == [3]
        assert issue_link.extract_refs("\tCloses #4\n") == [4]

    def test_mid_line_mention_rejected(self) -> None:
        # The keyword must start the line (after optional indent).
        assert issue_link.extract_refs("see Refs #5 above\n") == []

    def test_word_boundary_on_keyword(self) -> None:
        # "References" should NOT match "Refs".
        assert issue_link.extract_refs("References #6\n") == []
        # But "Refs" with whitespace before # must still match.
        assert issue_link.extract_refs("Refs #6\n") == [6]

    def test_keyword_requires_whitespace_before_hash(self) -> None:
        # No space between keyword and # is not a valid GitHub ref.
        assert issue_link.extract_refs("Refs#6\n") == []

    def test_multiple_refs_sorted_unique(self) -> None:
        body = (
            "Refs #10\n"
            "Closes #2\n"
            "Fixes #10\n"  # duplicate
            "Resolves #100\n"
        )
        assert issue_link.extract_refs(body) == [2, 10, 100]

    def test_real_world_multiline_body(self) -> None:
        body = (
            "## Summary\n"
            "\n"
            "Some prose about Refs #99 (mid-line; ignored).\n"
            "\n"
            "Refs #1\n"
            "closes #2\n"
            "  Fixes #3\n"
            "\n"
            "## End\n"
        )
        assert issue_link.extract_refs(body) == [1, 2, 3]

    def test_multiline_commented_ref_matches_without_strip(self) -> None:
        """``extract_refs`` is purely regex-based: a keyword that lands on
        its own line inside a multi-line HTML comment WILL match. The
        composition guarantee (strip then extract) is what makes the
        end-to-end path immune; this test pins the boundary so future
        readers do not assume ``extract_refs`` knows about comments.
        """
        body = "<!--\nRefs #999\n-->\n"
        assert issue_link.extract_refs(body) == [999]
        # And the composition is what saves us:
        cleaned = issue_link.strip_html_comments(body)
        assert issue_link.extract_refs(cleaned) == []


# ---------------------------------------------------------------------------
# issue_exists
# ---------------------------------------------------------------------------


class TestIssueExists:
    def test_gh_success_returns_true(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class _Result:
            stdout = b""
            stderr = b""
            returncode = 0

        captured: dict = {}

        def _run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs
            return _Result()

        monkeypatch.setattr(subprocess, "run", _run)
        assert issue_link.issue_exists("owner/repo", 42) is True
        # Argv contract: gh api /repos/owner/repo/issues/42 --silent
        assert captured["cmd"] == [
            "gh", "api", "/repos/owner/repo/issues/42", "--silent",
        ]
        assert captured["kwargs"].get("check") is True
        assert captured["kwargs"].get("timeout") == 30

    def test_gh_missing_returns_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(*_a, **_k):
            raise FileNotFoundError("gh: command not found")

        monkeypatch.setattr(subprocess, "run", _raise)
        assert issue_link.issue_exists("owner/repo", 42) is False


class TestVerifyRefExists:
    def test_runner_success_returns_true(self) -> None:
        captured: dict = {}

        def _run(cmd, **kwargs):
            captured["cmd"] = cmd
            captured["kwargs"] = kwargs

        assert (
            issue_link.verify_ref_exists("owner/repo", 42, runner=_run)
            is True
        )
        assert captured["cmd"] == [
            "gh", "api", "/repos/owner/repo/issues/42", "--silent",
        ]
        assert captured["kwargs"].get("check") is True
        assert captured["kwargs"].get("timeout") == 30

    def test_runner_failure_returns_false(self) -> None:
        def _run(*_a, **_k):
            raise subprocess.CalledProcessError(1, "gh")

        assert (
            issue_link.verify_ref_exists("owner/repo", 42, runner=_run)
            is False
        )

    def test_gh_nonzero_exit_returns_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(*_a, **_k):
            raise subprocess.CalledProcessError(
                1, "gh", stderr=b"HTTP 404: Not Found"
            )

        monkeypatch.setattr(subprocess, "run", _raise)
        assert issue_link.issue_exists("owner/repo", 999_999_999) is False

    def test_gh_timeout_returns_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(*_a, **_k):
            raise subprocess.TimeoutExpired(cmd="gh", timeout=30)

        monkeypatch.setattr(subprocess, "run", _raise)
        assert issue_link.issue_exists("owner/repo", 42) is False

    def test_oserror_returns_false(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(*_a, **_k):
            raise OSError("disk full or similar")

        monkeypatch.setattr(subprocess, "run", _raise)
        assert issue_link.issue_exists("owner/repo", 42) is False


# ---------------------------------------------------------------------------
# CLI / _verify end-to-end
# ---------------------------------------------------------------------------


class TestCLI:
    def test_happy_path(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        monkeypatch.setenv("PR_BODY", "Refs #42\n")
        monkeypatch.setattr(issue_link, "issue_exists", lambda *_a: True)
        exit_code = issue_link.main(["verify", "--repo", "owner/repo"])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "OK: #42 resolves in owner/repo." in out
        assert "::error::" not in out

    def test_no_refs_exits_nonzero(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        monkeypatch.setenv("PR_BODY", "Body with no refs at all.\n")
        exit_code = issue_link.main(["verify", "--repo", "owner/repo"])
        assert exit_code == 1
        out = capsys.readouterr().out
        assert "no issue reference" in out
        assert "::error::" in out

    def test_empty_body_exits_nonzero(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        monkeypatch.setenv("PR_BODY", "")
        exit_code = issue_link.main(["verify", "--repo", "owner/repo"])
        assert exit_code == 1
        assert "no issue reference" in capsys.readouterr().out

    def test_missing_pr_body_env_exits_nonzero(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        monkeypatch.delenv("PR_BODY", raising=False)
        exit_code = issue_link.main(["verify", "--repo", "owner/repo"])
        assert exit_code == 1
        assert "no issue reference" in capsys.readouterr().out

    def test_body_file_is_used(
        self,
        tmp_path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        monkeypatch.setenv("PR_BODY", "Refs #999\n")
        body_file = tmp_path / "pr-body.md"
        body_file.write_text("Refs #42\n", encoding="utf-8")
        monkeypatch.setattr(issue_link, "issue_exists", lambda *_a: True)

        exit_code = issue_link.main([
            "verify",
            "--repo",
            "owner/repo",
            "--body-file",
            str(body_file),
        ])

        assert exit_code == 0
        out = capsys.readouterr().out
        assert "#42" in out
        assert "#999" not in out

    def test_one_missing_ref_among_resolvable(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        monkeypatch.setenv("PR_BODY", "Refs #1\nCloses #2\n")
        monkeypatch.setattr(
            issue_link, "issue_exists",
            lambda _repo, number: number == 1,
        )
        exit_code = issue_link.main(["verify", "--repo", "owner/repo"])
        assert exit_code == 1
        out = capsys.readouterr().out
        assert "OK: #1 resolves in owner/repo." in out
        assert "::error::Referenced #2 does not exist in owner/repo." in out

    def test_html_commented_ref_is_skipped(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        monkeypatch.setenv(
            "PR_BODY",
            "<!-- Refs #999 -->\nRefs #1\n",
        )
        monkeypatch.setattr(issue_link, "issue_exists", lambda *_a: True)
        exit_code = issue_link.main(["verify", "--repo", "owner/repo"])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "#1" in out
        assert "#999" not in out

    def test_crlf_is_normalized(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        # GitHub sometimes delivers PR bodies with CRLF.
        monkeypatch.setenv("PR_BODY", "Refs #1\r\nCloses #2\r\n")
        monkeypatch.setattr(issue_link, "issue_exists", lambda *_a: True)
        exit_code = issue_link.main(["verify", "--repo", "owner/repo"])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "#1" in out
        assert "#2" in out

    def test_verify_subcommand_requires_repo(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        monkeypatch.setenv("PR_BODY", "Refs #1\n")
        with pytest.raises(SystemExit):
            issue_link.main(["verify"])

    def test_unknown_subcommand_exits(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        with pytest.raises(SystemExit):
            issue_link.main(["bogus"])


# ---------------------------------------------------------------------------
# Trusted-bot allowlist (issue #139)
# ---------------------------------------------------------------------------


class TestTrustedBotAllowlist:
    """The verify gate must exempt trusted bot authors from the Refs check.

    Issue #139 carves an exception out of the gate so that Dependabot PRs,
    which never carry a ``Refs #N`` reference, do not become unmergeable
    under the required status check.
    """

    def test_dependabot_no_refs_exits_zero_with_skip_note(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        monkeypatch.setenv("PR_BODY", "Bumps foo from 1.0 to 1.1.\n")
        exit_code = issue_link.main([
            "verify",
            "--repo",
            "owner/repo",
            "--author",
            "dependabot[bot]",
        ])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "skipped" in out
        assert "dependabot[bot]" in out

    def test_non_bot_no_refs_still_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        monkeypatch.setenv("PR_BODY", "Body with no refs at all.\n")
        exit_code = issue_link.main([
            "verify",
            "--repo",
            "owner/repo",
            "--author",
            "tvna",
        ])
        assert exit_code == 1
        assert "no issue reference" in capsys.readouterr().out

    def test_non_bot_with_refs_still_passes(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        monkeypatch.setenv("PR_BODY", "Refs #136\n")
        monkeypatch.setattr(issue_link, "issue_exists", lambda *_a: True)
        exit_code = issue_link.main([
            "verify",
            "--repo",
            "owner/repo",
            "--author",
            "tvna",
        ])
        assert exit_code == 0
        out = capsys.readouterr().out
        assert "OK: #136 resolves in owner/repo." in out

    def test_unknown_bot_no_refs_still_fails(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Allowlist is exact-match: an unrecognized bot login is not exempt."""
        monkeypatch.setenv("PR_BODY", "Bumps foo.\n")
        exit_code = issue_link.main([
            "verify",
            "--repo",
            "owner/repo",
            "--author",
            "renovate[bot]",
        ])
        assert exit_code == 1
        out = capsys.readouterr().out
        assert "no issue reference" in out
        assert "skipped" not in out

    def test_author_from_env_var(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """``--author`` falls back to $PR_AUTHOR (mirrors PR_BODY contract)."""
        monkeypatch.setenv("PR_BODY", "Bumps foo from 1.0 to 1.1.\n")
        monkeypatch.setenv("PR_AUTHOR", "dependabot[bot]")
        exit_code = issue_link.main(["verify", "--repo", "owner/repo"])
        assert exit_code == 0
        assert "skipped" in capsys.readouterr().out

    def test_empty_author_falls_through(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """An empty author string must NOT be treated as the allowlist entry."""
        monkeypatch.setenv("PR_BODY", "Body with no refs.\n")
        exit_code = issue_link.main([
            "verify",
            "--repo",
            "owner/repo",
            "--author",
            "",
        ])
        assert exit_code == 1
        assert "no issue reference" in capsys.readouterr().out

    def test_bot_author_does_not_resolve_unverifiable_refs(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Trusted-bot skip short-circuits even when the body has dangling refs.

        Dependabot bodies may contain mid-line ``#N`` mentions like
        ``Bumps foo from 1.0 to 1.1`` plus changelog text with stray
        keyword-like tokens. The skip must not call ``gh api`` at all.
        """
        monkeypatch.setenv("PR_BODY", "Refs #999999\n")

        def _fail(*_a, **_k):
            raise AssertionError("gh api must not be called for trusted bots")

        monkeypatch.setattr(issue_link, "issue_exists", _fail)
        exit_code = issue_link.main([
            "verify",
            "--repo",
            "owner/repo",
            "--author",
            "dependabot[bot]",
        ])
        assert exit_code == 0
        assert "skipped" in capsys.readouterr().out
