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

pytestmark = pytest.mark.shard_ci_ops

def _make_job(
    *,
    name: str,
    workflow_name: str = "Verify repository scripts",
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
            _make_job(name="a", workflow_name="Verify repository scripts"),
            _make_job(name="b", workflow_name="Something Else"),
        ]
        result = analyze_ci_timings.filter_jobs(
            jobs, workflow_name="Verify repository scripts"
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
                _make_job(name="b", workflow_name="Verify repository scripts"),
            ],
        )
        rc, out = self._run(
            ["--jobs", str(path), "--workflow", "Verify repository scripts"]
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

    def test_cutoff_switches_to_compare_mode(self, tmp_path: Path) -> None:
        path = _write_jobs(
            tmp_path,
            "r.json",
            [
                _make_job(
                    name="lint-scripts-pytest",
                    started_at="2026-05-26T12:00:00Z",
                    completed_at="2026-05-26T12:03:20Z",
                ),
                _make_job(
                    name="lint-scripts-pytest-gate",
                    started_at="2026-05-28T12:00:00Z",
                    completed_at="2026-05-28T12:01:20Z",
                ),
            ],
        )
        rc, out = self._run(["--jobs", str(path), "--cutoff", "2026-05-28"])
        assert rc == 0
        # Compare-mode header is present and trend-mode header is absent.
        assert "Cutoff: 2026-05-28T00:00:00Z" in out
        assert "pre count" in out
        assert "post count" in out
        assert "delta p50" in out
        assert "trend(5)" not in out
        # pre-only and post-only rows render the right markers.
        assert "| lint-scripts-pytest |" in out
        assert "gone" in out
        assert "| lint-scripts-pytest-gate |" in out
        assert "new" in out

    def test_cutoff_rejects_bad_format(self, tmp_path: Path) -> None:
        path = _write_jobs(tmp_path, "r.json", [_make_job(name="a")])
        with pytest.raises(SystemExit) as exc:
            analyze_ci_timings.main(["--jobs", str(path), "--cutoff", "20260528"])
        assert exc.value.code == 2


# ---------------------------------------------------------------------------
# Compare-mode partitioning and rendering
# ---------------------------------------------------------------------------


class TestPartitionAggregatesByCutoff:
    def test_strict_pre_post_split(self) -> None:
        ts_pre = datetime(2026, 5, 26, 12, 0, tzinfo=UTC)
        ts_post = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
        agg = {"job-a": [(ts_pre, 100.0), (ts_post, 50.0)]}
        cutoff = datetime(2026, 5, 28, tzinfo=UTC)
        pre, post = analyze_ci_timings.partition_aggregates_by_cutoff(agg, cutoff)
        assert pre == {"job-a": [100.0]}
        assert post == {"job-a": [50.0]}

    def test_cutoff_boundary_is_post(self) -> None:
        # An execution started exactly at the cutoff lands in ``post``;
        # this matches the "merge timestamp = cutoff" convention so the
        # merge run itself is counted as post-change.
        ts = datetime(2026, 5, 28, 0, 0, tzinfo=UTC)
        agg = {"job-a": [(ts, 42.0)]}
        cutoff = datetime(2026, 5, 28, tzinfo=UTC)
        pre, post = analyze_ci_timings.partition_aggregates_by_cutoff(agg, cutoff)
        assert pre == {}
        assert post == {"job-a": [42.0]}

    def test_only_pre_keeps_name_out_of_post(self) -> None:
        ts = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)
        agg = {"only-pre": [(ts, 7.0)]}
        cutoff = datetime(2026, 5, 28, tzinfo=UTC)
        pre, post = analyze_ci_timings.partition_aggregates_by_cutoff(agg, cutoff)
        assert pre == {"only-pre": [7.0]}
        assert post == {}

    def test_only_post_keeps_name_out_of_pre(self) -> None:
        ts = datetime(2026, 5, 30, 12, 0, tzinfo=UTC)
        agg = {"only-post": [(ts, 9.0)]}
        cutoff = datetime(2026, 5, 28, tzinfo=UTC)
        pre, post = analyze_ci_timings.partition_aggregates_by_cutoff(agg, cutoff)
        assert pre == {}
        assert post == {"only-post": [9.0]}

    def test_step_key_tuple_supported(self) -> None:
        # The same generic helper partitions step-level aggregates whose
        # keys are (job, step) tuples.
        ts_pre = datetime(2026, 5, 26, tzinfo=UTC)
        ts_post = datetime(2026, 5, 30, tzinfo=UTC)
        agg = {
            ("gate", "setup"): [(ts_pre, 3.0), (ts_post, 2.0)],
        }
        cutoff = datetime(2026, 5, 28, tzinfo=UTC)
        pre, post = analyze_ci_timings.partition_aggregates_by_cutoff(agg, cutoff)
        assert pre == {("gate", "setup"): [3.0]}
        assert post == {("gate", "setup"): [2.0]}


class TestDeltaP50Marker:
    def test_pre_and_post_present_signed_pct(self) -> None:
        # pre p50 = 200, post p50 = 100 -> -50.0%.
        assert (
            analyze_ci_timings._delta_p50_marker([200.0, 200.0], [100.0, 100.0])
            == "-50.0%"
        )

    def test_post_slower_carries_plus_sign(self) -> None:
        assert (
            analyze_ci_timings._delta_p50_marker([100.0], [150.0])
            == "+50.0%"
        )

    def test_only_post_returns_new(self) -> None:
        assert analyze_ci_timings._delta_p50_marker([], [50.0]) == "new"

    def test_only_pre_returns_gone(self) -> None:
        assert analyze_ci_timings._delta_p50_marker([100.0], []) == "gone"

    def test_both_empty_returns_na(self) -> None:
        assert analyze_ci_timings._delta_p50_marker([], []) == "n/a"

    def test_zero_pre_with_post_returns_inf(self) -> None:
        assert analyze_ci_timings._delta_p50_marker([0.0], [5.0]) == "+inf"

    def test_zero_pre_and_zero_post_returns_zero(self) -> None:
        assert analyze_ci_timings._delta_p50_marker([0.0], [0.0]) == "0.0%"


class TestRenderCompareReport:
    def _bracket_jobs(self) -> list[dict[str, object]]:
        # 2 pre-cutoff runs of the old single job (p50 = 200s) and 3
        # post-cutoff runs of the new gate (p50 = 80s) plus a job present
        # in both windows so we exercise the signed delta branch too.
        return [
            _make_job(
                name="lint-scripts-pytest",
                started_at="2026-05-25T12:00:00Z",
                completed_at="2026-05-25T12:03:20Z",  # 200s
            ),
            _make_job(
                name="lint-scripts-pytest",
                started_at="2026-05-26T12:00:00Z",
                completed_at="2026-05-26T12:03:20Z",  # 200s
            ),
            _make_job(
                name="lint-scripts-pytest-gate",
                started_at="2026-05-28T12:00:00Z",
                completed_at="2026-05-28T12:01:20Z",  # 80s
            ),
            _make_job(
                name="lint-scripts-pytest-gate",
                started_at="2026-05-29T12:00:00Z",
                completed_at="2026-05-29T12:01:20Z",  # 80s
            ),
            _make_job(
                name="lint-scripts-pytest-gate",
                started_at="2026-05-30T12:00:00Z",
                completed_at="2026-05-30T12:01:20Z",  # 80s
            ),
            _make_job(
                name="lint-scripts-static",
                started_at="2026-05-26T12:00:00Z",
                completed_at="2026-05-26T12:00:50Z",  # 50s
            ),
            _make_job(
                name="lint-scripts-static",
                started_at="2026-05-29T12:00:00Z",
                completed_at="2026-05-29T12:00:55Z",  # 55s
            ),
        ]

    def test_header_lists_pre_and_post_totals(self) -> None:
        cutoff = datetime(2026, 5, 28, tzinfo=UTC)
        report = analyze_ci_timings.render_report(
            self._bracket_jobs(), title="t", cutoff=cutoff
        )
        assert report.startswith("# t")
        assert "Cutoff: 2026-05-28T00:00:00Z" in report
        # 3 pre-cutoff jobs (2 old pytest + 1 static), 4 post-cutoff (3 gate + 1 static).
        assert "Pre-cutoff job executions: 3." in report
        assert "Post-cutoff job executions: 4." in report

    def test_pre_only_row_renders_gone_marker(self) -> None:
        cutoff = datetime(2026, 5, 28, tzinfo=UTC)
        report = analyze_ci_timings.render_report(
            self._bracket_jobs(), title="t", cutoff=cutoff
        )
        lines = [r for r in report.splitlines() if "lint-scripts-pytest |" in r]
        # Pre-only row (the old single job): 2 pre samples, 0 post, marker "gone".
        assert any(
            r.startswith("| lint-scripts-pytest |") and r.endswith("| gone |")
            for r in lines
        )

    def test_post_only_row_renders_new_marker(self) -> None:
        cutoff = datetime(2026, 5, 28, tzinfo=UTC)
        report = analyze_ci_timings.render_report(
            self._bracket_jobs(), title="t", cutoff=cutoff
        )
        gate_row = next(
            r
            for r in report.splitlines()
            if r.startswith("| lint-scripts-pytest-gate |")
        )
        assert gate_row.endswith("| new |")
        assert "| 0 |" in gate_row  # pre count
        assert "| 3 |" in gate_row  # post count

    def test_both_windows_row_renders_signed_pct(self) -> None:
        cutoff = datetime(2026, 5, 28, tzinfo=UTC)
        report = analyze_ci_timings.render_report(
            self._bracket_jobs(), title="t", cutoff=cutoff
        )
        static_row = next(
            r
            for r in report.splitlines()
            if r.startswith("| lint-scripts-static |")
        )
        # pre p50 = 50.0, post p50 = 55.0 -> +10.0%.
        assert static_row.endswith("| +10.0% |")

    def test_compare_report_is_ascii_safe(self) -> None:
        cutoff = datetime(2026, 5, 28, tzinfo=UTC)
        report = analyze_ci_timings.render_report(
            self._bracket_jobs(), title="t", cutoff=cutoff
        )
        report.encode("ascii")

    def test_compare_report_does_not_emit_trend_legend(self) -> None:
        cutoff = datetime(2026, 5, 28, tzinfo=UTC)
        report = analyze_ci_timings.render_report(
            self._bracket_jobs(), title="t", cutoff=cutoff
        )
        # The trend indicator is meaningless when the delta column already
        # carries the pre-vs-post signal.
        assert "Trend legend" not in report
        assert "trend(5)" not in report
        assert "Delta legend" in report

    def test_compare_report_with_no_samples_renders_placeholders(self) -> None:
        cutoff = datetime(2026, 5, 28, tzinfo=UTC)
        report = analyze_ci_timings.render_report([], title="t", cutoff=cutoff)
        assert "_no job samples_" in report
        assert "_no step samples_" in report
        assert "Pre-cutoff job executions: 0." in report
        assert "Post-cutoff job executions: 0." in report


_T = datetime(2026, 5, 20, 12, 0, tzinfo=UTC)


def _samples(*durations: float) -> list[tuple[datetime, float]]:
    """Build (started_at, duration) samples in the aggregate_job_durations shape."""
    return [(_T, d) for d in durations]


class TestBudget:
    def test_budget_breaches_flags_over(self) -> None:
        agg = {"slow": _samples(400.0, 420.0), "fast": _samples(10.0)}
        assert analyze_ci_timings.budget_breaches(agg, 300.0) == [("slow", 410.0)]

    def test_budget_breaches_empty_when_under(self) -> None:
        assert analyze_ci_timings.budget_breaches({"j": _samples(10.0, 20.0)}, 300.0) == []

    def test_budget_uses_p50_not_max(self) -> None:
        # A single slow outlier must not trip the soft budget (median is 10).
        assert analyze_ci_timings.budget_breaches({"j": _samples(10.0, 10.0, 999.0)}, 300.0) == []

    def test_budget_skips_empty_samples(self) -> None:
        assert analyze_ci_timings.budget_breaches({"j": []}, 1.0) == []

    def test_report_includes_budget_breach(self) -> None:
        jobs = [
            _make_job(
                name="slow",
                started_at="2026-05-20T12:00:00Z",
                completed_at="2026-05-20T12:10:00Z",  # 600s
            )
        ]
        report = analyze_ci_timings.render_report(
            jobs, title="t", budget_seconds=300.0
        )
        assert "## Budget" in report
        assert "BUDGET BREACH" in report
        assert "slow" in report

    def test_report_budget_ok_when_under(self) -> None:
        jobs = [_make_job(name="fast")]  # default 60s
        report = analyze_ci_timings.render_report(
            jobs, title="t", budget_seconds=300.0
        )
        assert "## Budget" in report
        assert "BUDGET BREACH" not in report

    def test_report_omits_budget_section_when_none(self) -> None:
        report = analyze_ci_timings.render_report(
            [_make_job(name="j")], title="t"
        )
        assert "## Budget" not in report

    def test_cli_budget_flag(self, tmp_path: Path) -> None:
        jobs = [
            _make_job(
                name="slow",
                started_at="2026-05-20T12:00:00Z",
                completed_at="2026-05-20T12:10:00Z",
            )
        ]
        _write_jobs(tmp_path, "run.json", jobs)
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = analyze_ci_timings.main(
                ["--jobs", str(tmp_path), "--budget-seconds", "300", "--title", "t"]
            )
        assert rc == 0
        assert "BUDGET BREACH" in buf.getvalue()

    def test_budget_breach_payload_shape(self) -> None:
        agg = {"slow": _samples(400.0, 420.0), "fast": _samples(10.0)}
        payload = analyze_ci_timings.budget_breach_payload(agg, 300.0)
        assert payload == {
            "budget_seconds": 300.0,
            "breaches": [{"job": "slow", "p50": 410.0}],
        }

    def test_budget_breach_payload_empty_when_under(self) -> None:
        payload = analyze_ci_timings.budget_breach_payload(
            {"j": _samples(10.0, 20.0)}, 300.0
        )
        assert payload == {"budget_seconds": 300.0, "breaches": []}

    def test_cli_budget_output_writes_breach_json(self, tmp_path: Path) -> None:
        jobs = [
            _make_job(
                name="slow",
                started_at="2026-05-20T12:00:00Z",
                completed_at="2026-05-20T12:10:00Z",  # 600s
            )
        ]
        _write_jobs(tmp_path, "run.json", jobs)
        out_file = tmp_path / "budget.json"
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = analyze_ci_timings.main(
                [
                    "--jobs",
                    str(tmp_path),
                    "--budget-seconds",
                    "300",
                    "--budget-output",
                    str(out_file),
                ]
            )
        assert rc == 0
        payload = json.loads(out_file.read_text(encoding="utf-8"))
        assert payload["budget_seconds"] == 300.0
        assert payload["breaches"] == [{"job": "slow", "p50": 600.0}]

    def test_cli_budget_output_empty_when_under(self, tmp_path: Path) -> None:
        _write_jobs(tmp_path, "run.json", [_make_job(name="fast")])  # 60s
        out_file = tmp_path / "budget.json"
        buf = io.StringIO()
        with redirect_stdout(buf):
            rc = analyze_ci_timings.main(
                [
                    "--jobs",
                    str(tmp_path),
                    "--budget-seconds",
                    "300",
                    "--budget-output",
                    str(out_file),
                ]
            )
        assert rc == 0
        assert json.loads(out_file.read_text(encoding="utf-8"))["breaches"] == []

    def test_cli_budget_output_requires_budget_seconds(self, tmp_path: Path) -> None:
        _write_jobs(tmp_path, "run.json", [_make_job(name="a")])
        with pytest.raises(SystemExit) as exc:
            analyze_ci_timings.main(
                ["--jobs", str(tmp_path), "--budget-output", str(tmp_path / "b.json")]
            )
        assert exc.value.code == 2
