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

Tested by ``tests/test_analyze_ci_timings.py``. Refs #474.
"""

from __future__ import annotations

import argparse
import json
import statistics
from collections.abc import Iterable, Iterator
from datetime import UTC, datetime
from pathlib import Path

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


def render_report(jobs: list[dict[str, object]], *, title: str) -> str:
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
    parts.append(
        "Trend legend: `^` = newer half >10% slower, `v` = newer half "
        ">10% faster, `=` = within +/-10%, `?` = fewer than 2 samples."
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
    args = parser.parse_args(argv)

    jobs = load_jobs(args.jobs)
    jobs = filter_jobs(
        jobs,
        workflow_name=args.workflow,
        job_name=args.job,
        since=args.since,
    )
    report = render_report(jobs, title=args.title)
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
