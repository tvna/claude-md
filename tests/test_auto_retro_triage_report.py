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
