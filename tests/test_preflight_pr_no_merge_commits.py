"""Tests for ``scripts/preflight_pr_no_merge_commits.py``.

Mirrors the table-driven style of ``tests/test_preflight_pr_single_commit.py``:
pure functions get parametrize cases, the subprocess boundary is
exercised via a fake ``runner`` injected through the kwarg the
production code already exposes.

The ``scripts/`` directory is on ``sys.path`` via ``pythonpath`` under
``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

import subprocess
from typing import Any

import preflight_pr_no_merge_commits as gate
import pytest


def _fake_runner(stdout: str = "", returncode: int = 0):
    """Return a callable mimicking ``subprocess.run(..., capture_output=True)``.

    The production module's :func:`preflight_pr_no_merge_commits._run`
    calls ``runner(cmd, capture_output=True, text=True, timeout=...,
    check=True)``. ``check=True`` makes the real subprocess raise on
    non-zero exit; we mirror that here so the fail-loud path in
    :func:`preflight_pr_no_merge_commits.main` is reachable from tests.
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
# resolve_head
# ---------------------------------------------------------------------------


class TestResolveHead:
    def test_explicit_head_ref_wins(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("HEAD_REF", "abc1234567")
        assert gate.resolve_head() == "abc1234567"

    def test_falls_back_to_head_when_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("HEAD_REF", raising=False)
        assert gate.resolve_head() == "HEAD"

    def test_empty_env_string_treated_as_unset(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # GitHub Actions may emit "" on synthesised events; do not let an
        # empty string override the default git ref.
        monkeypatch.setenv("HEAD_REF", "")
        assert gate.resolve_head() == "HEAD"


# ---------------------------------------------------------------------------
# find_merge_commits
# ---------------------------------------------------------------------------


class TestFindMergeCommits:
    def test_empty_output_yields_empty_list(self) -> None:
        assert gate.find_merge_commits("origin/main", runner=_fake_runner("")) == []

    def test_single_merge_from_main_subject(self) -> None:
        stdout = "deadbeef1234 Merge branch 'main' into feature-x\n"
        assert gate.find_merge_commits("origin/main", runner=_fake_runner(stdout)) == [
            ("deadbeef1234", "Merge branch 'main' into feature-x"),
        ]

    def test_unknown_merge_subject_still_returned(self) -> None:
        # ``--merges`` already filtered to parent_count > 1; an
        # unrecognized subject still counts as a merge commit and the
        # gate must fire on it.
        stdout = "abc1234567 Merge pull request #99 from foo/bar\n"
        assert gate.find_merge_commits("origin/main", runner=_fake_runner(stdout)) == [
            ("abc1234567", "Merge pull request #99 from foo/bar"),
        ]

    def test_multiple_merge_commits_all_returned(self) -> None:
        stdout = (
            "1111111111 Merge branch 'main' into feature-x\n"
            "2222222222 Merge remote-tracking branch 'origin/main' into feature-x\n"
            "3333333333 Merge branch 'master' into feature-x\n"
        )
        result = gate.find_merge_commits("origin/main", runner=_fake_runner(stdout))
        assert [sha for sha, _ in result] == ["1111111111", "2222222222", "3333333333"]

    def test_skips_blank_lines(self) -> None:
        stdout = "\n1111111111 Merge branch 'main' into feature-x\n\n"
        assert gate.find_merge_commits("origin/main", runner=_fake_runner(stdout)) == [
            ("1111111111", "Merge branch 'main' into feature-x"),
        ]

    def test_propagates_called_process_error(self) -> None:
        # Unknown base ref makes git log exit non-zero; the boundary
        # must let the CalledProcessError bubble so main() can surface it.
        with pytest.raises(subprocess.CalledProcessError):
            gate.find_merge_commits("origin/nonexistent", runner=_fake_runner("", returncode=128))


# ---------------------------------------------------------------------------
# subject_matches_merge_from_main
# ---------------------------------------------------------------------------


class TestSubjectMatchesMergeFromMain:
    @pytest.mark.parametrize(
        "subject",
        [
            "Merge branch 'main' into feature-x",
            "Merge branch 'main'",
            "Merge remote-tracking branch 'origin/main' into feature-x",
            "Merge branch 'master' into feature-x",
            "Merge remote-tracking branch 'origin/master'",
        ],
    )
    def test_known_prefixes_match(self, subject: str) -> None:
        assert gate.subject_matches_merge_from_main(subject) is True

    @pytest.mark.parametrize(
        "subject",
        [
            "feat: add thing",
            "Merge pull request #99 from foo/bar",
            "Merge branch 'release/1.0'",
            "docs: explain merge workflow",
            "",
        ],
    )
    def test_non_matching_subjects(self, subject: str) -> None:
        assert gate.subject_matches_merge_from_main(subject) is False

    def test_leading_whitespace_tolerated(self) -> None:
        assert gate.subject_matches_merge_from_main("  Merge branch 'main'") is True


# ---------------------------------------------------------------------------
# format_failure
# ---------------------------------------------------------------------------


class TestFormatFailure:
    def test_first_line_pins_canonical_wording_singular(self) -> None:
        msg = gate.format_failure(
            commits=[("abc1234567", "Merge branch 'main' into feature-x")],
            base="origin/main",
        )
        first = msg.splitlines()[0]
        assert first == "::error::PR has 1 merge commit, expected 0 (base: origin/main)"

    def test_first_line_pins_canonical_wording_plural(self) -> None:
        msg = gate.format_failure(
            commits=[
                ("1111111111", "Merge branch 'main'"),
                ("2222222222", "Merge pull request #99 from foo/bar"),
            ],
            base="origin/main",
        )
        first = msg.splitlines()[0]
        assert first == "::error::PR has 2 merge commits, expected 0 (base: origin/main)"

    def test_lists_each_commit_with_sha_and_subject(self) -> None:
        msg = gate.format_failure(
            commits=[
                ("1111111111", "Merge branch 'main' into feature-x"),
                ("2222222222", "Merge pull request #99 from foo/bar"),
            ],
            base="origin/main",
        )
        assert "1111111111 [merge-from-main] Merge branch 'main' into feature-x" in msg
        assert "2222222222 [merge] Merge pull request #99 from foo/bar" in msg

    def test_known_merge_from_main_tagged_distinctly(self) -> None:
        msg = gate.format_failure(
            commits=[("abc1234567", "Merge branch 'main'")],
            base="origin/main",
        )
        assert "[merge-from-main]" in msg
        assert "[merge] Merge branch 'main'" not in msg

    def test_unknown_merge_subject_tagged_as_plain_merge(self) -> None:
        msg = gate.format_failure(
            commits=[("abc1234567", "Merge pull request #99 from foo/bar")],
            base="origin/main",
        )
        assert "[merge] Merge pull request #99 from foo/bar" in msg
        assert "[merge-from-main]" not in msg

    def test_references_recovery_runbook(self) -> None:
        msg = gate.format_failure(
            commits=[("abc1234567", "Merge branch 'main'")],
            base="origin/main",
        )
        assert "docs/runbooks/rebase-debt-recovery.md" in msg

    def test_references_issue_491(self) -> None:
        msg = gate.format_failure(
            commits=[("abc1234567", "Merge branch 'main'")],
            base="origin/main",
        )
        assert "Issue #491" in msg


# ---------------------------------------------------------------------------
# main (CLI orchestration)
# ---------------------------------------------------------------------------


class TestMain:
    def test_exits_zero_when_no_merge_commits(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("BASE_REF", "origin/main")
        monkeypatch.setattr(gate, "find_merge_commits", lambda base, head="HEAD", **kw: [])
        assert gate.main() == 0
        captured = capsys.readouterr()
        assert "OK: 0 merge commits ahead of origin/main" in captured.out

    def test_exits_one_when_merge_commits_present(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("BASE_REF", "origin/main")
        monkeypatch.setattr(
            gate,
            "find_merge_commits",
            lambda base, head="HEAD", **kw: [
                ("1111111111", "Merge branch 'main' into feature-x"),
            ],
        )
        assert gate.main() == 1
        captured = capsys.readouterr()
        assert "::error::PR has 1 merge commit, expected 0" in captured.err
        assert "docs/runbooks/rebase-debt-recovery.md" in captured.err

    def test_fail_loud_on_git_invocation_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        monkeypatch.setenv("BASE_REF", "origin/missing")

        def explode(base: str, head: str = "HEAD", **kw: Any) -> list[tuple[str, str]]:
            raise subprocess.CalledProcessError(128, ["git"], output="", stderr="")

        monkeypatch.setattr(gate, "find_merge_commits", explode)
        assert gate.main() == 1
        captured = capsys.readouterr()
        assert "::error::preflight_pr_no_merge_commits: git invocation failed" in captured.err

    def test_forwards_head_ref_to_find_merge_commits(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # When HEAD_REF is set (the GitHub Actions pull_request shape),
        # main() must walk back from the PR head SHA, not the local HEAD.
        # Issue #491: the synthetic refs/pull/<N>/merge would otherwise
        # false-positive the gate.
        monkeypatch.setenv("BASE_REF", "origin/main")
        monkeypatch.setenv("HEAD_REF", "abc1234567")
        observed: dict[str, str] = {}

        def capture(base: str, head: str = "HEAD", **kw: Any) -> list[tuple[str, str]]:
            observed["base"] = base
            observed["head"] = head
            return []

        monkeypatch.setattr(gate, "find_merge_commits", capture)
        assert gate.main() == 0
        assert observed == {"base": "origin/main", "head": "abc1234567"}
