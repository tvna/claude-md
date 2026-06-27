"""Tests for ``scripts/verify_linked_issue_titles.py``.

The ``scripts/`` directory is added to ``sys.path`` via the
``pythonpath`` key under ``[tool.pytest.ini_options]`` in
``pyproject.toml``.

Covers #941: the gate that rejects a PR when any linked issue title
violates the repository title policy.
"""

from __future__ import annotations

import urllib.error
from pathlib import Path

import pytest
import verify_linked_issue_titles as vlit
from _github_api import GitHubApiError

pytestmark = pytest.mark.shard_ci_ops

# ---------------------------------------------------------------------------
# _extract_refs (internal, exercised through the public API below too)
# ---------------------------------------------------------------------------


class TestExtractRefs:
    def test_empty_body(self) -> None:
        assert vlit._extract_refs("") == []

    def test_single_closes(self) -> None:
        assert vlit._extract_refs("Closes #42\n") == [42]

    def test_all_keywords(self) -> None:
        body = "Refs #1\nCloses #2\nFixes #3\nResolves #4\n"
        assert vlit._extract_refs(body) == [1, 2, 3, 4]

    def test_sorted_unique(self) -> None:
        body = "Closes #10\nRefs #2\nFixes #10\n"
        assert vlit._extract_refs(body) == [2, 10]

    def test_mid_line_ignored(self) -> None:
        assert vlit._extract_refs("see Closes #5 above\n") == []

    def test_html_comments_suppressed_by_caller(self) -> None:
        from _ref_classifier import strip_html_comments
        body = "<!-- Closes #99 -->\nCloses #1\n"
        cleaned = strip_html_comments(body.replace("\r", ""))
        assert vlit._extract_refs(cleaned) == [1]


# ---------------------------------------------------------------------------
# get_issue_title
# ---------------------------------------------------------------------------


class TestGetIssueTitle:
    def test_returns_title_on_success(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            vlit, "rest_json", lambda *_a, **_k: {"title": "fix(scope): correct title"}
        )
        assert vlit.get_issue_title("owner/repo", 42) == "fix(scope): correct title"

    def test_strips_surrounding_whitespace(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vlit, "rest_json", lambda *_a, **_k: {"title": "  fix: simple  "})
        assert vlit.get_issue_title("owner/repo", 42) == "fix: simple"

    def test_rest_contract(self, monkeypatch: pytest.MonkeyPatch) -> None:
        captured: dict[str, str] = {}

        def _rest(method, path, *_a, **kwargs):
            captured["method"] = method
            captured["path"] = path
            captured["token"] = kwargs.get("token")
            return {"title": "fix: title"}

        monkeypatch.setattr(vlit, "rest_json", _rest)
        vlit.get_issue_title("owner/repo", 99, token="tok")
        assert captured["method"] == "GET"
        assert captured["path"] == "/repos/owner/repo/issues/99"
        assert captured["token"] == "tok"

    def test_returns_none_on_api_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise(*_a, **_k):
            raise GitHubApiError(404, "GET", "/repos/owner/repo/issues/1", "not found")

        monkeypatch.setattr(vlit, "rest_json", _raise)
        assert vlit.get_issue_title("owner/repo", 1) is None

    def test_returns_none_on_network_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise(*_a, **_k):
            raise urllib.error.URLError("connection refused")

        monkeypatch.setattr(vlit, "rest_json", _raise)
        assert vlit.get_issue_title("owner/repo", 1) is None

    def test_returns_none_on_oserror(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _raise(*_a, **_k):
            raise OSError("disk full")

        monkeypatch.setattr(vlit, "rest_json", _raise)
        assert vlit.get_issue_title("owner/repo", 1) is None

    def test_returns_none_on_empty_title(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vlit, "rest_json", lambda *_a, **_k: {"title": "   "})
        assert vlit.get_issue_title("owner/repo", 1) is None

    def test_returns_none_on_malformed_body(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(vlit, "rest_json", lambda *_a, **_k: ["not", "a", "dict"])
        assert vlit.get_issue_title("owner/repo", 1) is None


# ---------------------------------------------------------------------------
# _validate_issue_title
# ---------------------------------------------------------------------------


class TestValidateIssueTitle:
    def test_valid_title_returns_empty(self) -> None:
        assert vlit._validate_issue_title("fix(scope): correct title", 42) == []

    def test_valid_title_no_scope_returns_empty(self) -> None:
        assert vlit._validate_issue_title("feat: add new feature", 5) == []

    def test_non_ascii_title_reports_issue_number(self) -> None:
        errors = vlit._validate_issue_title("fix: 日本語タイトル", 7)
        assert any("Issue #7" in e for e in errors)
        assert any("ASCII-only" in e for e in errors)
        assert any("Fix the title on issue #7" in e for e in errors)

    def test_bad_convention_reports_issue_number(self) -> None:
        errors = vlit._validate_issue_title("Bad title without convention", 13)
        assert any("Issue #13" in e for e in errors)
        assert any("naming convention" in e for e in errors)
        assert any("Fix the title on issue #13" in e for e in errors)

    def test_unknown_type_reports_issue_number(self) -> None:
        errors = vlit._validate_issue_title("unknown: some description", 21)
        assert any("Issue #21" in e for e in errors)
        assert any("::error::" in e for e in errors)

    def test_type_fit_mismatch_reports_issue_number(self) -> None:
        # A "fix:" title whose summary is pure performance vocabulary
        # triggers the type-fit gate.
        errors = vlit._validate_issue_title(
            "fix: improve cache performance and throughput", 33
        )
        # When type-fit fires, the error must mention the issue number.
        if errors:
            assert any("Issue #33" in e for e in errors)
            assert any("Fix the title on issue #33" in e for e in errors)

    def test_all_errors_start_with_error_annotation(self) -> None:
        errors = vlit._validate_issue_title("INVALID TITLE", 99)
        assert errors
        for e in errors:
            assert e.startswith("::error::"), e


# ---------------------------------------------------------------------------
# verify_linked_issue_titles (core logic)
# ---------------------------------------------------------------------------


def _install_titles(
    monkeypatch: pytest.MonkeyPatch, titles: dict[int, str | None]
) -> list[int]:
    """Patch ``vlit.get_issue_title`` to serve *titles* by number.

    A title of ``None`` (or a number absent from the map) models a failed
    fetch. Returns a list that records the issue numbers fetched.
    """
    called: list[int] = []

    def _fake(repo: str, number: int, **_kwargs: object) -> str | None:
        called.append(number)
        return titles.get(number)

    monkeypatch.setattr(vlit, "get_issue_title", _fake)
    return called


class TestVerifyLinkedIssueTitles:
    def test_no_refs_returns_zero_with_note(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = vlit.verify_linked_issue_titles("owner/repo", "No refs here.\n")
        assert rc == 0
        assert "skipped" in capsys.readouterr().out

    def test_valid_issue_title_passes(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _install_titles(monkeypatch, {42: "fix: valid issue title"})
        rc = vlit.verify_linked_issue_titles("owner/repo", "Closes #42\n")
        assert rc == 0
        out = capsys.readouterr().out
        assert "OK: issue #42 title passes title policy." in out
        assert "::error::" not in out

    def test_invalid_issue_title_fails(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _install_titles(monkeypatch, {42: "INVALID TITLE WITHOUT CONVENTION"})
        rc = vlit.verify_linked_issue_titles("owner/repo", "Closes #42\n")
        assert rc == 1
        out = capsys.readouterr().out
        assert "::error::" in out
        assert "#42" in out

    def test_multiple_refs_one_invalid_fails_and_names_offender(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _install_titles(monkeypatch, {1: "fix: valid title", 2: "INVALID TITLE"})
        rc = vlit.verify_linked_issue_titles("owner/repo", "Closes #1\nRefs #2\n")
        assert rc == 1
        out = capsys.readouterr().out
        assert "OK: issue #1 title passes title policy." in out
        assert "Issue #2" in out
        assert "::error::" in out

    def test_api_failure_treated_as_gate_failure(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _install_titles(monkeypatch, {5: None})
        rc = vlit.verify_linked_issue_titles("owner/repo", "Closes #5\n")
        assert rc == 1
        out = capsys.readouterr().out
        assert "::error::" in out
        assert "#5" in out
        assert "GH_TOKEN" in out

    def test_html_commented_refs_are_ignored(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # The commented ref must NOT trigger a title fetch.
        called = _install_titles(monkeypatch, {1: "fix: real issue title"})
        rc = vlit.verify_linked_issue_titles(
            "owner/repo", "<!-- Closes #99 -->\nCloses #1\n"
        )
        assert rc == 0
        assert 99 not in called
        assert 1 in called

    def test_crlf_body_is_normalized(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _install_titles(monkeypatch, {10: "ci: valid title"})
        rc = vlit.verify_linked_issue_titles("owner/repo", "Closes #10\r\n")
        assert rc == 0
        assert "OK: issue #10 title passes title policy." in capsys.readouterr().out

    def test_non_ascii_issue_title_fails_with_context(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        _install_titles(monkeypatch, {7: "fix: 日本語タイトル"})
        rc = vlit.verify_linked_issue_titles("owner/repo", "Closes #7\n")
        assert rc == 1
        out = capsys.readouterr().out
        assert "Issue #7" in out
        assert "ASCII-only" in out


# ---------------------------------------------------------------------------
# CLI (main / _cmd_verify)
# ---------------------------------------------------------------------------


class TestCLI:
    def test_happy_path_via_env(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("PR_BODY", "Closes #1\n")
        monkeypatch.setattr(
            vlit, "get_issue_title",
            lambda repo, n, **_k: "fix: proper issue title",
        )
        rc = vlit.main(["verify", "--repo", "owner/repo"])
        assert rc == 0
        assert "OK" in capsys.readouterr().out

    def test_body_file_takes_precedence_over_env(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("PR_BODY", "Closes #999\n")
        body_file = tmp_path / "body.md"
        body_file.write_text("Closes #1\n", encoding="utf-8")
        monkeypatch.setattr(
            vlit, "get_issue_title",
            lambda repo, n, **_k: "fix: proper issue title",
        )
        rc = vlit.main(["verify", "--repo", "owner/repo", "--body-file", str(body_file)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "#1" in out
        assert "#999" not in out

    def test_no_refs_exits_zero(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("PR_BODY", "No refs at all.\n")
        rc = vlit.main(["verify", "--repo", "owner/repo"])
        assert rc == 0
        assert "skipped" in capsys.readouterr().out

    def test_invalid_title_exits_nonzero(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("PR_BODY", "Closes #42\n")
        monkeypatch.setattr(
            vlit, "get_issue_title",
            lambda repo, n, **_k: "INVALID TITLE",
        )
        rc = vlit.main(["verify", "--repo", "owner/repo"])
        assert rc == 1
        out = capsys.readouterr().out
        assert "::error::" in out
        assert "#42" in out

    def test_missing_body_env_defaults_to_empty(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.delenv("PR_BODY", raising=False)
        rc = vlit.main(["verify", "--repo", "owner/repo"])
        assert rc == 0
        assert "skipped" in capsys.readouterr().out

    def test_verify_subcommand_requires_repo(self) -> None:
        with pytest.raises(SystemExit):
            vlit.main(["verify"])

    def test_unknown_subcommand_exits(self) -> None:
        with pytest.raises(SystemExit):
            vlit.main(["bogus"])
