#!/usr/bin/env python3
"""Break a Claude Code session's cost down by cache regime, from the transcript.

``scripts/session_resource_report.py`` (#1413, #1435) reports a session's *total*
ccusage cost as a single number for the PR body. That number answers "how much
did this PR cost" but not "*where* did the cost go"; and for cache-heavy web
sessions the where is the actionable part. Cache-read is billed at 0.1x base
input but paid on every request; cache *writes* are billed at 1.25x (5-minute
TTL) or 2x (1-hour TTL), so a session that writes the same large prefix to the
1h cache without enough reads to amortise it is paying the 2x premium for no
benefit. None of that is visible in a single total.

This script makes the structure visible. It reads the session transcript
(the JSONL the Claude Code harness writes under
``~/.claude/projects/<slug>/``), de-duplicates the per-message ``usage``
objects by message id (streaming writes the same id more than once), and sums
the token counts into four cost categories:

* **cache-read**    ; ``cache_read_input_tokens`` (0.1x input).
* **cache-write 5m**; ``cache_creation.ephemeral_5m_input_tokens`` (1.25x).
* **cache-write 1h**; ``cache_creation.ephemeral_1h_input_tokens`` (2x).
* **uncached input**; ``input_tokens`` (full input rate).
* **output**        ; ``output_tokens`` (full output rate).

It then prices each category with per-1M-token rates and prints the cost
structure (USD and percent of total).

The default rates reproduce **ccusage's** billing model for ``claude-opus-4-8``,
verified to the cent against a real session ($2.7147 derived vs $2.7147 ccusage
across five independent categories): input $5.00, output $25.00, cache-read
$0.50, and cache-write at $6.25 (1.25x input) for **both** TTLs. That last point
is a measure-first finding, not a typo: Anthropic's published list price is 2x
input ($10.00) for the 1-hour TTL, but ccusage; the cost authority here
(measure-first); prices every ``cache_creation`` token at the flat 1.25x
regardless of TTL, so matching ccusage means defaulting the 1h write rate to
$6.25, not $10.00. Each rate is overridable on the CLI, so an operator who wants
to model the published list price passes ``--cache-write-1h-rate 10.0``; the 5m
and 1h token *counts* are always reported separately so the TTL split stays
observable even when both are priced the same.

When ``ccusage`` is on PATH and ``--session-id`` is given (or discoverable), the
``--ccusage-check`` flag runs it and reports the percent agreement between this
script's derived total and ccusage's ``totalCost``; a derived breakdown that
disagrees with ccusage by more than a few percent means the token-to-cost model
drifted from billing and should not be trusted.

Every input degrades independently: no transcript, an unreadable file, or a
malformed ``usage`` object yields a zeroed category rather than a crash, and the
script always prints a report and exits 0. It performs no network I/O of its own
(ccusage, when invoked, is a local pinned binary).

Refs #1492.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any, NamedTuple

_CCUSAGE_TIMEOUT_S = 20

# Per-1M-token USD rates for claude-opus-4-8, chosen to match ccusage's billed
# total (the cost authority) to the cent: input 1x, output 5x, cache-read 0.1x,
# and cache-write 1.25x for BOTH TTLs. Anthropic's list price is 2x ($10.00) for
# the 1-hour TTL, but ccusage prices cache_creation tokens at a flat 1.25x
# regardless of TTL, so the ccusage-matching default for cache_write_1h is $6.25,
# not $10.00 (override with --cache-write-1h-rate 10.0 to model the list price).
# Each is a CLI override so a model swap or pricing change is a flag, not an edit.
_DEFAULT_RATES = {
    "input": 5.00,
    "output": 25.00,
    "cache_read": 0.50,
    "cache_write_5m": 6.25,
    "cache_write_1h": 6.25,
}

_CATEGORY_LABELS = (
    ("cache_read", "cache-read"),
    ("cache_write_5m", "cache-write-5m"),
    ("cache_write_1h", "cache-write-1h"),
    ("input", "uncached-input"),
    ("output", "output"),
)


class Tokens(NamedTuple):
    """De-duplicated token counts for one session, split by cost category."""

    input: int
    output: int
    cache_read: int
    cache_write_5m: int
    cache_write_1h: int


class Costs(NamedTuple):
    """Per-category USD cost and the total, derived from :class:`Tokens`."""

    input: float
    output: float
    cache_read: float
    cache_write_5m: float
    cache_write_1h: float
    total: float


def _coerce_int(value: object) -> int:
    """Return *value* as a non-negative int, or 0 when it is not a number.

    ``bool`` is rejected so a JSON ``true`` never reads as ``1``. The transcript
    is untrusted input, so a string / null / negative where a token count is
    expected degrades that field to 0 rather than crashing the aggregation.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        return 0
    return max(0, int(value))


def _message_usage(entry: object) -> tuple[str, dict[str, Any]] | None:
    """Return ``(message_id, usage_dict)`` for an assistant entry, or ``None``.

    Only assistant entries carry billable ``usage``; user / tool-result entries
    are skipped. A missing id falls back to ``""`` so the entry still counts
    once (an empty id is a single de-dup bucket, which slightly under-counts
    rather than crashing; acceptable for a best-effort report).
    """
    if not isinstance(entry, dict):
        return None
    message = entry.get("message")
    if not isinstance(message, dict):
        return None
    usage = message.get("usage")
    if not isinstance(usage, dict):
        return None
    message_id = message.get("id")
    return (message_id if isinstance(message_id, str) else "", usage)


def aggregate_usages(entries: Iterable[object]) -> Tokens:
    """Sum the per-message ``usage`` objects in *entries* into :class:`Tokens`.

    De-duplicates by message id (last occurrence wins): streaming writes the
    same message id to the transcript more than once, and only the final write
    carries the complete usage, so summing every line double-counts. The 5m/1h
    cache-write split comes from ``usage.cache_creation``; when that nested
    object is absent the flat ``cache_creation_input_tokens`` is attributed to
    the 5m bucket (the API default TTL) so an older transcript shape still sums.
    """
    by_id: dict[str, dict[str, Any]] = {}
    for entry in entries:
        found = _message_usage(entry)
        if found is not None:
            by_id[found[0]] = found[1]

    input_t = output_t = read_t = write_5m = write_1h = 0
    for usage in by_id.values():
        input_t += _coerce_int(usage.get("input_tokens"))
        output_t += _coerce_int(usage.get("output_tokens"))
        read_t += _coerce_int(usage.get("cache_read_input_tokens"))
        creation = usage.get("cache_creation")
        if isinstance(creation, dict):
            write_5m += _coerce_int(creation.get("ephemeral_5m_input_tokens"))
            write_1h += _coerce_int(creation.get("ephemeral_1h_input_tokens"))
        else:
            # No TTL split available; attribute the flat count to 5m (default).
            write_5m += _coerce_int(usage.get("cache_creation_input_tokens"))
    return Tokens(
        input=input_t,
        output=output_t,
        cache_read=read_t,
        cache_write_5m=write_5m,
        cache_write_1h=write_1h,
    )


def compute_costs(tokens: Tokens, rates: dict[str, float]) -> Costs:
    """Price each token category at its per-1M rate and return :class:`Costs`."""
    input_c = tokens.input / 1e6 * rates["input"]
    output_c = tokens.output / 1e6 * rates["output"]
    read_c = tokens.cache_read / 1e6 * rates["cache_read"]
    write_5m_c = tokens.cache_write_5m / 1e6 * rates["cache_write_5m"]
    write_1h_c = tokens.cache_write_1h / 1e6 * rates["cache_write_1h"]
    return Costs(
        input=input_c,
        output=output_c,
        cache_read=read_c,
        cache_write_5m=write_5m_c,
        cache_write_1h=write_1h_c,
        total=input_c + output_c + read_c + write_5m_c + write_1h_c,
    )


def load_transcript(path: Path) -> list[object]:
    """Read a JSONL transcript into entries; ``[]`` on any read / parse failure.

    Mirrors the fail-soft loader in ``stop_new_session_handoff_prompt.py``:
    individual unparseable lines are skipped, and an unreadable file yields an
    empty list so the report degrades to zeros rather than crashing.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return []
    entries: list[object] = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return entries


def _slug_for(cwd: Path) -> str:
    """Return the Claude Code project-dir slug for *cwd*.

    The harness names the transcript directory after the absolute working
    directory with every ``/`` replaced by ``-`` (e.g. ``/home/user/claude-md``
    -> ``-home-user-claude-md``).
    """
    return str(cwd).replace("/", "-")


def discover_transcript(projects_dir: Path, cwd: Path) -> Path | None:
    """Return the most recently modified ``*.jsonl`` for *cwd*, or ``None``.

    Looks under ``<projects_dir>/<slug>/`` for the current project's
    transcripts and picks the newest by mtime. ``None`` when the directory is
    absent or holds no transcript; the caller then reports an empty session.
    """
    session_dir = projects_dir / _slug_for(cwd)
    try:
        candidates = [p for p in session_dir.glob("*.jsonl") if p.is_file()]
    except OSError:
        return None
    if not candidates:
        return None
    return max(candidates, key=lambda p: p.stat().st_mtime)


def _run_ccusage_total(session_id: str) -> float | None:
    """Return ccusage ``totalCost`` for *session_id*, or ``None`` on any failure.

    Reuses the grouped ``session --json`` shape (a ``{"session": [...]}`` array
    whose rows carry ``period`` = session id and ``totalCost``) that
    ``session_resource_report.py`` reads. Never raises: a missing binary,
    non-zero exit, timeout, or unparseable output yields ``None`` so the
    cross-check is simply omitted.
    """
    if not session_id:
        return None
    binary = shutil.which("ccusage")
    if binary is None:
        return None
    try:
        proc = subprocess.run(  # noqa: S603 -- fixed argv, absolute binary, no shell, no user input in flags
            [binary, "session", "--json"],
            capture_output=True,
            text=True,
            timeout=_CCUSAGE_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    try:
        data = json.loads(proc.stdout)
    except (TypeError, ValueError):
        return None
    rows = data.get("session") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return None
    for row in rows:
        if isinstance(row, dict) and row.get("period") == session_id:
            cost = row.get("totalCost")
            if isinstance(cost, int | float) and not isinstance(cost, bool):
                return float(cost)
    return None


def agreement_pct(derived: float, reference: float) -> float | None:
    """Return percent agreement of *derived* with *reference*, or ``None``.

    ``100 - |derived - reference| / reference * 100``. ``None`` when *reference*
    is non-positive (no meaningful base to compare against).
    """
    if reference <= 0:
        return None
    return 100.0 - abs(derived - reference) / reference * 100.0


def render_report(tokens: Tokens, costs: Costs, ccusage_total: float | None) -> str:
    """Return the ASCII cost-structure report.

    One line per category with tokens, USD, and percent of the derived total,
    then the total. When a ccusage total is supplied, a final line reports the
    percent agreement so a drift between the derived model and billing is
    visible by inspection. ASCII-only so it passes the GitHub-post non-ASCII
    gate if pasted into an issue or PR.
    """
    lines = ["Session cache cost structure", ""]
    total = costs.total
    for key, label in _CATEGORY_LABELS:
        tok = getattr(tokens, key)
        cost = getattr(costs, key)
        share = (cost / total * 100.0) if total > 0 else 0.0
        lines.append(f"  {label:<16} {tok:>12,} tok  ${cost:>9.4f}  {share:5.1f}%")
    lines.append("")
    lines.append(f"  {'TOTAL':<16} {'':>12}      ${total:>9.4f}  100.0%")
    if ccusage_total is not None:
        pct = agreement_pct(total, ccusage_total)
        pct_txt = f"{pct:.1f}%" if pct is not None else "unavailable"
        lines.append("")
        lines.append(
            f"  ccusage total ${ccusage_total:.4f}  (derived agrees {pct_txt})"
        )
    return "\n".join(lines) + "\n"


def _build_rates(args: argparse.Namespace) -> dict[str, float]:
    """Return the per-category rates, applying any CLI overrides over defaults."""
    rates = dict(_DEFAULT_RATES)
    for key in rates:
        override = getattr(args, f"{key}_rate", None)
        if override is not None:
            rates[key] = override
    return rates


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--transcript",
        type=Path,
        help="Path to a session JSONL transcript. Defaults to the newest "
        "transcript discovered for the current working directory.",
    )
    parser.add_argument(
        "--projects-dir",
        type=Path,
        default=Path.home() / ".claude" / "projects",
        help="Root of the Claude Code project transcript directories.",
    )
    parser.add_argument(
        "--session-id",
        default="",
        help="Session id for the optional ccusage cross-check.",
    )
    parser.add_argument(
        "--ccusage-check",
        action="store_true",
        help="Run ccusage and report percent agreement with the derived total.",
    )
    for key in _DEFAULT_RATES:
        parser.add_argument(
            f"--{key.replace('_', '-')}-rate",
            dest=f"{key}_rate",
            type=float,
            default=None,
            help=f"Override the per-1M-token USD rate for {key} "
            f"(default {_DEFAULT_RATES[key]}).",
        )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    transcript = args.transcript
    if transcript is None:
        transcript = discover_transcript(args.projects_dir, Path.cwd())
    entries = load_transcript(transcript) if transcript is not None else []
    tokens = aggregate_usages(entries)
    rates = _build_rates(args)
    costs = compute_costs(tokens, rates)
    ccusage_total = (
        _run_ccusage_total(args.session_id) if args.ccusage_check else None
    )
    sys.stdout.write(render_report(tokens, costs, ccusage_total))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
