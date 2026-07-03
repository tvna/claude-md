"""Tests for ``scripts/branch_cleanup.py``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import branch_cleanup
import pytest

pytestmark = pytest.mark.shard_ci_ops


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
    def test_list_branches_parses_rows(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(
            branch_cleanup,
            "paginate",
            lambda *_a, **_k: [
                {"name": "a", "commit": {"sha": "sha1"}},
                {"name": "b", "commit": {"sha": "sha2"}},
            ],
        )
        assert branch_cleanup.list_branches("o/r") == [("a", "sha1"), ("b", "sha2")]

    def test_list_branches_empty_repo(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(branch_cleanup, "paginate", lambda *_a, **_k: [])
        assert branch_cleanup.list_branches("o/r") == []

    def test_list_branches_rejects_malformed_row(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            branch_cleanup, "paginate", lambda *_a, **_k: [{"name": "a", "commit": {}}]
        )
        with pytest.raises(ValueError, match="malformed branch row"):
            branch_cleanup.list_branches("o/r")

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("2026-01-02T03:04:05Z", datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)),
            (
                "2026-01-02T03:04:05+00:00",
                datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC),
            ),
        ],
    )
    def test_get_last_commit_date(
        self, raw: str, expected: datetime, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            branch_cleanup,
            "rest_json",
            lambda *_a, **_k: {"commit": {"committer": {"date": raw}}},
        )
        assert branch_cleanup.get_last_commit_date("o/r", "sha") == expected

    def test_get_last_commit_date_rejects_malformed_date(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            branch_cleanup,
            "rest_json",
            lambda *_a, **_k: {"commit": {"committer": {"date": "nope"}}},
        )
        with pytest.raises(ValueError, match="malformed GitHub datetime"):
            branch_cleanup.get_last_commit_date("o/r", "sha")

    @pytest.mark.parametrize("count", [0, 1, 3])
    def test_count_open_prs_for_head(
        self, count: int, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            branch_cleanup, "paginate", lambda *_a, **_k: [{"number": i} for i in range(count)]
        )
        assert branch_cleanup.count_open_prs_for_head("o/r", "b") == count

    def test_count_open_prs_encodes_reserved_branch_chars(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # A branch name with `#` / `&` must be percent-encoded so it is not
        # parsed as a URL fragment / extra query param (Codex review on #2122).
        seen: dict[str, str] = {}

        def _fake(path: str, *, token: str, **_kw: object) -> list[dict[str, object]]:
            seen["path"] = path
            return []

        monkeypatch.setattr(branch_cleanup, "paginate", _fake)
        branch_cleanup.count_open_prs_for_head("owner/repo", "fix/a#b&c")
        # `:` and `/` stay literal; `#` and `&` are encoded.
        assert "head=owner:fix/a%23b%26c" in seen["path"]
        assert "#" not in seen["path"]

    def test_find_rolling_issue_exact_title(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            branch_cleanup,
            "rest_json",
            lambda *_a, **_k: {
                "items": [
                    {"number": 1, "title": "other"},
                    {"number": 2, "title": "target", "created_at": "2026-01-01T00:00:00Z"},
                ]
            },
        )
        assert branch_cleanup.find_rolling_issue("o/r", "target") == {
            "number": 2,
            "title": "target",
            "created_at": "2026-01-01T00:00:00Z",
        }

    def test_fetch_issue_last_activity_uses_last_comment(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            branch_cleanup,
            "rest_json",
            lambda *_a, **_k: {"created_at": "2026-01-01T00:00:00Z"},
        )
        monkeypatch.setattr(
            branch_cleanup,
            "paginate",
            lambda *_a, **_k: [
                {"created_at": "2026-01-02T00:00:00Z"},
                {"created_at": "2026-01-03T00:00:00Z"},
            ],
        )
        assert branch_cleanup.fetch_issue_last_activity("o/r", 7) == datetime(
            2026, 1, 3, tzinfo=UTC
        )

    def test_fetch_issue_last_activity_falls_back_to_created_at(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            branch_cleanup,
            "rest_json",
            lambda *_a, **_k: {"created_at": "2026-01-01T00:00:00Z"},
        )
        monkeypatch.setattr(branch_cleanup, "paginate", lambda *_a, **_k: [])
        assert branch_cleanup.fetch_issue_last_activity("o/r", 7) == datetime(
            2026, 1, 1, tzinfo=UTC
        )


class TestCreateIssue:
    def test_labels_come_from_the_ssot_registry(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        calls: list[dict[str, Any] | None] = []

        def _fake_rest_json(method: str, path: str, body: dict[str, Any] | None = None, **_kw: object) -> None:
            calls.append(body)

        monkeypatch.setattr(branch_cleanup, "rest_json", _fake_rest_json)
        monkeypatch.setattr(
            branch_cleanup._ssot,
            "consumer_labels",
            lambda path: ("area:example", "type:docs"),
        )

        body_file = tmp_path / "body.md"
        body_file.write_text("body\n", encoding="utf-8")
        branch_cleanup.create_issue("o/r", "title", body_file)

        assert calls == [
            {"title": "title", "body": "body\n", "labels": ["area:example", "type:docs"]}
        ]


def _stub_survey_io(
    monkeypatch: pytest.MonkeyPatch,
    *,
    branches: list[tuple[str, str]],
    commit_date: datetime = datetime(2026, 1, 1, tzinfo=UTC),
    open_prs: int = 0,
) -> None:
    monkeypatch.setattr(branch_cleanup, "list_branches", lambda *_a, **_k: branches)
    monkeypatch.setattr(branch_cleanup, "get_last_commit_date", lambda *_a, **_k: commit_date)
    monkeypatch.setattr(branch_cleanup, "count_open_prs_for_head", lambda *_a, **_k: open_prs)


class TestRenderSurvey:
    def test_empty_repo_prints_none_and_zero_count(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_survey_io(monkeypatch, branches=[])
        summary, comment, count = branch_cleanup.render_survey(
            repo="o/r",
            dry_run_raw="true",
            min_age_days_raw="60",
            default_branch="main",
            event_name="workflow_dispatch",
            run_url="https://example.test/run",
            now_utc=_dt(2026, 1, 31),
        )
        assert "Total branches: `0`" in summary
        assert "| _(none)_ | - | - | - |" in summary
        assert comment is None
        assert count == 0

    def test_single_old_orphan_is_listed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_survey_io(
            monkeypatch,
            branches=[("old", "abcdef123456")],
            commit_date=_dt(2026, 1, 1),
            open_prs=0,
        )
        summary, comment, count = branch_cleanup.render_survey(
            repo="o/r",
            dry_run_raw="true",
            min_age_days_raw="60",
            default_branch="main",
            event_name="schedule",
            run_url="https://example.test/run",
            now_utc=_dt(2026, 3, 10),
        )
        assert "| `old` | 2026-01-01T00:00:00Z | 68 | `abcdef1` |" in summary
        assert comment is not None
        assert "## Run 2026-03-10T00:00:00Z" in comment
        assert count == 1

    def test_old_branch_with_open_pr_is_excluded(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _stub_survey_io(
            monkeypatch,
            branches=[("old", "abcdef123456")],
            commit_date=_dt(2026, 1, 1),
            open_prs=1,
        )
        summary, comment, count = branch_cleanup.render_survey(
            repo="o/r",
            dry_run_raw="true",
            min_age_days_raw="60",
            default_branch="main",
            event_name="schedule",
            run_url="https://example.test/run",
            now_utc=_dt(2026, 3, 10),
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
