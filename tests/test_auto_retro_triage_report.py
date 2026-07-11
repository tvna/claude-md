"""Unit tests for the auto-retro cross-retro triage report.

Covers the pure aggregation (:func:`auto_retro.compute_triage_report`)
and the Markdown/Mermaid rendering
(:func:`auto_retro.render_triage_report_markdown`). Both are
GitHub-independent, so every case here is deterministic. Refs #1042.
"""

from __future__ import annotations

import _retro_labels as rl
import auto_retro as ar
import pytest

pytestmark = pytest.mark.shard_ci_ops


def _retro(
    number: int,
    signals: set[str],
    labels: set[str],
    state: str = "open",
    title: str = "",
) -> ar.PastRetro:
    return ar.PastRetro(
        number=number,
        signals=frozenset(signals),
        labels=frozenset(labels),
        state=state,
        title=title,
    )


class TestComputeTriageReport:
    """Triage-status tallies and per-signal stats over a population."""

    def test_empty_population_is_all_zero(self) -> None:
        report = ar.compute_triage_report([])
        assert report.total == 0
        assert report.label_counts[rl.RETRO_TP] == 0
        assert report.label_counts[ar._UNLABELLED_KEY] == 0
        assert report.anomalies == ()
        # Every signal still appears, with zero everything.
        names = {s.name for s in report.signal_stats}
        assert names == set(ar._SIGNAL_NAMES)
        for stat in report.signal_stats:
            assert stat.fire_count == 0
            assert stat.fire_rate == 0.0
            assert stat.fp_count == 0
            assert stat.fp_rate == 0.0

    def test_label_counts_are_independent_tallies(self) -> None:
        # A single retro carrying two triage labels increments both
        # buckets; counts need not sum to total.
        past = [
            _retro(1, {"multi_commit_pr"}, {rl.RETRO_FP, rl.RETRO_FP_CANDIDATE}),
            _retro(2, {"multi_commit_pr"}, {rl.RETRO_TP}),
        ]
        report = ar.compute_triage_report(past)
        assert report.total == 2
        assert report.label_counts[rl.RETRO_FP] == 1
        assert report.label_counts[rl.RETRO_FP_CANDIDATE] == 1
        assert report.label_counts[rl.RETRO_TP] == 1
        assert report.label_counts[rl.RETRO_TENTATIVE] == 0
        assert report.label_counts[ar._UNLABELLED_KEY] == 0

    def test_unlabelled_bucket_counts_retros_with_no_triage_label(self) -> None:
        past = [
            _retro(1, {"multi_commit_pr"}, set()),
            _retro(2, {"multi_commit_pr"}, {rl.RETRO_TP}),
        ]
        report = ar.compute_triage_report(past)
        assert report.label_counts[ar._UNLABELLED_KEY] == 1

    def test_signal_stats_mirror_prior_definition(self) -> None:
        # 3 fp + 2 tp over the same signal -> fire 5, fp 3, rate 0.6.
        past = [
            _retro(
                i,
                {"multi_commit_pr"},
                {rl.RETRO_FP if i < 3 else rl.RETRO_TP},
            )
            for i in range(5)
        ]
        report = ar.compute_triage_report(past)
        stat = next(
            s for s in report.signal_stats if s.name == "multi_commit_pr"
        )
        assert stat.fire_count == 5
        assert stat.sample_size == 5
        assert stat.fp_count == 3
        assert abs(stat.fp_rate - 0.6) < 1e-9
        assert abs(stat.fire_rate - 1.0) < 1e-9

    def test_fire_rate_is_over_total_population(self) -> None:
        # Signal fires on 1 of 4 retros -> fire_rate 0.25.
        past = [
            _retro(1, {"multi_commit_pr"}, {rl.RETRO_FP}),
            _retro(2, {"body_cites_refs"}, {rl.RETRO_TP}),
            _retro(3, {"body_cites_refs"}, {rl.RETRO_TP}),
            _retro(4, {"body_cites_refs"}, {rl.RETRO_TP}),
        ]
        report = ar.compute_triage_report(past)
        stat = next(
            s for s in report.signal_stats if s.name == "multi_commit_pr"
        )
        assert stat.fire_count == 1
        assert abs(stat.fire_rate - 0.25) < 1e-9


class TestAnomalyGate:
    """is_anomaly mirrors should_skip_by_prior's threshold + sample floor."""

    def test_high_fp_rate_below_sample_floor_is_not_anomaly(self) -> None:
        # All fp, but only 4 observations (< PRIOR_MIN_SAMPLE_SIZE=5).
        past = [
            _retro(i, {"multi_commit_pr"}, {rl.RETRO_FP})
            for i in range(rl.PRIOR_MIN_SAMPLE_SIZE - 1)
        ]
        report = ar.compute_triage_report(past)
        stat = next(
            s for s in report.signal_stats if s.name == "multi_commit_pr"
        )
        assert stat.fp_rate == 1.0
        assert not stat.is_anomaly
        assert report.anomalies == ()

    def test_high_fp_rate_at_sample_floor_is_anomaly(self) -> None:
        past = [
            _retro(i, {"multi_commit_pr"}, {rl.RETRO_FP})
            for i in range(rl.PRIOR_MIN_SAMPLE_SIZE)
        ]
        report = ar.compute_triage_report(past)
        stat = next(
            s for s in report.signal_stats if s.name == "multi_commit_pr"
        )
        assert stat.is_anomaly
        assert stat in report.anomalies

    def test_fp_rate_below_skip_threshold_is_not_anomaly(self) -> None:
        # 2 fp + 8 tp -> fp_rate 0.2 < PRIOR_SKIP_THRESHOLD over n=10.
        past = [
            _retro(
                i,
                {"multi_commit_pr"},
                {rl.RETRO_FP if i < 2 else rl.RETRO_TP},
            )
            for i in range(10)
        ]
        report = ar.compute_triage_report(past)
        stat = next(
            s for s in report.signal_stats if s.name == "multi_commit_pr"
        )
        assert not stat.is_anomaly


class TestRenderTriageReportMarkdown:
    """Rendering shape: headline anomalies, pie, and the signal table."""

    def test_empty_population_renders_without_pie(self) -> None:
        out = ar.render_triage_report_markdown(ar.compute_triage_report([]))
        assert "# Auto-retro triage report" in out
        assert "Retros observed: **0**" in out
        assert "No retros observed yet." in out
        # No pie block for an empty population (avoids an empty Mermaid pie).
        assert "```mermaid" not in out
        # Anomalies section present but empty.
        assert "## Anomalies" in out
        assert "None:" in out

    def test_anomaly_is_listed_at_top_and_flagged_in_table(self) -> None:
        past = [
            _retro(i, {"multi_commit_pr"}, {rl.RETRO_FP})
            for i in range(rl.PRIOR_MIN_SAMPLE_SIZE)
        ]
        out = ar.render_triage_report_markdown(
            ar.compute_triage_report(past)
        )
        # Headline anomaly bullet.
        assert "- `multi_commit_pr`: FP rate 1.00" in out
        # Table row carries the !! marker.
        assert "`multi_commit_pr`" in out
        assert "!!" in out

    def test_pie_lists_every_triage_bucket(self) -> None:
        past = [
            _retro(1, {"multi_commit_pr"}, {rl.RETRO_TP}),
            _retro(2, {"multi_commit_pr"}, {rl.RETRO_FP}),
        ]
        out = ar.render_triage_report_markdown(
            ar.compute_triage_report(past)
        )
        assert "```mermaid" in out
        assert "pie showData" in out
        for label in (*ar._TRIAGE_LABELS, ar._UNLABELLED_KEY):
            assert f'"{label}"' in out

    def test_output_is_deterministic(self) -> None:
        past = [
            _retro(1, {"multi_commit_pr", "body_cites_refs"}, {rl.RETRO_FP}),
            _retro(2, {"fix_typed_title"}, {rl.RETRO_TP}),
        ]
        report = ar.compute_triage_report(past)
        first = ar.render_triage_report_markdown(report)
        second = ar.render_triage_report_markdown(report)
        assert first == second
        assert first.endswith("\n")


class TestOpenUntriaged:
    """open_untriaged counts open retros carrying no triage label (#1386)."""

    def test_counts_only_open_and_unlabelled(self) -> None:
        past = [
            _retro(1, {"multi_commit_pr"}, set(), state="open"),  # counts
            _retro(2, {"multi_commit_pr"}, set(), state="closed"),  # closed
            _retro(3, {"multi_commit_pr"}, {rl.RETRO_FP}, state="open"),  # triaged
            _retro(4, {"multi_commit_pr"}, set(), state="open"),  # counts
        ]
        report = ar.compute_triage_report(past)
        assert report.open_untriaged == 2

    def test_zero_when_empty(self) -> None:
        assert ar.compute_triage_report([]).open_untriaged == 0

    def test_rendered_in_header(self) -> None:
        past = [_retro(1, {"multi_commit_pr"}, set(), state="open")]
        out = ar.render_triage_report_markdown(ar.compute_triage_report(past))
        assert "Open untriaged: **1**" in out


class TestRecentRetros:
    """The recent-retros list is newest-first and capped (#1386)."""

    def test_newest_first_order(self) -> None:
        past = [
            _retro(1, set(), {rl.RETRO_FP}, title="first"),
            _retro(9, set(), set(), title="latest"),
            _retro(5, set(), {rl.RETRO_TP}, title="middle"),
        ]
        report = ar.compute_triage_report(past)
        assert [r.number for r in report.recent] == [9, 5, 1]
        assert report.recent[0].title == "latest"

    def test_capped_at_recent_count(self) -> None:
        past = [_retro(i, set(), set()) for i in range(50)]
        report = ar.compute_triage_report(past)
        assert len(report.recent) == ar._RECENT_RETRO_COUNT

    def test_status_priority_and_untriaged(self) -> None:
        past = [
            _retro(2, set(), {rl.RETRO_TP, rl.RETRO_FP}),  # tp wins (order)
            _retro(1, set(), set()),  # untriaged
        ]
        report = ar.compute_triage_report(past)
        by_num = {r.number: r for r in report.recent}
        assert by_num[2].status == rl.RETRO_TP
        assert by_num[1].status == "untriaged"

    def test_rendered_table_and_empty(self) -> None:
        out_empty = ar.render_triage_report_markdown(
            ar.compute_triage_report([])
        )
        assert "## Recent retros" in out_empty
        past = [_retro(7, set(), {rl.RETRO_FP}, state="open", title="t7")]
        out = ar.render_triage_report_markdown(ar.compute_triage_report(past))
        assert "## Recent retros" in out
        assert "| 7 | open | retro:fp | t7 |" in out


class TestPopulationTruncation:
    """Issue #2413: the report must never silently cap the population; it
    must state observed/total, declaring truncation explicitly when the
    live population exceeds what was fetched."""

    def test_truncated_population_declares_truncation_in_header(self) -> None:
        past = [_retro(i, set(), set()) for i in range(5)]
        report = ar.compute_triage_report(past, total_live=351)
        assert report.truncated
        out = ar.render_triage_report_markdown(report)
        assert "Retros observed: **5 of 351 (truncated)**" in out

    def test_full_population_is_not_truncated(self) -> None:
        past = [_retro(i, set(), set()) for i in range(5)]
        report = ar.compute_triage_report(past, total_live=5)
        assert not report.truncated
        out = ar.render_triage_report_markdown(report)
        assert "Retros observed: **5**" in out
        assert "truncated" not in out

    def test_default_total_live_matches_observed_and_is_not_truncated(
        self,
    ) -> None:
        """Callers that never pass total_live (the pre-#2413 shape) render
        exactly as before: no truncation notice."""
        past = [_retro(i, set(), set()) for i in range(3)]
        report = ar.compute_triage_report(past)
        assert not report.truncated
        assert report.population_total == report.total == 3


class TestFpTrend:
    """Retro-level FP-rate trend: all-time vs trailing window (#1386)."""

    def test_no_triaged_population(self) -> None:
        past = [_retro(i, set(), set()) for i in range(3)]
        report = ar.compute_triage_report(past)
        assert report.fp_triaged == 0
        out = ar.render_triage_report_markdown(report)
        assert "No triaged retros yet" in out

    def test_all_time_rate(self) -> None:
        # 3 fp + 1 tp triaged -> 0.75; one unlabelled is excluded.
        past = [
            _retro(1, set(), {rl.RETRO_FP}),
            _retro(2, set(), {rl.RETRO_FP}),
            _retro(3, set(), {rl.RETRO_FP}),
            _retro(4, set(), {rl.RETRO_TP}),
            _retro(5, set(), set()),
        ]
        report = ar.compute_triage_report(past)
        assert report.fp_triaged == 4
        assert abs(report.fp_rate_all - 0.75) < 1e-9

    def test_trend_direction_falling(self) -> None:
        # Old retros all fp; the most recent window dominated by tp -> falling.
        old = [_retro(i, set(), {rl.RETRO_FP}) for i in range(1, 6)]
        recent = [_retro(i, set(), {rl.RETRO_TP}) for i in range(100, 130)]
        report = ar.compute_triage_report(old + recent)
        out = ar.render_triage_report_markdown(report)
        assert report.fp_rate_recent < report.fp_rate_all
        assert "falling" in out

    def test_trend_rendered_with_counts(self) -> None:
        past = [_retro(1, set(), {rl.RETRO_FP}), _retro(2, set(), {rl.RETRO_TP})]
        out = ar.render_triage_report_markdown(ar.compute_triage_report(past))
        assert "## False-positive rate trend" in out
        assert "All-time:" in out
        assert f"Last {ar._FP_TREND_WINDOW} retros:" in out


class TestLoopHealthMetrics:
    """Loop-health panel metrics: triage rate, sentinel disposal, unlabelled
    ratio (issue #2434). All three derive from ``total`` + ``label_counts``."""

    def test_triage_rate_counts_any_retro_label_as_triaged(self) -> None:
        past = [
            _retro(1, set(), {rl.RETRO_TP}),
            _retro(2, set(), {rl.RETRO_FP}),
            _retro(3, set(), set()),
            _retro(4, set(), set()),
        ]
        report = ar.compute_triage_report(past)
        assert report.triaged == 2
        assert report.unlabelled == 2
        assert abs(report.triage_rate - 0.5) < 1e-9
        assert abs(report.unlabelled_ratio - 0.5) < 1e-9

    def test_sentinel_disposal_counts_retro_expired(self) -> None:
        # retro:expired is a retro label, so an expired retro is "triaged"
        # (labelled), not unlabelled.
        past = [
            _retro(1, set(), {rl.RETRO_EXPIRED}),
            _retro(2, set(), {rl.RETRO_EXPIRED}),
            _retro(3, set(), {rl.RETRO_TP}),
            _retro(4, set(), set()),
        ]
        report = ar.compute_triage_report(past)
        assert report.sentinel_disposed == 2
        assert abs(report.sentinel_disposal_rate - 0.5) < 1e-9
        assert report.unlabelled == 1
        assert report.triaged == 3

    def test_empty_population_metrics_are_zero(self) -> None:
        report = ar.compute_triage_report([])
        assert report.triaged == 0
        assert report.triage_rate == 0.0
        assert report.sentinel_disposed == 0
        assert report.sentinel_disposal_rate == 0.0
        assert report.unlabelled_ratio == 0.0
        assert report.unlabelled_anomaly is False


class TestUnlabelledAnomaly:
    """The unlabelled ratio is an Anomaly in its own right: a "no anomalies"
    headline must not be able to mean "nothing was ever labelled" (#2434)."""

    def test_all_unlabelled_large_population_is_anomaly(self) -> None:
        past = [
            _retro(i, {"multi_commit_pr"}, set())
            for i in range(ar._UNLABELLED_MIN_SAMPLE)
        ]
        report = ar.compute_triage_report(past)
        assert report.unlabelled_ratio == 1.0
        assert report.unlabelled_anomaly is True
        # No per-signal FP anomaly fires (nothing is retro:fp), so this is
        # exactly the degenerate the per-signal gate is blind to.
        assert report.anomalies == ()

    def test_below_sample_floor_is_not_anomaly(self) -> None:
        past = [
            _retro(i, set(), set())
            for i in range(ar._UNLABELLED_MIN_SAMPLE - 1)
        ]
        report = ar.compute_triage_report(past)
        assert report.unlabelled_ratio == 1.0
        assert report.unlabelled_anomaly is False

    def test_below_ratio_is_not_anomaly(self) -> None:
        # 5 retros, only 2 unlabelled -> ratio 0.4 < 0.5.
        past = [
            _retro(1, set(), {rl.RETRO_TP}),
            _retro(2, set(), {rl.RETRO_TP}),
            _retro(3, set(), {rl.RETRO_FP}),
            _retro(4, set(), set()),
            _retro(5, set(), set()),
        ]
        report = ar.compute_triage_report(past)
        assert abs(report.unlabelled_ratio - 0.4) < 1e-9
        assert report.unlabelled_anomaly is False

    def test_at_ratio_threshold_is_anomaly(self) -> None:
        # Exactly 0.5 unlabelled at the sample floor -> fires (>= boundary).
        labelled = [_retro(i, set(), {rl.RETRO_TP}) for i in range(1, 4)]
        unlabelled = [_retro(i, set(), set()) for i in range(100, 103)]
        report = ar.compute_triage_report(labelled + unlabelled)
        assert abs(report.unlabelled_ratio - 0.5) < 1e-9
        assert report.unlabelled_anomaly is True


class TestLoopHealthRender:
    """Rendering of the loop-health panel and its headline anomaly wiring."""

    def test_loop_health_section_present_with_metrics(self) -> None:
        past = [
            _retro(1, set(), {rl.RETRO_TP}),
            _retro(2, set(), {rl.RETRO_EXPIRED}),
            _retro(3, set(), set()),
        ]
        out = ar.render_triage_report_markdown(ar.compute_triage_report(past))
        assert "## Loop health" in out
        assert "Triage rate:" in out
        assert "Sentinel disposal:" in out

    def test_unlabelled_anomaly_listed_in_headline_not_none(self) -> None:
        past = [
            _retro(i, {"multi_commit_pr"}, set())
            for i in range(ar._UNLABELLED_MIN_SAMPLE)
        ]
        out = ar.render_triage_report_markdown(ar.compute_triage_report(past))
        # Headline Anomalies block carries the unlabelled-ratio bullet ...
        assert "unlabelled ratio" in out
        # ... and does NOT collapse to the "None" message.
        anomalies_block = out.split("## Loop health")[0]
        assert "None:" not in anomalies_block

    def test_healthy_population_headline_says_none(self) -> None:
        # Fully triaged, no FP anomaly, low unlabelled ratio -> "None".
        past = [_retro(i, set(), {rl.RETRO_TP}) for i in range(1, 6)]
        out = ar.render_triage_report_markdown(ar.compute_triage_report(past))
        anomalies_block = out.split("## Loop health")[0]
        assert "None:" in anomalies_block

    def test_empty_population_loop_health_placeholder(self) -> None:
        out = ar.render_triage_report_markdown(ar.compute_triage_report([]))
        assert "## Loop health" in out

    def test_sample_floor_miss_reports_the_sample_not_the_ratio(self) -> None:
        # All-unlabelled but below the sample floor: the anomaly does not
        # fire because of the sample gate, so the "None" reason must cite
        # the sample, not falsely claim a sub-threshold ratio (#2455 review).
        past = [
            _retro(i, set(), set())
            for i in range(ar._UNLABELLED_MIN_SAMPLE - 1)
        ]
        report = ar.compute_triage_report(past)
        assert report.unlabelled_ratio == 1.0
        assert report.unlabelled_anomaly is False
        anomalies_block = ar.render_triage_report_markdown(report).split(
            "## Loop health"
        )[0]
        assert "None:" in anomalies_block
        assert f"n={report.total}" in anomalies_block
        assert "ratio is below" not in anomalies_block
