#!/usr/bin/env python3
"""Repair-free merge rate ledger: pure parse/render layer for auto_retro.py.

Persists one row per merge that ``auto_retro.run()`` evaluates (PR number,
merged-at timestamp, whether a repair signal fired) and renders a weekly
repair-free-rate aggregation from that history. This is the primary
convergence signal for CLAUDE.md section 3 ("measurably better each
cycle"): repair-free merge rate = the weekly share of evaluated merges
where no repair signal fired (owner decision 2026-07-10).

The rendered file is a non-deterministic GitHub-state snapshot, refreshed
via a bot PR after each merge (the same treatment as the sibling
``auto-retro-triage-report.md``), rather than the deterministic
``docs/generated/`` regeneration. auto_retro.py owns the GitHub IO
(fetching the current file, calling ``pr_upsert.upsert_single_file_pr``);
every function in this module is pure. Refs #2415.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

LEDGER_TITLE = "# Repair-free merge rate ledger"

# Bounds the per-merge table so a rerun of the same merge event (or a
# backfill from the "existing retro" / "fix() append" branches of run())
# can locate and skip a row that is already recorded. Same open/close
# HTML-comment convention as _AUTO_FILLED_OPEN/_CLOSE in _auto_retro_parse.py.
_ROWS_OPEN = "<!-- auto-retro-ledger:rows -->"
_ROWS_CLOSE = "<!-- /auto-retro-ledger:rows -->"

_ROW_RE = re.compile(
    r"^\|\s*#(\d+)\s*\|\s*(\S+)\s*\|\s*(yes|no)\s*\|\s*$",
    re.MULTILINE,
)

# Weekly aggregation table display window (issue #2415 acceptance
# criterion: "if the rendering windows the history, state the window
# explicitly"). Only the *rendered weekly table* is windowed; the
# per-merge table below it is the full ledger and is never truncated: it
# is the durable time series the weekly rate is recomputed from on every
# run.
WEEKLY_DISPLAY_WINDOW = 12

# Moving-average width for the stop-rule signal (CLAUDE.md section 5:
# "When the measured proportion of quality to volume degrades, stop and
# re-plan"). compute_weekly_stats fills any merge-free calendar week with an
# explicit zero-merge entry so this genuinely spans MOVING_AVERAGE_WINDOW
# calendar weeks, not just the last N weeks that happened to have a merge.
MOVING_AVERAGE_WINDOW = 4


@dataclass(frozen=True)
class LedgerRow:
    """One merge's repair-free-merge-ledger entry."""

    pr_number: int
    merged_at: str
    repair_free: bool


@dataclass(frozen=True)
class WeeklyStat:
    iso_week: str
    merges: int
    repair_free_count: int
    rate: float | None  # percentage, 0.0-100.0; None for a merge-free week
    moving_avg: float | None  # percentage; None until MOVING_AVERAGE_WINDOW calendar weeks observed


def render_row(row: LedgerRow) -> str:
    flag = "yes" if row.repair_free else "no"
    return f"| #{row.pr_number} | {row.merged_at} | {flag} |"


def parse_rows(body: str) -> list[LedgerRow]:
    """Parse every per-merge row inside the rows markers.

    Returns ``[]`` when the markers are absent (no ledger file yet, i.e.
    the first-ever recorded merge) or contain no rows.
    """
    open_idx = body.find(_ROWS_OPEN)
    close_idx = body.find(_ROWS_CLOSE)
    if open_idx == -1 or close_idx == -1 or close_idx < open_idx:
        return []
    block = body[open_idx:close_idx]
    rows: list[LedgerRow] = []
    for match in _ROW_RE.finditer(block):
        number_s, merged_at, flag = match.groups()
        rows.append(
            LedgerRow(
                pr_number=int(number_s),
                merged_at=merged_at,
                repair_free=(flag == "yes"),
            )
        )
    return rows


def insert_row(
    rows: list[LedgerRow], new_row: LedgerRow
) -> tuple[list[LedgerRow], bool]:
    """Append *new_row* unless *rows* already carries its ``pr_number``.

    Idempotency anchor (issue #2415 acceptance criterion: exactly one row
    per merge, safe under a rerun / retry of the same merge event, and
    safe when multiple ``run()`` branches for the same PR each attempt to
    record a row).
    """
    if any(row.pr_number == new_row.pr_number for row in rows):
        return rows, False
    return [*rows, new_row], True


def _iso_week(merged_at: str) -> str:
    """Return the ``GGGG-Www`` ISO week label for an ISO 8601 timestamp.

    Mirrors the ``iso[:20]`` / ``%Y-%m-%dT%H:%M:%SZ`` parse already used by
    ``auto_retro._hours_between`` so both readings of a GitHub
    ``merged_at`` timestamp agree.
    """
    dt = datetime.strptime(merged_at[:20], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    year, week, _weekday = dt.isocalendar()
    return f"{year:04d}-W{week:02d}"


def _iso_week_monday(iso_week: str) -> datetime:
    """Return the Monday (00:00 UTC) of a ``GGGG-Www`` ISO week label."""
    return datetime.strptime(f"{iso_week}-1", "%G-W%V-%u").replace(tzinfo=UTC)


def _next_iso_week(iso_week: str) -> str:
    """Return the ISO week label immediately following *iso_week*."""
    year, week, _weekday = (_iso_week_monday(iso_week) + timedelta(weeks=1)).isocalendar()
    return f"{year:04d}-W{week:02d}"


def compute_weekly_stats(rows: list[LedgerRow]) -> list[WeeklyStat]:
    """Group *rows* by ISO week and compute the repair-free rate + moving avg.

    Fills every merge-free calendar week between the first and last
    observed week with an explicit zero-merge :class:`WeeklyStat` (``rate``
    ``None``), so a merge-cadence gap cannot silently compress the "4-week
    moving average" into an average of 4 *non-adjacent* weeks: it always
    spans exactly :data:`MOVING_AVERAGE_WINDOW` consecutive calendar weeks,
    skipping merge-free weeks (``rate is None``) when forming the average.
    Weeks are returned oldest-first so the moving average reads
    left-to-right over the full (unwindowed) history; :func:`render_weekly_table`
    windows only the *display*, so the moving average stays exact.
    """
    by_week: dict[str, list[LedgerRow]] = {}
    for row in rows:
        by_week.setdefault(_iso_week(row.merged_at), []).append(row)
    if not by_week:
        return []

    observed_weeks = sorted(by_week)
    full_weeks = [observed_weeks[0]]
    while full_weeks[-1] != observed_weeks[-1]:
        full_weeks.append(_next_iso_week(full_weeks[-1]))

    stats: list[WeeklyStat] = []
    window_rates: list[float | None] = []
    for week in full_weeks:
        week_rows = by_week.get(week, [])
        merges = len(week_rows)
        if merges:
            repair_free_count = sum(1 for r in week_rows if r.repair_free)
            rate: float | None = (repair_free_count / merges) * 100.0
        else:
            repair_free_count = 0
            rate = None
        window_rates.append(rate)
        trailing = [r for r in window_rates[-MOVING_AVERAGE_WINDOW:] if r is not None]
        moving_avg = (
            sum(trailing) / len(trailing)
            if len(window_rates) >= MOVING_AVERAGE_WINDOW and trailing
            else None
        )
        stats.append(WeeklyStat(week, merges, repair_free_count, rate, moving_avg))
    return stats


def render_weekly_table(
    stats: list[WeeklyStat], *, window: int = WEEKLY_DISPLAY_WINDOW
) -> str:
    """Render the weekly rate table, windowed to the most recent *window* weeks."""
    total = len(stats)
    windowed = stats[-window:] if total > window else stats
    lines: list[str] = []
    if total > window:
        lines.append(
            f"Showing the most recent {len(windowed)} of {total} ISO weeks "
            f"(window={window}); the per-merge history below is never "
            "windowed.\n"
        )
    lines.append("| ISO week | Merges | Repair-free | Rate | 4-week moving avg |")
    lines.append("|---|---|---|---|---|")
    for stat in windowed:
        rate = f"{stat.rate:.1f}%" if stat.rate is not None else "n/a (no merges)"
        avg = f"{stat.moving_avg:.1f}%" if stat.moving_avg is not None else "n/a"
        lines.append(
            f"| {stat.iso_week} | {stat.merges} | {stat.repair_free_count} | "
            f"{rate} | {avg} |"
        )
    return "\n".join(lines) + "\n"


_STOP_RULE = (
    "## Stop rule\n"
    "\n"
    "If the 4-week moving average declines for two consecutive observed "
    "weeks, stop scaling and re-plan per CLAUDE.md section 5 (\"When the "
    "measured proportion of quality to volume degrades, stop and "
    "re-plan\") instead of adding more scale on top of a regressing "
    "repair-free rate. The moving average spans 4 consecutive calendar "
    "weeks (a merge-free week counts toward the span with no rate of its "
    "own), not merely the last 4 weeks that happened to have a merge.\n"
)


def render_ledger_markdown(rows: list[LedgerRow]) -> str:
    """Render the full ledger document: header, stop rule, weekly table,
    then the full (unwindowed) per-merge history."""
    stats = compute_weekly_stats(rows)
    rows_block = "\n".join(render_row(r) for r in rows)
    return (
        f"{LEDGER_TITLE}\n"
        "\n"
        "Primary convergence signal for CLAUDE.md section 3 (\"measurably "
        "better each cycle\"): repair-free merge rate = the weekly share "
        "of merges auto_retro.py evaluates where no repair signal fired. "
        "Refreshed by a bot PR after every merge (a non-deterministic "
        "GitHub-state snapshot, same treatment as the sibling triage "
        "report). Refs #2415.\n"
        "\n"
        f"{_STOP_RULE}"
        "\n"
        "## Weekly repair-free rate\n"
        "\n"
        f"{render_weekly_table(stats)}"
        "\n"
        "## Per-merge history\n"
        "\n"
        f"{_ROWS_OPEN}\n"
        "| PR | Merged at (UTC) | Repair-free |\n"
        "|---|---|---|\n"
        f"{rows_block}\n"
        f"{_ROWS_CLOSE}\n"
    )


def upsert_ledger_markdown(
    existing: bytes | None, new_row: LedgerRow
) -> tuple[bytes, bool]:
    """Return ``(new_content_bytes, changed)`` after idempotently inserting *new_row*.

    ``existing`` is the current committed file content, or ``None`` before
    the ledger file exists (the very first recorded merge). ``changed`` is
    False when *new_row*'s ``pr_number`` is already recorded, in which case
    *existing* (or ``b""`` if it was ``None``) is returned unchanged and the
    caller skips the PR upsert entirely (issue #2415 idempotency criterion).
    """
    body = existing.decode("utf-8") if existing is not None else ""
    rows = parse_rows(body)
    new_rows, changed = insert_row(rows, new_row)
    if not changed:
        return existing if existing is not None else b"", False
    return render_ledger_markdown(new_rows).encode("utf-8"), True
