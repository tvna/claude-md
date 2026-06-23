#!/usr/bin/env python3
"""Compare cache regimes by cost-per-PR and repairs-per-PR.

The cache-cost work in #1492 measures one session's cost structure
(``session_cost_structure.py``) and advises in-session when a regime is
under-amortised (``gate_cache_regime_advisor.py``). This script closes the loop
at the *portfolio* level: given samples of PRs produced under two or more
caching regimes, it reports each regime's mean cost per PR and mean repairs per
PR, and the delta of each candidate against the first (baseline) regime; the
two numbers that decide whether a regime change paid off. Cost is the spend
lever; repairs/PR is the quality lever (a cheaper regime that doubles the repair
rate is not actually cheaper), so the comparison reports both side by side per
CLAUDE.md section 5 (quality must scale with volume, observably).

**Input is supplied, never scraped.** The script reads a JSON document; from a
``--input`` file or stdin; of the shape::

    {"regimes": [
       {"name": "baseline-5m", "prs": [{"cost": 2.71, "repairs": 1}, ...]},
       {"name": "candidate-1h", "prs": [{"cost": 3.14, "repairs": 0}, ...]}
    ]}

Each PR record yields a per-PR ``cost`` (USD) and ``repairs`` (the count of
repairs between PR open and merge). The two fields resolve independently, each
from one of two sources, so a record may mix them:

* a *fixture* number supplied inline; ``"cost": 3.14`` / ``"repairs": 0``; or
* an *auto-collected* number read from the observed record the harness already
  produces; ``"pr_body"`` (the cost is parsed from its ``## Resource
  Consumption`` ``- Cost (USD): $X`` line, which ``session_resource_report.py``
  renders from the per-PR ccusage checkpoint delta) and ``"retro_body"`` (the
  repairs are counted from the Repair history table that ``auto_retro.py``
  pre-fills into the retrospective issue).

Auto-collection still does no network fetch: the caller supplies the body text
it already pulled through the approved GitHub read path, so the comparison stays
deterministic, unit-testable, and bounded to arithmetic plus parsing over data
the caller already trusted (CLAUDE.md sections 2 and 4).

Malformed input fails loudly (exit 1 with a specific message) rather than
silently averaging garbage; this is an analysis tool a human reads, not a
fail-open hook. The report is ASCII so it is safe to paste into a GitHub issue.

Refs #1492.
"""

from __future__ import annotations

import argparse
import json
import re
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


# ---------------------------------------------------------------------------
# Auto-collection from observed PR / retro bodies.
#
# The fixture path takes inline ``cost`` / ``repairs`` numbers. The
# auto-collection path resolves those same two numbers from the durable,
# observed records the harness already produces, so a portfolio comparison can
# run on real samples without hand-transcribing them; yet the script still
# performs no network fetch: the caller supplies the body text it already
# pulled through the approved GitHub read path (CLAUDE.md sections 2 and 4).
# ---------------------------------------------------------------------------

# session_resource_report.render_section emits a ``## Resource Consumption``
# section whose cost line is exactly ``- Cost (USD): $<float>`` (4 decimals),
# or ``- Cost (USD): unavailable (no session data)`` when ccusage produced no
# figure. Slice to the section first so a ``$`` elsewhere in the body cannot be
# misread as the cost.
_RESOURCE_HEADING_RE = re.compile(r"(?im)^[ \t]*##[ \t]+Resource[ \t]+Consumption\b")
_NEXT_H2_RE = re.compile(r"(?m)^[ \t]*##[ \t]+")
_COST_LINE_RE = re.compile(r"(?im)^[ \t]*-[ \t]*Cost \(USD\):[ \t]*\$([0-9]+(?:\.[0-9]+)?)\b")
# Matches session_resource_report._UNAVAILABLE; treated as a loud failure
# rather than a $0 sample so an absent ccusage figure is never averaged in.
_COST_UNAVAILABLE = "unavailable (no session data)"

# auto_retro._build_repair_history_table renders:
#   | # | Repair | Cause | Next action |
#   |---|--------|-------|-------------|
#   | 1 | CI fail: ... | ... | ... |
# A genuine repair is a numbered data row that is NOT an exempt policy
# artifact. auto_retro marks rebase/squash/revert/multi-commit/verification
# rows with ``[policy-artifact]`` and exempts them from the repair taxonomy;
# ``Iteration commit`` rows carry the marker too but stay actionable
# (auto_retro._has_only_exempt_policy_artifact_rows), so they still count. The
# sentinel row (``no automated repair signals detected``) has a ``--`` index
# cell and contributes zero. These literals are the rendered contract of
# auto_retro.py; the paired test pins them to that producer so a drift there
# breaks this parser's test rather than silently miscounting.
_REPAIR_HEADER_RE = re.compile(r"^\|\s*#\s*\|\s*Repair\s*\|")
_POLICY_ARTIFACT_MARKER = "[policy-artifact]"
_ITERATION_COMMIT_REPAIR = "Iteration commit"


def _resource_section(body: str) -> str | None:
    """Return the ``## Resource Consumption`` section text of *body*, or ``None``.

    The section runs from its heading to the next ``## `` heading (or end of
    body). ``None`` when the body has no such heading.
    """
    match = _RESOURCE_HEADING_RE.search(body)
    if match is None:
        return None
    rest = body[match.end() :]
    nxt = _NEXT_H2_RE.search(rest)
    return rest if nxt is None else rest[: nxt.start()]


def parse_pr_cost(pr_body: str, where: str) -> float:
    """Return the per-PR USD cost parsed from *pr_body*'s Resource Consumption.

    Reads the ``- Cost (USD): $<float>`` line inside the ``## Resource
    Consumption`` section that ``scripts/session_resource_report.py`` renders
    into every PR body from the per-PR ccusage checkpoint delta. Raises
    :class:`InputError`; loudly, never a silent default; when the section is
    absent, when the cost is the ``unavailable (no session data)`` marker
    (ccusage produced no figure for that PR), or when no cost line is found.
    """
    section = _resource_section(pr_body)
    if section is None:
        raise InputError(f"{where}: no '## Resource Consumption' section in pr_body")
    match = _COST_LINE_RE.search(section)
    if match is None:
        if _COST_UNAVAILABLE in section:
            raise InputError(
                f"{where}: Resource Consumption cost is "
                f"'{_COST_UNAVAILABLE}' (no ccusage figure for this PR)"
            )
        raise InputError(f"{where}: no '- Cost (USD): $...' line in Resource Consumption")
    return float(match.group(1))


def _first_table_cell(row: str) -> str | None:
    """Return the first cell of a stripped markdown table *row*, or ``None``.

    *row* starts with ``|``; the surrounding pipes are dropped before the first
    ``|``-split cell is returned, so ``| 1 | ... |`` yields ``"1"``.
    """
    inner = row.strip().strip("|")
    if not inner:
        return None
    return inner.split("|", 1)[0].strip()


def parse_retro_repairs(retro_body: str, where: str) -> int:
    """Return the genuine-repair count from *retro_body*'s Repair history table.

    Counts numbered rows in the ``| # | Repair | Cause | Next action |`` table
    that ``scripts/auto_retro.py`` pre-fills into a retrospective issue,
    excluding the exempt policy-artifact rows (rebase/squash/revert/
    multi-commit/verification noise forced by the merge policy) but keeping
    ``Iteration commit`` rows, mirroring auto_retro's own actionable-repair
    predicate. The sentinel "no automated repair signals detected" row has a
    ``--`` index and contributes zero. Raises :class:`InputError` when no
    Repair history table is present; a retro body that lost its table is
    malformed input, not a zero-repair PR.
    """
    lines = retro_body.splitlines()
    header_idx = next(
        (i for i, line in enumerate(lines) if _REPAIR_HEADER_RE.match(line.strip())),
        None,
    )
    if header_idx is None:
        raise InputError(f"{where}: no Repair history table in retro_body")
    count = 0
    for line in lines[header_idx + 1 :]:
        stripped = line.strip()
        if not stripped.startswith("|"):
            break  # table ended
        first = _first_table_cell(stripped)
        if first is None:
            break
        if not first.isdigit() or int(first) <= 0:
            continue  # separator (`---`) or sentinel (`--`) row
        if _POLICY_ARTIFACT_MARKER in line and _ITERATION_COMMIT_REPAIR not in line:
            continue  # exempt policy artifact
        count += 1
    return count


def _resolve_cost(pr: dict[str, object], where: str) -> float:
    """Return a PR sample's cost from an inline ``cost`` or an observed ``pr_body``."""
    if "cost" in pr:
        return _as_number(pr.get("cost"), f"{where}.cost")
    body = pr.get("pr_body")
    if isinstance(body, str):
        return parse_pr_cost(body, f"{where}.pr_body")
    raise InputError(
        f"{where}: needs a numeric 'cost' or a 'pr_body' string to collect it from"
    )


def _resolve_repairs(pr: dict[str, object], where: str) -> float:
    """Return a PR sample's repairs from an inline ``repairs`` or ``retro_body``."""
    if "repairs" in pr:
        return _as_number(pr.get("repairs"), f"{where}.repairs")
    body = pr.get("retro_body")
    if isinstance(body, str):
        return float(parse_retro_repairs(body, f"{where}.retro_body"))
    raise InputError(
        f"{where}: needs a numeric 'repairs' or a 'retro_body' string to collect it from"
    )


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
            where = f"regime {name!r} prs[{j}]"
            total_cost += _resolve_cost(pr, where)
            total_repairs += _resolve_repairs(pr, where)
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
