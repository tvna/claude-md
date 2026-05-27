"""Tests for ``scripts/analyze_ci_timings.py`` (issue #474).

The ``scripts/`` directory is added to ``sys.path`` via the
``pythonpath`` key under ``[tool.pytest.ini_options]`` in
``pyproject.toml``.
"""

from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from datetime import UTC, datetime
from pathlib import Path

import analyze_ci_timings
import pytest


def _make_job(
    *,
    name: str,
    workflow_name: str = "Verify agent instructions",
    started_at: str = "2026-05-20T12:00:00Z",
    completed_at: str = "2026-05-20T12:01:00Z",
    steps: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "name": name,
        "workflow_name": workflow_name,
        "started_at": started_at,
        "completed_at": completed_at,
        "steps": steps if steps is not None else [],
    }


def _write_jobs(tmp_path: Path, name: str, jobs: list[dict[str, object]]) -> Path:
    path = tmp_path / name
    path.write_text(json.dumps({"jobs": jobs}), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Numeric helpers
# ---------------------------------------------------------------------------


class TestPercentile:
    def test_empty_returns_zero(self) -> None:
        assert analyze_ci_timings._percentile([], 50) == 0.0

    def test_single_value(self) -> None:
        assert analyze_ci_timings._percentile([42.0], 95) == 42.0

    def test_p50_of_even_count(self) -> None:
        # Linear interpolation: midpoint of 10 and 20 -> 15.
        assert analyze_ci_timings._percentile([10.0, 20.0], 50) == 15.0

    def test_p95_of_known_distribution(self) -> None:
        values = [float(x) for x in range(1, 101)]
        # Linear interpolation index = 99 * 0.95 = 94.05 -> 95.05.
        assert analyze_ci_timings._percentile(values, 95) == pytest.approx(95.05)

    def test_max_equals_p100(self) -> None:
        values = [1.0, 5.0, 9.0]
        assert analyze_ci_timings._percentile(values, 100) == 9.0


class TestDurationSeconds:
    def test_simple_minute(self) -> None:
        assert analyze_ci_timings._duration_seconds(
            "2026-05-20T12:00:00Z", "2026-05-20T12:01:00Z"
        ) == 60.0

    def test_missing_endpoints_returns_none(self) -> None:
        assert analyze_ci_timings._duration_seconds(None, "2026-05-20T12:01:00Z") is None
        assert analyze_ci_timings._duration_seconds("2026-05-20T12:00:00Z", None) is None
        assert analyze_ci_timings._duration_seconds("", "") is None

    def test_negative_returns_none(self) -> None:
        # Clock skew between runners has been observed; reject rather
        # than poison the aggregate with a negative sample.
        assert (
            analyze_ci_timings._duration_seconds(
                "2026-05-20T12:01:00Z", "2026-05-20T12:00:00Z"
            )
            is None
        )

    def test_unparsable_returns_none(self) -> None:
        assert analyze_ci_timings._duration_seconds("not-a-ts", "2026-05-20T12:01:00Z") is None


class TestTrendArrow:
    def test_insufficient_samples(self) -> None:
        assert analyze_ci_timings._trend_arrow([]) == "?"
        assert analyze_ci_timings._trend_arrow([1.0]) == "?"

    def test_flat_within_band(self) -> None:
        assert analyze_ci_timings._trend_arrow([10.0, 10.5, 10.2, 9.9, 10.3]) == "="

    def test_rising_above_band(self) -> None:
        assert analyze_ci_timings._trend_arrow([10.0, 10.0, 30.0, 30.0, 30.0]) == "^"

    def test_falling_below_band(self) -> None:
        assert analyze_ci_timings._trend_arrow([30.0, 30.0, 10.0, 10.0, 10.0]) == "v"

    def test_uses_only_last_five(self) -> None:
        # Older samples must not pull the trend back to flat.
        samples = [100.0] * 10 + [5.0, 5.0, 5.0, 5.0, 5.0]
        assert analyze_ci_timings._trend_arrow(samples) == "="
        # ...whereas one transitional slow value inside the window
        # should not flip the indicator if the medians stay close.
        samples = [5.0, 5.0, 5.0, 100.0, 5.0]
        assert analyze_ci_timings._trend_arrow(samples) == "="

    def test_zero_older_median(self) -> None:
        assert analyze_ci_timings._trend_arrow([0.0, 0.0, 0.0, 0.0, 0.0]) == "="
        # Older half median 0, newer half median 5 -> divide-by-zero
        # guard returns the rising indicator.
        assert analyze_ci_timings._trend_arrow([0.0, 0.0, 0.0, 5.0, 5.0]) == "^"


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


class TestLoadJobs:
    def test_loads_from_file(self, tmp_path: Path) -> None:
        path = _write_jobs(tmp_path, "j1.json", [_make_job(name="a"), _make_job(name="b")])
        jobs = analyze_ci_timings.load_jobs([path])
        assert [str(j["name"]) for j in jobs] == ["a", "b"]

    def test_loads_from_directory(self, tmp_path: Path) -> None:
        _write_jobs(tmp_path, "r1.json", [_make_job(name="a")])
        _write_jobs(tmp_path, "r2.json", [_make_job(name="b")])
        jobs = analyze_ci_timings.load_jobs([tmp_path])
        assert sorted(str(j["name"]) for j in jobs) == ["a", "b"]

    def test_skips_non_jobs_payload(self, tmp_path: Path) -> None:
        # A runs.json dump accidentally dropped into the same folder
        # must not crash the analyzer.
        runs = tmp_path / "runs.json"
        runs.write_text(json.dumps({"workflow_runs": [{"id": 1}]}), encoding="utf-8")
        jobs = analyze_ci_timings.load_jobs([tmp_path])
        assert jobs == []

    def test_skips_non_object_root(self, tmp_path: Path) -> None:
        path = tmp_path / "weird.json"
        path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        assert analyze_ci_timings.load_jobs([path]) == []

    def test_skips_non_dict_job_entries(self, tmp_path: Path) -> None:
        path = tmp_path / "mixed.json"
        path.write_text(json.dumps({"jobs": [_make_job(name="a"), "garbage"]}), encoding="utf-8")
        jobs = analyze_ci_timings.load_jobs([path])
        assert [j["name"] for j in jobs] == ["a"]


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


class TestFilterJobs:
    def test_workflow_name(self) -> None:
        jobs = [
            _make_job(name="a", workflow_name="Verify agent instructions"),
            _make_job(name="b", workflow_name="Something Else"),
        ]
        result = analyze_ci_timings.filter_jobs(
            jobs, workflow_name="Verify agent instructions"
        )
        assert [j["name"] for j in result] == ["a"]

    def test_job_name(self) -> None:
        jobs = [_make_job(name="lint-scripts-static"), _make_job(name="gate")]
        result = analyze_ci_timings.filter_jobs(jobs, job_name="gate")
        assert [j["name"] for j in result] == ["gate"]

    def test_since_drops_older(self) -> None:
        jobs = [
            _make_job(name="old", started_at="2026-04-01T00:00:00Z", completed_at="2026-04-01T00:01:00Z"),
            _make_job(name="new", started_at="2026-05-20T00:00:00Z", completed_at="2026-05-20T00:01:00Z"),
        ]
        since = datetime(2026, 5, 1, tzinfo=UTC)
        result = analyze_ci_timings.filter_jobs(jobs, since=since)
        assert [j["name"] for j in result] == ["new"]

    def test_since_drops_unparseable_start(self) -> None:
        jobs = [_make_job(name="x", started_at="not-a-ts", completed_at="2026-05-20T00:01:00Z")]
        since = datetime(2026, 5, 1, tzinfo=UTC)
        assert analyze_ci_timings.filter_jobs(jobs, since=since) == []

    def test_no_filters_returns_input(self) -> None:
        jobs = [_make_job(name="a")]
        assert analyze_ci_timings.filter_jobs(jobs) == jobs


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


class TestAggregateJobDurations:
    def test_groups_by_name_and_sorts_chronologically(self) -> None:
        jobs = [
            _make_job(
                name="lint-scripts-static",
                started_at="2026-05-20T12:00:00Z",
                completed_at="2026-05-20T12:00:30Z",
            ),
            _make_job(
                name="lint-scripts-static",
                started_at="2026-05-19T12:00:00Z",
                completed_at="2026-05-19T12:00:45Z",
            ),
            _make_job(
                name="gate",
                started_at="2026-05-20T12:01:00Z",
                completed_at="2026-05-20T12:01:05Z",
            ),
        ]
        agg = analyze_ci_timings.aggregate_job_durations(jobs)
        assert set(agg) == {"lint-scripts-static", "gate"}
        static_samples = [v for _, v in agg["lint-scripts-static"]]
        assert static_samples == [45.0, 30.0]  # sorted by start time, older first
        assert [v for _, v in agg["gate"]] == [5.0]

    def test_drops_jobs_missing_endpoints(self) -> None:
        jobs = [
            _make_job(
                name="a",
                started_at="2026-05-20T12:00:00Z",
                completed_at="",
            ),
            _make_job(
                name="a",
                started_at="2026-05-20T12:00:00Z",
                completed_at="2026-05-20T12:00:30Z",
            ),
        ]
        agg = analyze_ci_timings.aggregate_job_durations(jobs)
        assert [v for _, v in agg["a"]] == [30.0]

    def test_drops_non_string_name(self) -> None:
        # The GitHub API has shipped null name fields in edge cases;
        # guard rather than crash.
        jobs: list[dict[str, object]] = [
            {
                "name": None,
                "started_at": "2026-05-20T12:00:00Z",
                "completed_at": "2026-05-20T12:00:30Z",
            }
        ]
        assert analyze_ci_timings.aggregate_job_durations(jobs) == {}


class TestAggregateStepDurations:
    def test_buckets_by_job_and_step(self) -> None:
        jobs = [
            _make_job(
                name="lint-scripts-static",
                steps=[
                    {
                        "name": "Set up uv",
                        "started_at": "2026-05-20T12:00:00Z",
                        "completed_at": "2026-05-20T12:00:10Z",
                    },
                    {
                        "name": "ruff check",
                        "started_at": "2026-05-20T12:00:10Z",
                        "completed_at": "2026-05-20T12:00:15Z",
                    },
                ],
            ),
            _make_job(
                name="lint-scripts-static",
                steps=[
                    {
                        "name": "Set up uv",
                        "started_at": "2026-05-21T12:00:00Z",
                        "completed_at": "2026-05-21T12:00:08Z",
                    },
                ],
            ),
        ]
        agg = analyze_ci_timings.aggregate_step_durations(jobs)
        assert set(agg) == {
            ("lint-scripts-static", "Set up uv"),
            ("lint-scripts-static", "ruff check"),
        }
        setup = [v for _, v in agg[("lint-scripts-static", "Set up uv")]]
        assert setup == [10.0, 8.0]

    def test_skips_steps_without_endpoints(self) -> None:
        jobs = [
            _make_job(
                name="a",
                steps=[
                    {"name": "skipped", "started_at": "2026-05-20T12:00:00Z", "completed_at": None},
                    {"name": "ok", "started_at": "2026-05-20T12:00:00Z", "completed_at": "2026-05-20T12:00:05Z"},
                ],
            ),
        ]
        agg = analyze_ci_timings.aggregate_step_durations(jobs)
        assert list(agg) == [("a", "ok")]

    def test_skips_jobs_with_no_steps_list(self) -> None:
        jobs: list[dict[str, object]] = [{"name": "a", "steps": "not-a-list"}]
        assert analyze_ci_timings.aggregate_step_durations(jobs) == {}

    def test_skips_non_dict_step_entries(self) -> None:
        jobs: list[dict[str, object]] = [{"name": "a", "steps": ["garbage"]}]
        assert analyze_ci_timings.aggregate_step_durations(jobs) == {}


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class TestRenderReport:
    def _sample_jobs(self) -> list[dict[str, object]]:
        return [
            _make_job(
                name="lint-scripts-static",
                started_at="2026-05-20T12:00:00Z",
                completed_at="2026-05-20T12:00:30Z",
                steps=[
                    {
                        "name": "Set up uv",
                        "started_at": "2026-05-20T12:00:00Z",
                        "completed_at": "2026-05-20T12:00:10Z",
                    },
                ],
            ),
            _make_job(
                name="lint-scripts-static",
                started_at="2026-05-21T12:00:00Z",
                completed_at="2026-05-21T12:00:40Z",
                steps=[
                    {
                        "name": "Set up uv",
                        "started_at": "2026-05-21T12:00:00Z",
                        "completed_at": "2026-05-21T12:00:08Z",
                    },
                ],
            ),
        ]

    def test_report_has_header_and_columns(self) -> None:
        report = analyze_ci_timings.render_report(self._sample_jobs(), title="ci report")
        assert report.startswith("# ci report")
        assert "Aggregated over 2 job execution(s)." in report
        assert "## Per-job durations" in report
        assert "## Per-step durations" in report
        assert "| job | count | p50 | p95 | max | trend(5) |" in report
        assert "| job | step | count | p50 | p95 | max | trend(5) |" in report

    def test_report_contains_aggregate_values(self) -> None:
        report = analyze_ci_timings.render_report(self._sample_jobs(), title="t")
        assert "lint-scripts-static" in report
        assert "Set up uv" in report
        # p50 of [30, 40] = 35.0, max = 40.0.
        assert "35.0" in report
        assert "40.0" in report

    def test_empty_input_renders_placeholders(self) -> None:
        report = analyze_ci_timings.render_report([], title="empty")
        assert "_no job samples_" in report
        assert "_no step samples_" in report
        assert "Aggregated over 0 job execution(s)." in report

    def test_report_is_ascii_safe(self) -> None:
        # The operator pastes this directly into a GitHub comment; the
        # repo's non-ASCII gate (scripts/preflight_non_ascii.py) would
        # otherwise reject the comment.
        report = analyze_ci_timings.render_report(self._sample_jobs(), title="t")
        report.encode("ascii")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


class TestCli:
    def _run(self, argv: list[str]) -> tuple[int, str]:
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = analyze_ci_timings.main(argv)
        return rc, buf.getvalue()

    def test_jobs_flag_required(self) -> None:
        with pytest.raises(SystemExit) as exc:
            analyze_ci_timings.main([])
        assert exc.value.code == 2

    def test_end_to_end_directory(self, tmp_path: Path) -> None:
        _write_jobs(
            tmp_path,
            "r1.json",
            [
                _make_job(
                    name="gate",
                    started_at="2026-05-20T12:00:00Z",
                    completed_at="2026-05-20T12:00:05Z",
                ),
            ],
        )
        rc, out = self._run(["--jobs", str(tmp_path)])
        assert rc == 0
        assert "# CI timings report" in out
        assert "gate" in out
        assert "5.0" in out

    def test_workflow_filter_applies(self, tmp_path: Path) -> None:
        path = _write_jobs(
            tmp_path,
            "r1.json",
            [
                _make_job(name="a", workflow_name="Other"),
                _make_job(name="b", workflow_name="Verify agent instructions"),
            ],
        )
        rc, out = self._run(
            ["--jobs", str(path), "--workflow", "Verify agent instructions"]
        )
        assert rc == 0
        assert "| b |" in out
        assert "| a |" not in out

    def test_job_filter_applies(self, tmp_path: Path) -> None:
        path = _write_jobs(
            tmp_path,
            "r1.json",
            [_make_job(name="lint-scripts-static"), _make_job(name="gate")],
        )
        rc, out = self._run(["--jobs", str(path), "--job", "gate"])
        assert rc == 0
        assert "| gate |" in out
        assert "lint-scripts-static" not in out

    def test_since_filter_applies(self, tmp_path: Path) -> None:
        path = _write_jobs(
            tmp_path,
            "r1.json",
            [
                _make_job(
                    name="old",
                    started_at="2026-04-01T00:00:00Z",
                    completed_at="2026-04-01T00:00:30Z",
                ),
                _make_job(
                    name="new",
                    started_at="2026-05-20T00:00:00Z",
                    completed_at="2026-05-20T00:00:30Z",
                ),
            ],
        )
        rc, out = self._run(["--jobs", str(path), "--since", "2026-05-01"])
        assert rc == 0
        assert "| new |" in out
        assert "| old |" not in out

    def test_since_rejects_bad_format(self, tmp_path: Path) -> None:
        path = _write_jobs(tmp_path, "r.json", [_make_job(name="a")])
        with pytest.raises(SystemExit) as exc:
            analyze_ci_timings.main(["--jobs", str(path), "--since", "20260520"])
        assert exc.value.code == 2

    def test_custom_title(self, tmp_path: Path) -> None:
        path = _write_jobs(tmp_path, "r.json", [_make_job(name="a")])
        rc, out = self._run(["--jobs", str(path), "--title", "Sprint 4 report"])
        assert rc == 0
        assert out.startswith("# Sprint 4 report")
