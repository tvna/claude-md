"""Tests for ``scripts/branch_cleanup.py``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import branch_cleanup
import pytest

pytestmark = pytest.mark.shard_ci_ops

class _Result:
    def __init__(self, stdout: str = "") -> None:
        self.stdout = stdout


class TestParseDryRun:
    def test_true(self) -> None:
        assert branch_cleanup.parse_dry_run("true") is True

    def test_false(self) -> None:
        assert branch_cleanup.parse_dry_run("false") is False

    @pytest.mark.parametrize("raw", ["", "True", "FALSE", "yes", "0"])
    def test_rejects_other_values(self, raw: str) -> None:
        with pytest.raises(ValueError, match="Invalid dry_run"):
            branch_cleanup.parse_dry_run(raw)


class TestParseMinAgeDays:
    @pytest.mark.parametrize(("raw", "expected"), [("0", 0), ("60", 60)])
    def test_accepts_non_negative_integer(self, raw: str, expected: int) -> None:
        assert branch_cleanup.parse_min_age_days(raw) == expected

    @pytest.mark.parametrize("raw", ["", "-1", "1.5", "abc"])
    def test_rejects_invalid_values(self, raw: str) -> None:
        with pytest.raises(ValueError, match="non-negative integer"):
            branch_cleanup.parse_min_age_days(raw)


class TestIsCandidate:
    def test_default_branch_excluded(self) -> None:
        assert not _candidate(branch="main")

    def test_age_below_threshold_excluded(self) -> None:
        assert not _candidate(last_commit_days_ago=59, min_age_days=60)

    def test_exact_threshold_excluded_preserving_existing_semantic(self) -> None:
        assert not _candidate(last_commit_days_ago=60, min_age_days=60)

    def test_open_pr_excluded(self) -> None:
        assert not _candidate(has_open_pr=True)

    def test_old_orphan_branch_included(self) -> None:
        assert _candidate(last_commit_days_ago=61, min_age_days=60)


class TestFormatSummaryRow:
    def test_formats_markdown_row(self) -> None:
        row = branch_cleanup.format_summary_row(
            "feature/x",
            datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            61,
            "abcdef123456",
        )
        assert row == "| `feature/x` | 2026-01-02T03:04:05Z | 61 | `abcdef1` |"


class TestDecideIssueAction:
    def test_non_empty_without_issue_creates(self) -> None:
        assert _action(candidate_count=1, existing_issue=None) == "create"

    def test_non_empty_with_issue_appends(self) -> None:
        assert _action(candidate_count=1, existing_issue={"number": 1}) == "append"

    def test_empty_without_issue_silent(self) -> None:
        assert _action(candidate_count=0, existing_issue=None) == "silent"

    def test_empty_with_fresh_issue_silent(self) -> None:
        assert (
            _action(candidate_count=0, existing_issue={"number": 1}, idle_days=27)
            == "silent"
        )

    def test_empty_with_idle_issue_closes(self) -> None:
        assert (
            _action(candidate_count=0, existing_issue={"number": 1}, idle_days=29)
            == "close"
        )

    def test_exact_idle_threshold_closes(self) -> None:
        assert (
            _action(candidate_count=0, existing_issue={"number": 1}, idle_days=28)
            == "close"
        )


class TestSideEffectWrappers:
    def test_list_branches_parses_rows(self) -> None:
        assert branch_cleanup.list_branches("o/r", runner=_runner(["a\tsha1\nb\tsha2\n"])) == [
            ("a", "sha1"),
            ("b", "sha2"),
        ]

    def test_list_branches_empty_repo(self) -> None:
        assert branch_cleanup.list_branches("o/r", runner=_runner([""])) == []

    def test_list_branches_rejects_malformed_row(self) -> None:
        with pytest.raises(ValueError, match="malformed branch row"):
            branch_cleanup.list_branches("o/r", runner=_runner(["not-tabbed\n"]))

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("2026-01-02T03:04:05Z\n", datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)),
            (
                "2026-01-02T03:04:05+00:00\n",
                datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            ),
        ],
    )
    def test_get_last_commit_date(self, raw: str, expected: datetime) -> None:
        assert branch_cleanup.get_last_commit_date("o/r", "sha", runner=_runner([raw])) == expected

    def test_get_last_commit_date_rejects_malformed_date(self) -> None:
        with pytest.raises(ValueError, match="malformed GitHub datetime"):
            branch_cleanup.get_last_commit_date("o/r", "sha", runner=_runner(["nope\n"]))

    @pytest.mark.parametrize(("raw", "expected"), [("0\n", 0), ("1\n", 1), ("3\n", 3)])
    def test_count_open_prs_for_head(self, raw: str, expected: int) -> None:
        assert branch_cleanup.count_open_prs_for_head("o/r", "b", runner=_runner([raw])) == expected

    def test_find_rolling_issue_exact_title(self) -> None:
        payload = '[{"number": 1, "title": "other"}, {"number": 2, "title": "target", "createdAt": "2026-01-01T00:00:00Z"}]'
        assert branch_cleanup.find_rolling_issue("o/r", "target", runner=_runner([payload])) == {
            "number": 2,
            "title": "target",
            "created_at": "2026-01-01T00:00:00Z",
        }

    def test_fetch_issue_last_activity_uses_last_comment(self) -> None:
        assert branch_cleanup.fetch_issue_last_activity(
            "o/r",
            7,
            runner=_runner(
                [
                    "2026-01-01T00:00:00Z\n",
                    "2026-01-02T00:00:00Z\n2026-01-03T00:00:00Z\n",
                ]
            ),
        ) == datetime(2026, 1, 3, tzinfo=UTC)

    def test_fetch_issue_last_activity_falls_back_to_created_at(self) -> None:
        assert branch_cleanup.fetch_issue_last_activity(
            "o/r",
            7,
            runner=_runner(["2026-01-01T00:00:00Z\n", ""]),
        ) == datetime(2026, 1, 1, tzinfo=UTC)


class TestRenderSurvey:
    def test_empty_repo_prints_none_and_zero_count(self) -> None:
        summary, comment, count = branch_cleanup.render_survey(
            repo="o/r",
            dry_run_raw="true",
            min_age_days_raw="60",
            default_branch="main",
            event_name="workflow_dispatch",
            run_url="https://example.test/run",
            now_utc=_dt(2026, 1, 31),
            runner=_runner([""]),
        )
        assert "Total branches: `0`" in summary
        assert "| _(none)_ | - | - | - |" in summary
        assert comment is None
        assert count == 0

    def test_single_old_orphan_is_listed(self) -> None:
        summary, comment, count = branch_cleanup.render_survey(
            repo="o/r",
            dry_run_raw="true",
            min_age_days_raw="60",
            default_branch="main",
            event_name="schedule",
            run_url="https://example.test/run",
            now_utc=_dt(2026, 3, 10),
            runner=_runner(
                [
                    "old\tabcdef123456\n",
                    "2026-01-01T00:00:00Z\n",
                    "0\n",
                ]
            ),
        )
        assert "| `old` | 2026-01-01T00:00:00Z | 68 | `abcdef1` |" in summary
        assert comment is not None
        assert "## Run 2026-03-10T00:00:00Z" in comment
        assert count == 1

    def test_old_branch_with_open_pr_is_excluded(self) -> None:
        summary, comment, count = branch_cleanup.render_survey(
            repo="o/r",
            dry_run_raw="true",
            min_age_days_raw="60",
            default_branch="main",
            event_name="schedule",
            run_url="https://example.test/run",
            now_utc=_dt(2026, 3, 10),
            runner=_runner(
                [
                    "old\tabcdef123456\n",
                    "2026-01-01T00:00:00Z\n",
                    "1\n",
                ]
            ),
        )
        assert "| `old` |" not in summary
        assert comment is None
        assert count == 0


class TestCLISurvey:
    def test_writes_comment_file_and_github_output(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        out = tmp_path / "comment.md"
        github_output = tmp_path / "github-output.txt"
        monkeypatch.setattr(branch_cleanup, "_now_utc", lambda: _dt(2026, 3, 10))
        monkeypatch.setattr(
            branch_cleanup,
            "render_survey",
            lambda **_kwargs: ("summary\n", "comment\n", 1),
        )

        rc = branch_cleanup.main(
            [
                "survey",
                "--repo",
                "o/r",
                "--dry-run",
                "true",
                "--min-age-days",
                "60",
                "--default-branch",
                "main",
                "--out",
                str(out),
                "--github-output",
                str(github_output),
            ]
        )

        assert rc == 0
        captured = capsys.readouterr()
        assert captured.out == "summary\n"
        assert "candidate_count=1" in captured.err
        assert out.read_text() == "comment\n"
        assert github_output.read_text() == "candidate_count=1\n"


class TestCLIReconcile:
    def test_create(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        calls: list[str] = []
        monkeypatch.setattr(branch_cleanup, "find_rolling_issue", lambda *_a, **_k: None)
        monkeypatch.setattr(branch_cleanup, "create_issue", lambda *_a, **_k: calls.append("create"))
        assert _run_reconcile(tmp_path, candidate_count=1) == 0
        assert calls == ["create"]

    def test_append(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        calls: list[str] = []
        monkeypatch.setattr(branch_cleanup, "find_rolling_issue", lambda *_a, **_k: {"number": 7})
        monkeypatch.setattr(branch_cleanup, "fetch_issue_last_activity", lambda *_a, **_k: _dt(2026, 1, 1))
        monkeypatch.setattr(branch_cleanup, "comment_on_issue", lambda *_a, **_k: calls.append("append"))
        assert _run_reconcile(tmp_path, candidate_count=1) == 0
        assert calls == ["append"]

    def test_silent_without_issue(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        calls: list[str] = []
        monkeypatch.setattr(branch_cleanup, "find_rolling_issue", lambda *_a, **_k: None)
        monkeypatch.setattr(branch_cleanup, "create_issue", lambda *_a, **_k: calls.append("create"))
        assert _run_reconcile(tmp_path, candidate_count=0) == 0
        assert calls == []

    def test_silent_with_fresh_issue(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        calls: list[str] = []
        monkeypatch.setattr(branch_cleanup, "_now_utc", lambda: _dt(2026, 1, 20))
        monkeypatch.setattr(branch_cleanup, "find_rolling_issue", lambda *_a, **_k: {"number": 7})
        monkeypatch.setattr(branch_cleanup, "fetch_issue_last_activity", lambda *_a, **_k: _dt(2026, 1, 1))
        monkeypatch.setattr(branch_cleanup, "close_issue_with_comment", lambda *_a, **_k: calls.append("close"))
        assert _run_reconcile(tmp_path, candidate_count=0) == 0
        assert calls == []

    def test_close_idle_issue(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        calls: list[str] = []
        monkeypatch.setattr(branch_cleanup, "_now_utc", lambda: _dt(2026, 2, 1))
        monkeypatch.setattr(branch_cleanup, "find_rolling_issue", lambda *_a, **_k: {"number": 7})
        monkeypatch.setattr(branch_cleanup, "fetch_issue_last_activity", lambda *_a, **_k: _dt(2026, 1, 1))
        monkeypatch.setattr(branch_cleanup, "close_issue_with_comment", lambda *_a, **_k: calls.append("close"))
        assert _run_reconcile(tmp_path, candidate_count=0) == 0
        assert calls == ["close"]


def _candidate(
    *,
    branch: str = "feature",
    default_branch: str = "main",
    last_commit_days_ago: int = 61,
    min_age_days: int = 60,
    has_open_pr: bool = False,
) -> bool:
    now = _dt(2026, 3, 10)
    return branch_cleanup.is_candidate(
        branch=branch,
        default_branch=default_branch,
        last_commit_utc=now - timedelta(days=last_commit_days_ago),
        now_utc=now,
        min_age_days=min_age_days,
        has_open_pr=has_open_pr,
    )


def _action(
    *,
    candidate_count: int,
    existing_issue: dict[str, Any] | None,
    idle_days: int = 0,
) -> branch_cleanup.IssueAction:
    return branch_cleanup.decide_issue_action(
        candidate_count=candidate_count,
        existing_issue=existing_issue,
        idle_seconds=idle_days * branch_cleanup.SECONDS_PER_DAY,
        idle_threshold_seconds=28 * branch_cleanup.SECONDS_PER_DAY,
    )


def _runner(outputs: list[str]):
    queue = list(outputs)

    def run(cmd, **kwargs):
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        assert kwargs["check"] is True
        assert kwargs["timeout"] == 30
        if not queue:
            raise AssertionError(f"unexpected command: {cmd}")
        return _Result(queue.pop(0))

    return run


def _run_reconcile(tmp_path: Path, *, candidate_count: int) -> int:
    comment = tmp_path / "comment.md"
    comment.write_text("body\n")
    return branch_cleanup.main(
        [
            "reconcile",
            "--repo",
            "o/r",
            "--title",
            "summary",
            "--candidate-count",
            str(candidate_count),
            "--comment-file",
            str(comment),
            "--idle-close-days",
            "28",
            "--run-url",
            "https://example.test/run",
        ]
    )


def _dt(year: int, month: int, day: int) -> datetime:
    return datetime(year, month, day, tzinfo=UTC)
