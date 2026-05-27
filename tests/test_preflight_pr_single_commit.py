"""Tests for ``scripts/preflight_pr_single_commit.py``.

Mirrors the table-driven style of ``tests/test_preflight_title_policy.py``
and ``tests/test_branch_cleanup.py``: pure functions get parametrize
cases, the subprocess boundary is exercised via a fake ``runner``
injected through the kwarg the production code already exposes.

The ``scripts/`` directory is on ``sys.path`` via ``pythonpath`` under
``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

import subprocess
from typing import Any

import preflight_pr_single_commit as gate
import pytest


def _fake_runner(stdout: str = "", returncode: int = 0):
    """Return a callable mimicking ``subprocess.run(..., capture_output=True)``.

    The production module's :func:`preflight_pr_single_commit._run`
    calls ``runner(cmd, capture_output=True, text=True, timeout=...,
    check=True)``. ``check=True`` makes the real subprocess raise on
    non-zero exit; we mirror that here so the fail-loud path in
    :func:`preflight_pr_single_commit.main` is reachable from tests.
    """
    def runner(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess:
        if kwargs.get("check") and returncode != 0:
            raise subprocess.CalledProcessError(returncode, cmd, output=stdout, stderr="")
        return subprocess.CompletedProcess(args=cmd, returncode=returncode, stdout=stdout, stderr="")
    return runner


# ---------------------------------------------------------------------------
# resolve_base
# ---------------------------------------------------------------------------


class TestResolveBase:
    def test_explicit_base_ref_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("BASE_REF", "origin/feature")
        monkeypatch.setenv("GITHUB_BASE_REF", "main")
        assert gate.resolve_base() == "origin/feature"

    def test_github_base_ref_used_when_explicit_absent(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BASE_REF", raising=False)
        monkeypatch.setenv("GITHUB_BASE_REF", "main")
        assert gate.resolve_base() == "origin/main"

    def test_fallback_to_origin_main(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BASE_REF", raising=False)
        monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
        assert gate.resolve_base() == "origin/main"

    def test_empty_env_strings_treated_as_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # GitHub Actions sets GITHUB_BASE_REF to "" on push events; an
        # empty string must NOT take precedence over the default base.
        monkeypatch.setenv("BASE_REF", "")
        monkeypatch.setenv("GITHUB_BASE_REF", "")
        assert gate.resolve_base() == "origin/main"


# ---------------------------------------------------------------------------
# count_commits
# ---------------------------------------------------------------------------


class TestCountCommits:
    @pytest.mark.parametrize("stdout, expected", [("0\n", 0), ("1\n", 1), ("2\n", 2), ("17\n", 17)])
    def test_returns_int_from_rev_list_output(self, stdout: str, expected: int) -> None:
        assert gate.count_commits("origin/main", runner=_fake_runner(stdout)) == expected

    def test_strips_whitespace_around_count(self) -> None:
        assert gate.count_commits("origin/main", runner=_fake_runner("  3  \n")) == 3

    def test_non_integer_output_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match="non-integer"):
            gate.count_commits("origin/main", runner=_fake_runner("not-a-number\n"))

    def test_propagates_called_process_error(self) -> None:
        # Unknown base ref makes git rev-list exit non-zero; the boundary
        # must let the CalledProcessError bubble so main() can surface it.
        with pytest.raises(subprocess.CalledProcessError):
            gate.count_commits("origin/nonexistent", runner=_fake_runner("", returncode=128))


# ---------------------------------------------------------------------------
# list_subjects
# ---------------------------------------------------------------------------


class TestListSubjects:
    def test_returns_one_line_per_commit(self) -> None:
        stdout = "abc1234 feat: a\nbcd2345 fix: b\n"
        assert gate.list_subjects("origin/main", runner=_fake_runner(stdout)) == [
            "abc1234 feat: a",
            "bcd2345 fix: b",
        ]

    def test_empty_output_yields_empty_list(self) -> None:
        assert gate.list_subjects("origin/main", runner=_fake_runner("")) == []

    def test_skips_blank_lines(self) -> None:
        assert gate.list_subjects("origin/main", runner=_fake_runner("\n\n")) == []


# ---------------------------------------------------------------------------
# has_fixup_commits
# ---------------------------------------------------------------------------


class TestHasFixupCommits:
    @pytest.mark.parametrize(
        "subjects",
        [
            ["abc1234 fixup! original subject"],
            ["abc1234 squash! original subject"],
            ["abc1234 amend! original subject"],
            ["abc1234 feat: ok", "bcd2345 fixup! patch"],
        ],
    )
    def test_detects_fixup_prefixes(self, subjects: list[str]) -> None:
        assert gate.has_fixup_commits(subjects) is True

    @pytest.mark.parametrize(
        "subjects",
        [
            [],
            ["abc1234 feat: add thing"],
            ["abc1234 fix(scope): bug"],
            # Subject containing "fixup!" mid-line must not be flagged.
            ["abc1234 docs: explain fixup! workflow"],
        ],
    )
    def test_no_match_returns_false(self, subjects: list[str]) -> None:
        assert gate.has_fixup_commits(subjects) is False

    def test_malformed_line_without_subject_is_skipped(self) -> None:
        # ``--format=%h %s`` always emits ``<sha> <subject>``; defensive
        # check guarding against pathological output (e.g. a bare sha).
        assert gate.has_fixup_commits(["abc1234"]) is False


# ---------------------------------------------------------------------------
# format_failure
# ---------------------------------------------------------------------------


class TestFormatFailure:
    def test_first_line_pins_canonical_wording(self) -> None:
        msg = gate.format_failure(
            count=3,
            base="origin/main",
            subjects=["abc1234 feat: a", "bcd2345 fix: b", "cde3456 chore: c"],
            fixup_present=False,
        )
        first = msg.splitlines()[0]
        assert first == "::error::PR has 3 commits, expected 1 (base: origin/main)"

    def test_lists_each_commit_subject(self) -> None:
        msg = gate.format_failure(
            count=2,
            base="origin/main",
            subjects=["abc1234 feat: a", "bcd2345 fix: b"],
            fixup_present=False,
        )
        assert "  - abc1234 feat: a" in msg
        assert "  - bcd2345 fix: b" in msg

    def test_fixup_branch_uses_autosquash_remediation(self) -> None:
        msg = gate.format_failure(
            count=2,
            base="origin/main",
            subjects=["abc1234 feat: a", "bcd2345 fixup! a"],
            fixup_present=True,
        )
        assert "fixup!/squash!/amend! commit detected" in msg
        assert "git rebase -i --autosquash origin/main" in msg

    def test_non_fixup_branch_uses_plain_rebase(self) -> None:
        msg = gate.format_failure(
            count=2,
            base="origin/main",
            subjects=["abc1234 feat: a", "bcd2345 feat: b"],
            fixup_present=False,
        )
        assert "git rebase -i origin/main" in msg
        assert "fixup!/squash!/amend!" not in msg

    def test_references_issue_492(self) -> None:
        msg = gate.format_failure(
            count=2,
            base="origin/main",
            subjects=["abc1234 feat: a", "bcd2345 feat: b"],
            fixup_present=False,
        )
        assert "Issue #492" in msg


# ---------------------------------------------------------------------------
# main (CLI orchestration)
# ---------------------------------------------------------------------------


class TestMain:
    def test_exits_zero_for_single_clean_commit(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("BASE_REF", "origin/main")
        monkeypatch.setattr(gate, "list_subjects", lambda base, head="HEAD", **kw: ["abc1234 feat: a"])
        monkeypatch.setattr(gate, "count_commits", lambda base, head="HEAD", **kw: 1)
        assert gate.main() == 0
        captured = capsys.readouterr()
        assert "OK: 1 commit ahead of origin/main" in captured.out

    def test_exits_one_when_multiple_commits(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("BASE_REF", "origin/main")
        monkeypatch.setattr(
            gate,
            "list_subjects",
            lambda base, head="HEAD", **kw: ["abc1234 feat: a", "bcd2345 feat: b"],
        )
        monkeypatch.setattr(gate, "count_commits", lambda base, head="HEAD", **kw: 2)
        assert gate.main() == 1
        captured = capsys.readouterr()
        assert "::error::PR has 2 commits, expected 1" in captured.err

    def test_exits_one_when_zero_commits(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        # An empty branch ahead of main is also a contract violation:
        # the PR cannot land work it does not carry.
        monkeypatch.setenv("BASE_REF", "origin/main")
        monkeypatch.setattr(gate, "list_subjects", lambda base, head="HEAD", **kw: [])
        monkeypatch.setattr(gate, "count_commits", lambda base, head="HEAD", **kw: 0)
        assert gate.main() == 1
        captured = capsys.readouterr()
        assert "::error::PR has 0 commits, expected 1" in captured.err

    def test_exits_one_when_single_commit_is_fixup(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("BASE_REF", "origin/main")
        monkeypatch.setattr(gate, "list_subjects", lambda base, head="HEAD", **kw: ["abc1234 fixup! a"])
        monkeypatch.setattr(gate, "count_commits", lambda base, head="HEAD", **kw: 1)
        assert gate.main() == 1
        captured = capsys.readouterr()
        # Canonical count line still reflects the real count (1) per the
        # Issue #492 verification wording; the fixup hint is an extra
        # ::error:: line that surfaces the rejection reason.
        assert "::error::PR has 1 commits, expected 1" in captured.err
        assert "fixup!/squash!/amend! commit detected" in captured.err

    def test_fail_loud_on_git_invocation_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("BASE_REF", "origin/missing")

        def explode(base: str, head: str = "HEAD", **kw: Any) -> list[str]:
            raise subprocess.CalledProcessError(128, ["git"], output="", stderr="")

        monkeypatch.setattr(gate, "list_subjects", explode)
        assert gate.main() == 1
        captured = capsys.readouterr()
        assert "::error::preflight_pr_single_commit: git invocation failed" in captured.err

    def test_fail_loud_on_value_error_from_count(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("BASE_REF", "origin/main")
        monkeypatch.setattr(gate, "list_subjects", lambda base, head="HEAD", **kw: [])

        def raise_value_error(base: str, head: str = "HEAD", **kw: Any) -> int:
            raise ValueError("non-integer count")

        monkeypatch.setattr(gate, "count_commits", raise_value_error)
        assert gate.main() == 1
        captured = capsys.readouterr()
        assert "::error::preflight_pr_single_commit: git invocation failed" in captured.err
