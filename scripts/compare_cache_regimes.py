#!/usr/bin/env python3
"""Compare cache regimes by cost-per-PR and repairs-per-PR.

The cache-cost work in #1492 measures one session's cost structure
(``session_cost_structure.py``) and advises in-session when a regime is
under-amortised (``gate_cache_regime_advisor.py``). This script closes the loop
at the *portfolio* level: given samples of PRs produced under two or more
caching regimes, it reports each regime's mean cost per PR and mean repairs per
PR, and the delta of each candidate against the first (baseline) regime -- the
two numbers that decide whether a regime change paid off. Cost is the spend
lever; repairs/PR is the quality lever (a cheaper regime that doubles the repair
rate is not actually cheaper), so the comparison reports both side by side per
CLAUDE.md section 5 (quality must scale with volume, observably).

**Input is supplied, never scraped.** The script reads a JSON document -- from a
``--input`` file or stdin -- of the shape::

    {"regimes": [
       {"name": "baseline-5m", "prs": [{"cost": 2.71, "repairs": 1}, ...]},
       {"name": "candidate-1h", "prs": [{"cost": 3.14, "repairs": 0}, ...]}
    ]}

Each PR record carries the per-PR ``cost`` (USD, e.g. from
``session_resource_report.py`` / ccusage) and ``repairs`` (the count of repairs
between PR open and merge, e.g. from the post-merge retrospective). Keeping the
input a fixture rather than scraping ccusage checkpoints and retrospective
issues keeps the comparison deterministic and unit-testable, and keeps this
script's blast radius to arithmetic over numbers the caller already trusted
(CLAUDE.md sections 2 and 4); wiring the observed-value collection in is a
separate, later concern.

Malformed input fails loudly (exit 1 with a specific message) rather than
silently averaging garbage -- this is an analysis tool a human reads, not a
fail-open hook. The report is ASCII so it is safe to paste into a GitHub issue.

Refs #1492.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import NamedTuple


class RegimeSummary(NamedTuple):
    """Aggregate of one regime's PR samples."""

    name: str
    n: int
    cost_per_pr: float
    repairs_per_pr: float


class InputError(Exception):
    """Raised when the supplied regime document is malformed."""


def _as_number(value: object, where: str) -> float:
    """Return *value* as a float, raising :class:`InputError` if it is not one.

    ``bool`` is rejected so a JSON ``true`` is never averaged as ``1``.
    """
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise InputError(f"{where}: expected a number, got {value!r}")
    return float(value)


def parse_regimes(data: object) -> list[RegimeSummary]:
    """Return one :class:`RegimeSummary` per regime in the parsed *data*.

    Raises :class:`InputError` with a specific message on any shape violation:
    a missing ``regimes`` list, a regime without a name or PR list, an empty PR
    list (no per-PR mean is definable), or a non-numeric ``cost`` / ``repairs``.
    """
    if not isinstance(data, dict):
        raise InputError("top level must be a JSON object")
    regimes = data.get("regimes")
    if not isinstance(regimes, list) or not regimes:
        raise InputError("'regimes' must be a non-empty list")
    summaries: list[RegimeSummary] = []
    for idx, regime in enumerate(regimes):
        if not isinstance(regime, dict):
            raise InputError(f"regimes[{idx}] must be an object")
        name = regime.get("name")
        if not isinstance(name, str) or not name:
            raise InputError(f"regimes[{idx}] is missing a non-empty 'name'")
        prs = regime.get("prs")
        if not isinstance(prs, list) or not prs:
            raise InputError(f"regime {name!r}: 'prs' must be a non-empty list")
        total_cost = 0.0
        total_repairs = 0.0
        for j, pr in enumerate(prs):
            if not isinstance(pr, dict):
                raise InputError(f"regime {name!r} prs[{j}] must be an object")
            total_cost += _as_number(pr.get("cost"), f"regime {name!r} prs[{j}].cost")
            total_repairs += _as_number(
                pr.get("repairs"), f"regime {name!r} prs[{j}].repairs"
            )
        n = len(prs)
        summaries.append(
            RegimeSummary(
                name=name,
                n=n,
                cost_per_pr=total_cost / n,
                repairs_per_pr=total_repairs / n,
            )
        )
    return summaries


def _delta(value: float, baseline: float) -> str:
    """Return a signed delta string vs *baseline* (``+`` for an increase)."""
    diff = value - baseline
    return f"{diff:+.4f}"


def render_comparison(summaries: list[RegimeSummary]) -> str:
    """Return the ASCII comparison table.

    The first regime is the baseline; every later regime also shows the signed
    delta of its cost-per-PR and repairs-per-PR against that baseline, so a
    regime that trades lower cost for more repairs is visible by inspection.
    """
    baseline = summaries[0]
    lines = [
        "Cache regime comparison (baseline = first regime)",
        "",
        f"  {'regime':<18} {'n':>4} {'$/PR':>10} {'d$/PR':>10} "
        f"{'repairs/PR':>11} {'d-rep/PR':>10}",
    ]
    for s in summaries:
        if s is baseline:
            d_cost = d_rep = "--"
        else:
            d_cost = _delta(s.cost_per_pr, baseline.cost_per_pr)
            d_rep = _delta(s.repairs_per_pr, baseline.repairs_per_pr)
        lines.append(
            f"  {s.name:<18} {s.n:>4} {s.cost_per_pr:>10.4f} {d_cost:>10} "
            f"{s.repairs_per_pr:>11.4f} {d_rep:>10}"
        )
    return "\n".join(lines) + "\n"


def _load_input(path: Path | None) -> object:
    """Return the parsed JSON from *path*, or stdin when *path* is ``None``.

    Raises :class:`InputError` on an unreadable file or unparseable JSON.
    """
    try:
        raw = path.read_text(encoding="utf-8") if path is not None else sys.stdin.read()
    except OSError as exc:
        raise InputError(f"cannot read input: {exc}") from exc
    try:
        return json.loads(raw)
    except (TypeError, ValueError) as exc:
        raise InputError(f"input is not valid JSON: {exc}") from exc


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=None,
        help="Path to the regimes JSON document. Reads stdin when omitted.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        summaries = parse_regimes(_load_input(args.input))
    except InputError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    sys.stdout.write(render_comparison(summaries))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
