#!/usr/bin/env python3
"""Read-only analyzer for ``verify-agents.yml`` CI timings.

Issue #474: the ``lint-scripts`` split landed in #425 (into
``lint-scripts-static`` and ``lint-scripts-pytest``) did not deliver
the expected wall-time improvement. Before making further structural
changes to ``verify-agents.yml`` (composite action for the 5-step uv
setup, ``pytest-xdist``, ``~/.cache/uv`` caching), we need observational
data to identify which job or step is actually on the critical path.
Per CLAUDE.md s2 (separate facts from speculation) the next round must
trace to measurement, not guesswork.

The script is intentionally offline. The operator fetches the inputs
with::

    gh api repos/tvna/claude-md/actions/workflows/verify-agents.yml/\\
        runs?per_page=100 > runs.json
    mkdir -p jobs
    for id in $(jq -r '.workflow_runs[].id' runs.json); do
        gh api repos/tvna/claude-md/actions/runs/"$id"/jobs \\
            > "jobs/$id.json"
    done
    python scripts/analyze_ci_timings.py --jobs jobs/ > report.md

The script itself does not call the GitHub API, mutates no state, runs
nowhere in CI, and writes outside stdout only when redirected. Single
file addition under ``scripts/`` plus its tests under ``tests/``.
Revert is a single ``git revert``.

Output is a markdown report (per-job and per-step aggregates) with
columns ``count | p50 | p95 | max | trend(5)``. The trend indicator is
a single ASCII character (``^`` faster-rising, ``v`` falling,
``=`` flat, ``?`` insufficient samples) so the report can be pasted
verbatim into a GitHub comment without tripping the non-ASCII gate.

Pass ``--cutoff YYYY-MM-DD`` to switch the report into compare mode:
samples are split at UTC midnight of the cutoff date into a baseline
window (pre-cutoff) and a post-change window (post-cutoff), and the
tables become ``pre count | pre p50 | post count | post p50 | delta p50``.
This is the mode used to close issue #545 acceptance criteria AC1
(baseline) and AC7 (post-change p50 strictly lower than baseline) for
performance-claiming PRs in one workflow dispatch.

Tested by ``tests/test_analyze_ci_timings.py``. Refs #474, #545.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections.abc import Hashable, Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path
from typing import TypeVar

# GitHub Actions API returns ISO-8601 with a trailing ``Z``. Parsing
# with this exact format avoids the dateutil dependency and keeps the
# script stdlib-only.
_GH_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"


def _parse_iso(ts: str) -> datetime:
    return datetime.strptime(ts, _GH_TS_FORMAT).replace(tzinfo=UTC)


def _duration_seconds(start: str | None, end: str | None) -> float | None:
    if not start or not end:
        return None
    try:
        delta = (_parse_iso(end) - _parse_iso(start)).total_seconds()
    except ValueError:
        return None
    if delta < 0:
        return None
    return delta


def _percentile(values: list[float], p: float) -> float:
    """Linear-interpolation percentile. ``p`` is a percentage 0..100.

    Mirrors ``numpy.percentile(values, p)`` for a single percentile but
    without the dependency. Returns 0.0 for an empty list -- the caller
    is responsible for not aggregating empty buckets, this is a guard.
    """
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    k = (len(ordered) - 1) * (p / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(ordered) - 1)
    frac = k - lo
    return ordered[lo] + (ordered[hi] - ordered[lo]) * frac


def _trend_arrow(samples_chronological: list[float]) -> str:
    """Single-char trend over the last up to 5 samples.

    Compares the median of the older half against the median of the
    newer half. A 10% band is treated as ``=`` (flat) to avoid noisy
    flips from one-off slow runs. ``?`` means fewer than two samples.
    """
    last = samples_chronological[-5:]
    if len(last) < 2:
        return "?"
    mid = len(last) // 2
    older = last[:mid] if mid else last[:1]
    newer = last[mid:]
    older_med = statistics.median(older)
    newer_med = statistics.median(newer)
    if older_med == 0:
        return "=" if newer_med == 0 else "^"
    ratio = newer_med / older_med
    if ratio > 1.10:
        return "^"
    if ratio < 0.90:
        return "v"
    return "="


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _expand_paths(paths: Iterable[Path]) -> Iterator[Path]:
    for p in paths:
        if p.is_dir():
            yield from sorted(p.glob("*.json"))
        else:
            yield p


def load_jobs(paths: Iterable[Path]) -> list[dict[str, object]]:
    """Load and flatten every ``jobs`` array from the supplied dumps.

    Each input file is expected to be the body of
    ``GET /repos/{owner}/{repo}/actions/runs/{run_id}/jobs`` -- an
    object with a ``jobs`` array. Files that do not match this shape
    contribute nothing (silent skip) so a stray ``runs.json`` dropped
    into the same directory does not crash the analyzer.
    """
    out: list[dict[str, object]] = []
    for path in _expand_paths(paths):
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        if not isinstance(data, dict):
            continue
        jobs = data.get("jobs")
        if not isinstance(jobs, list):
            continue
        for j in jobs:
            if isinstance(j, dict):
                out.append(j)
    return out


# ---------------------------------------------------------------------------
# Filtering
# ---------------------------------------------------------------------------


def filter_jobs(
    jobs: list[dict[str, object]],
    *,
    workflow_name: str | None = None,
    job_name: str | None = None,
    since: datetime | None = None,
) -> list[dict[str, object]]:
    out: list[dict[str, object]] = []
    for j in jobs:
        if workflow_name is not None and j.get("workflow_name") != workflow_name:
            continue
        if job_name is not None and j.get("name") != job_name:
            continue
        if since is not None:
            start = j.get("started_at")
            if not isinstance(start, str):
                continue
            try:
                started = _parse_iso(start)
            except ValueError:
                continue
            if started < since:
                continue
        out.append(j)
    return out


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


def aggregate_job_durations(
    jobs: list[dict[str, object]],
) -> dict[str, list[tuple[datetime, float]]]:
    """Map ``job-name -> [(started_at, duration_sec), ...]`` time-sorted."""
    bucket: dict[str, list[tuple[datetime, float]]] = {}
    for j in jobs:
        name = j.get("name")
        start_raw = j.get("started_at")
        end_raw = j.get("completed_at")
        if not isinstance(name, str) or not isinstance(start_raw, str):
            continue
        if not isinstance(end_raw, str):
            continue
        dur = _duration_seconds(start_raw, end_raw)
        if dur is None:
            continue
        try:
            started = _parse_iso(start_raw)
        except ValueError:
            continue
        bucket.setdefault(name, []).append((started, dur))
    for v in bucket.values():
        v.sort(key=lambda t: t[0])
    return bucket


def aggregate_step_durations(
    jobs: list[dict[str, object]],
) -> dict[tuple[str, str], list[tuple[datetime, float]]]:
    """Map ``(job-name, step-name) -> [(started_at, duration_sec), ...]``."""
    bucket: dict[tuple[str, str], list[tuple[datetime, float]]] = {}
    for j in jobs:
        job_name = j.get("name")
        if not isinstance(job_name, str):
            continue
        steps = j.get("steps")
        if not isinstance(steps, list):
            continue
        for s in steps:
            if not isinstance(s, dict):
                continue
            step_name = s.get("name")
            start_raw = s.get("started_at")
            end_raw = s.get("completed_at")
            if not isinstance(step_name, str) or not isinstance(start_raw, str):
                continue
            if not isinstance(end_raw, str):
                continue
            dur = _duration_seconds(start_raw, end_raw)
            if dur is None:
                continue
            try:
                started = _parse_iso(start_raw)
            except ValueError:
                continue
            bucket.setdefault((job_name, step_name), []).append((started, dur))
    for v in bucket.values():
        v.sort(key=lambda t: t[0])
    return bucket


# ---------------------------------------------------------------------------
# Partitioning (cutoff-windowed baseline vs post-change)
# ---------------------------------------------------------------------------


_K = TypeVar("_K", bound=Hashable)


def partition_aggregates_by_cutoff(
    aggregates: dict[_K, list[tuple[datetime, float]]],
    cutoff: datetime,
) -> tuple[dict[_K, list[float]], dict[_K, list[float]]]:
    """Split ``aggregates`` at ``cutoff`` into ``(pre, post)`` sample dicts.

    Samples whose ``started_at`` is strictly before ``cutoff`` go to
    ``pre``; samples at or after ``cutoff`` go to ``post``. Used by the
    compare-mode report (#545 AC1 / AC7) to put baseline and post-change
    p50 on the same row.
    """
    pre: dict[_K, list[float]] = {}
    post: dict[_K, list[float]] = {}
    for key, samples in aggregates.items():
        for ts, val in samples:
            if ts < cutoff:
                pre.setdefault(key, []).append(val)
            else:
                post.setdefault(key, []).append(val)
    return pre, post


def _delta_p50_marker(pre_samples: list[float], post_samples: list[float]) -> str:
    """Render the ``delta p50`` cell for a compare row.

    ``new`` -- no pre-cutoff sample; the row appeared after cutoff.
    ``gone`` -- no post-cutoff sample; the row existed only before.
    ``+/-X.Y%`` -- both windows present; signed percentage change.
    Output is ASCII-only (the report is pasted into a GitHub comment
    behind ``scripts/preflight_non_ascii.py``).
    """
    if not pre_samples and not post_samples:
        return "n/a"
    if not pre_samples:
        return "new"
    if not post_samples:
        return "gone"
    pre_p50 = _percentile(pre_samples, 50)
    post_p50 = _percentile(post_samples, 50)
    if pre_p50 == 0:
        return "+inf" if post_p50 > 0 else "0.0%"
    pct = (post_p50 - pre_p50) / pre_p50 * 100.0
    sign = "+" if pct >= 0 else ""
    return f"{sign}{pct:.1f}%"


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


def _fmt_seconds(value: float) -> str:
    return f"{value:.1f}"


def _render_job_table(
    aggregates: dict[str, list[tuple[datetime, float]]],
) -> str:
    rows: list[str] = []
    rows.append("| job | count | p50 | p95 | max | trend(5) |")
    rows.append("| --- | ---: | ---: | ---: | ---: | :---: |")
    for name in sorted(aggregates):
        samples = [v for _, v in aggregates[name]]
        rows.append(
            f"| {name} | {len(samples)} | "
            f"{_fmt_seconds(_percentile(samples, 50))} | "
            f"{_fmt_seconds(_percentile(samples, 95))} | "
            f"{_fmt_seconds(max(samples))} | "
            f"{_trend_arrow(samples)} |"
        )
    return "\n".join(rows)


def _render_step_table(
    aggregates: dict[tuple[str, str], list[tuple[datetime, float]]],
) -> str:
    rows: list[str] = []
    rows.append("| job | step | count | p50 | p95 | max | trend(5) |")
    rows.append("| --- | --- | ---: | ---: | ---: | ---: | :---: |")
    for key in sorted(aggregates):
        job_name, step_name = key
        samples = [v for _, v in aggregates[key]]
        rows.append(
            f"| {job_name} | {step_name} | {len(samples)} | "
            f"{_fmt_seconds(_percentile(samples, 50))} | "
            f"{_fmt_seconds(_percentile(samples, 95))} | "
            f"{_fmt_seconds(max(samples))} | "
            f"{_trend_arrow(samples)} |"
        )
    return "\n".join(rows)


def _render_compare_job_table(
    pre: dict[str, list[float]],
    post: dict[str, list[float]],
) -> str:
    rows: list[str] = []
    rows.append(
        "| job | pre count | pre p50 | post count | post p50 | delta p50 |"
    )
    rows.append("| --- | ---: | ---: | ---: | ---: | ---: |")
    for name in sorted(set(pre) | set(post)):
        pre_samples = pre.get(name, [])
        post_samples = post.get(name, [])
        rows.append(
            f"| {name} | {len(pre_samples)} | "
            f"{_fmt_seconds(_percentile(pre_samples, 50))} | "
            f"{len(post_samples)} | "
            f"{_fmt_seconds(_percentile(post_samples, 50))} | "
            f"{_delta_p50_marker(pre_samples, post_samples)} |"
        )
    return "\n".join(rows)


def _render_compare_step_table(
    pre: dict[tuple[str, str], list[float]],
    post: dict[tuple[str, str], list[float]],
) -> str:
    rows: list[str] = []
    rows.append(
        "| job | step | pre count | pre p50 | post count | post p50 | delta p50 |"
    )
    rows.append("| --- | --- | ---: | ---: | ---: | ---: | ---: |")
    for key in sorted(set(pre) | set(post)):
        job_name, step_name = key
        pre_samples = pre.get(key, [])
        post_samples = post.get(key, [])
        rows.append(
            f"| {job_name} | {step_name} | {len(pre_samples)} | "
            f"{_fmt_seconds(_percentile(pre_samples, 50))} | "
            f"{len(post_samples)} | "
            f"{_fmt_seconds(_percentile(post_samples, 50))} | "
            f"{_delta_p50_marker(pre_samples, post_samples)} |"
        )
    return "\n".join(rows)


def budget_breaches(
    job_agg: dict[str, list[tuple[datetime, float]]], budget_seconds: float
) -> list[tuple[str, float]]:
    """Return ``(job_name, p50)`` for jobs whose median exceeds the budget.

    Sorted slowest-first. p50 (median) is used rather than max so a single
    noisy runner outlier does not trip the soft budget. Takes the same
    ``aggregate_job_durations`` shape (``[(started_at, duration), ...]``) as
    the report tables. Refs #1156.
    """
    out: list[tuple[str, float]] = []
    for name, samples in job_agg.items():
        durations = [v for _, v in samples]
        if not durations:
            continue
        p50 = _percentile(durations, 50)
        if p50 > budget_seconds:
            out.append((name, p50))
    return sorted(out, key=lambda item: item[1], reverse=True)


def _render_budget_section(
    job_agg: dict[str, list[tuple[datetime, float]]], budget_seconds: float
) -> str:
    parts: list[str] = []
    parts.append(f"## Budget ({_fmt_seconds(budget_seconds)} per job, p50)")
    parts.append("")
    breaches = budget_breaches(job_agg, budget_seconds)
    if not breaches:
        parts.append(f"OK: no job p50 exceeds {_fmt_seconds(budget_seconds)}.")
        return "\n".join(parts)
    parts.append(
        f"BUDGET BREACH: {len(breaches)} job(s) over the soft budget "
        f"(observability, not a hard gate -- #1156):"
    )
    parts.append("")
    parts.append("| job | p50 | budget |")
    parts.append("| --- | ---: | ---: |")
    for name, p50 in breaches:
        parts.append(
            f"| {name} | {_fmt_seconds(p50)} | {_fmt_seconds(budget_seconds)} |"
        )
    return "\n".join(parts)


def render_report(
    jobs: list[dict[str, object]],
    *,
    title: str,
    cutoff: datetime | None = None,
    budget_seconds: float | None = None,
) -> str:
    if cutoff is None:
        return _render_single_window_report(
            jobs, title=title, budget_seconds=budget_seconds
        )
    return _render_compare_report(jobs, title=title, cutoff=cutoff)


def _render_single_window_report(
    jobs: list[dict[str, object]],
    *,
    title: str,
    budget_seconds: float | None = None,
) -> str:
    job_agg = aggregate_job_durations(jobs)
    step_agg = aggregate_step_durations(jobs)
    parts: list[str] = []
    parts.append(f"# {title}")
    parts.append("")
    parts.append(f"Aggregated over {len(jobs)} job execution(s).")
    parts.append("")
    parts.append("## Per-job durations (seconds)")
    parts.append("")
    if job_agg:
        parts.append(_render_job_table(job_agg))
    else:
        parts.append("_no job samples_")
    parts.append("")
    parts.append("## Per-step durations (seconds)")
    parts.append("")
    if step_agg:
        parts.append(_render_step_table(step_agg))
    else:
        parts.append("_no step samples_")
    parts.append("")
    if budget_seconds is not None:
        parts.append(_render_budget_section(job_agg, budget_seconds))
        parts.append("")
    parts.append(
        "Trend legend: `^` = newer half >10% slower, `v` = newer half "
        ">10% faster, `=` = within +/-10%, `?` = fewer than 2 samples."
    )
    return "\n".join(parts)


def _render_compare_report(
    jobs: list[dict[str, object]],
    *,
    title: str,
    cutoff: datetime,
) -> str:
    job_agg = aggregate_job_durations(jobs)
    step_agg = aggregate_step_durations(jobs)
    pre_jobs, post_jobs = partition_aggregates_by_cutoff(job_agg, cutoff)
    pre_steps, post_steps = partition_aggregates_by_cutoff(step_agg, cutoff)
    pre_total = sum(len(s) for s in pre_jobs.values())
    post_total = sum(len(s) for s in post_jobs.values())
    cutoff_iso = cutoff.strftime("%Y-%m-%dT%H:%M:%SZ")
    parts: list[str] = []
    parts.append(f"# {title}")
    parts.append("")
    parts.append(
        f"Cutoff: {cutoff_iso}. "
        f"Pre-cutoff job executions: {pre_total}. "
        f"Post-cutoff job executions: {post_total}."
    )
    parts.append("")
    parts.append("## Per-job durations (seconds, pre vs post cutoff)")
    parts.append("")
    if pre_jobs or post_jobs:
        parts.append(_render_compare_job_table(pre_jobs, post_jobs))
    else:
        parts.append("_no job samples_")
    parts.append("")
    parts.append("## Per-step durations (seconds, pre vs post cutoff)")
    parts.append("")
    if pre_steps or post_steps:
        parts.append(_render_compare_step_table(pre_steps, post_steps))
    else:
        parts.append("_no step samples_")
    parts.append("")
    parts.append(
        "Delta legend: `+X.Y%` = post p50 slower than pre, `-X.Y%` = post "
        "faster, `new` = no pre-cutoff sample, `gone` = no post-cutoff "
        "sample, `+inf` = pre p50 was zero with post-cutoff samples present."
    )
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_since(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--since expects YYYY-MM-DD, got {value!r}"
        ) from exc


def _parse_cutoff(value: str) -> datetime:
    try:
        return datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=UTC)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"--cutoff expects YYYY-MM-DD (UTC midnight), got {value!r}"
        ) from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--jobs",
        type=Path,
        nargs="+",
        required=True,
        help=(
            "One or more paths to GitHub 'runs/{id}/jobs' JSON dumps. "
            "Directories are expanded by globbing '*.json'."
        ),
    )
    parser.add_argument(
        "--workflow",
        default=None,
        help="Filter to jobs whose 'workflow_name' equals this value.",
    )
    parser.add_argument(
        "--job",
        default=None,
        help="Filter to jobs whose 'name' equals this value.",
    )
    parser.add_argument(
        "--since",
        type=_parse_since,
        default=None,
        help="Drop jobs whose 'started_at' is before this UTC date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--title",
        default="CI timings report",
        help="Markdown report title.",
    )
    parser.add_argument(
        "--cutoff",
        type=_parse_cutoff,
        default=None,
        help=(
            "Optional UTC date (YYYY-MM-DD). When supplied, the report "
            "splits aggregates into pre-cutoff (baseline) and post-cutoff "
            "(post-change) columns with a delta p50 marker. Use this to "
            "satisfy issue #545 AC1/AC7 (baseline vs post-change comparison) "
            "for performance-claiming PRs."
        ),
    )
    parser.add_argument(
        "--budget-seconds",
        type=float,
        default=None,
        help=(
            "Optional soft per-job wall-time budget. When supplied, the "
            "single-window report appends a Budget section listing jobs whose "
            "median (p50) exceeds it (observability, not a hard gate; #1156)."
        ),
    )
    args = parser.parse_args(argv)

    jobs = load_jobs(args.jobs)
    jobs = filter_jobs(
        jobs,
        workflow_name=args.workflow,
        job_name=args.job,
        since=args.since,
    )
    report = render_report(
        jobs,
        title=args.title,
        cutoff=args.cutoff,
        budget_seconds=args.budget_seconds,
    )
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
