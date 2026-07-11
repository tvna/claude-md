"""Pure triage/prior layer for ``scripts/auto_retro.py``.

The middle layer of the auto-retro refactor (Refs #1725, a precondition
for #1702): the label-derived prior, the cross-retro triage-report
aggregate, and the prior-based skip / tentative decisions. Every function
here is pure; it operates on :class:`_auto_retro_parse.PastRetro`
populations supplied by the IO layer, computes statistics, and renders the
triage-report Markdown; with no GitHub API calls or filesystem access.

Depends on :mod:`_auto_retro_parse` for the signal universe
(``_SIGNAL_NAMES``) and shared dataclasses, plus the constants-only
``_retro_labels`` helper. It never imports ``auto_retro`` or
``_auto_retro_render``, keeping the dependency graph acyclic.

``scripts/auto_retro.py`` re-exports every public and underscore-prefixed
name defined here so existing ``import auto_retro as ar; ar.<X>`` callers
and tests keep working unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

from _auto_retro_parse import _SIGNAL_NAMES
from _retro_labels import (
    ALL_RETRO_LABELS,
    PRIOR_MIN_SAMPLE_SIZE,
    PRIOR_SKIP_THRESHOLD,
    PRIOR_TENTATIVE_THRESHOLD,
    RETRO_EXPIRED,
    RETRO_FP,
    RETRO_FP_CANDIDATE,
    RETRO_TENTATIVE,
    RETRO_TP,
)

# CLAUDE.md section 3 taxonomy labels used to classify each repair row in a
# retro issue. Slugs match the backtick names in _auto_retro_render.py's
# operator-fill block. `pr-body-content-quality` is the fourth category,
# tracking defects observable in the PR body itself (placeholder residue,
# empty sections, missing examples, retro-feedback-loop). Refs #1828.
KNOWN_REPAIR_CATEGORIES: frozenset[str] = frozenset(
    {
        "missing-deterministic-gate",
        "unclear-agent-instruction",
        "external-human-decision",
        "pr-body-content-quality",
    }
)


@dataclass(frozen=True)
class PastRetro:
    """A past retro issue's signal set and label set, captured for the prior.

    ``signals`` is the frozenset of signal names parsed from the retro
    body's ``- Signals fired:`` line (empty for pre-#582 retros).
    ``labels`` is the frozenset of label strings currently applied to
    the retro; the prior only cares whether ``retro:fp`` is among
    them, but the full set is preserved so future retrofits can layer
    on other labels without changing the dataclass shape.

    ``state`` (``"open"``/``"closed"``) and ``title`` default to the
    pre-#1386 values so the prior/drift/sentinel construction sites and
    every existing test keep working unchanged; the triage-report
    dashboard (recent-retros list, open-untriaged count) reads them when
    populated by :func:`fetch_past_retro_labels`.
    """

    number: int
    signals: frozenset[str]
    labels: frozenset[str]
    state: str = "open"
    title: str = ""


def compute_prior_from_labels(
    past_retros: list[PastRetro],
    signal_names: tuple[str, ...] = _SIGNAL_NAMES,
    epoch_min_number: int = 0,
) -> dict[str, tuple[float, int]]:
    """For each signal name, return ``(fp_rate, sample_size)``.

    ``fp_rate`` is

        |{r in eligible : signal in r.signals and RETRO_FP in r.labels}|
        / max(1, |{r in eligible : signal in r.signals}|)

    and ``sample_size`` is the denominator (un-floored). Empty input
    yields ``(0.0, 0)`` for every signal; the consumer
    (:func:`should_skip_by_prior`) gates on ``sample_size >=
    PRIOR_MIN_SAMPLE_SIZE`` so the empty-prior case degrades to
    "open normally" rather than to a silent skip. Refs #582.

    *epoch_min_number* drops retros whose issue ``number`` is below the
    boundary from the population before any counting; the live skip
    decision in :func:`run` passes
    :data:`PRIOR_EPOCH_MIN_RETRO_NUMBER` so retros opened under the old
    (pre-#1227) signal semantics do not poison the prior. The default
    ``0`` keeps the function a pure tally over the supplied population
    (used by the descriptive triage report and by the unit tests).
    Refs #1227.
    """
    eligible = (
        past_retros
        if epoch_min_number <= 0
        else [r for r in past_retros if r.number >= epoch_min_number]
    )
    prior: dict[str, tuple[float, int]] = {}
    for name in signal_names:
        denom = sum(1 for r in eligible if name in r.signals)
        if denom == 0:
            prior[name] = (0.0, 0)
            continue
        numer = sum(
            1 for r in eligible if name in r.signals and RETRO_FP in r.labels
        )
        prior[name] = (numer / denom, denom)
    return prior


# Triage labels in the fixed display order used by the triage report.
# Mirrors the universe in :data:`ALL_RETRO_LABELS` but is ordered so the
# rendered pie/table is byte-stable across runs. Refs #1042. RETRO_EXPIRED
# is last: it is a weak, unconfirmed signal (the sentinel closed the retro
# without operator engagement), so an operator-set retro:tp/fp/fp-candidate/
# tentative label always wins the display priority over it. Refs #2433,
# #2439 review.
_TRIAGE_LABELS: tuple[str, ...] = (
    RETRO_TP,
    RETRO_FP,
    RETRO_FP_CANDIDATE,
    RETRO_TENTATIVE,
    RETRO_EXPIRED,
)
_UNLABELLED_KEY: str = "unlabelled"

# How many most-recent retros (by issue number) the dashboard lists, and
# the trailing window over which it recomputes the FP rate for the trend
# line. Numbers are the recency proxy: a higher issue number is newer.
# Refs #1386.
_RECENT_RETRO_COUNT: int = 10
_FP_TREND_WINDOW: int = 20

# Loop-health panel (issue #2434). The unlabelled-ratio anomaly fires when a
# majority of a large-enough observed population carries none of
# :data:`ALL_RETRO_LABELS`, so a "no anomalies" headline can never mask
# "nothing was ever labelled"; the all-unlabelled degenerate the per-signal
# FP gate (:meth:`SignalStat.is_anomaly`) is structurally blind to, because an
# unlabelled retro contributes to no signal's FP numerator. The 0.5 majority
# bar mirrors :data:`PRIOR_SKIP_THRESHOLD` and the sample floor reuses
# :data:`PRIOR_MIN_SAMPLE_SIZE`, so the loop-health gate shares the FP gate's
# "insufficient signal to judge" discipline. Both are operator-tunable here.
_UNLABELLED_ANOMALY_RATIO: float = 0.5
_UNLABELLED_MIN_SAMPLE: int = PRIOR_MIN_SAMPLE_SIZE


def _retro_status(labels: frozenset[str]) -> str:
    """Return the single display status for a retro from its label set.

    Triage labels are checked in :data:`_TRIAGE_LABELS` priority order so
    a multi-labelled retro renders one stable status; a retro carrying no
    triage label is ``"untriaged"``.
    """
    for label in _TRIAGE_LABELS:
        if label in labels:
            return label
    return "untriaged"


def _retro_fp_rate(retros: list[PastRetro]) -> tuple[float, int]:
    """Return ``(fp_rate, triaged_count)`` over *retros*.

    A retro is *triaged* iff it carries ``retro:tp`` or ``retro:fp``; the
    rate is ``|retro:fp| / |triaged|``. An empty triaged population yields
    ``(0.0, 0)`` so callers can render "n/a" without a zero-division guard
    at each site.
    """
    triaged = [r for r in retros if (RETRO_FP in r.labels or RETRO_TP in r.labels)]
    if not triaged:
        return 0.0, 0
    fp = sum(1 for r in triaged if RETRO_FP in r.labels)
    return fp / len(triaged), len(triaged)


@dataclass(frozen=True)
class SignalStat:
    """Per-signal occurrence and false-positive statistics for the report.

    ``fire_count`` is the number of past retros whose ``Signals fired:``
    line carries this signal; ``fire_rate`` is that count over the total
    retro population. ``fp_count`` / ``fp_rate`` reuse the exact prior
    definition from :func:`compute_prior_from_labels` (a retro counts as
    a false positive iff it carries ``retro:fp``). ``sample_size`` equals
    ``fire_count`` and is surfaced so a reader can judge whether
    ``fp_rate`` clears :data:`PRIOR_MIN_SAMPLE_SIZE` before trusting it.
    """

    name: str
    fire_count: int
    fire_rate: float
    fp_count: int
    fp_rate: float
    sample_size: int

    @property
    def is_anomaly(self) -> bool:
        """True when the prior would skip a future retro on this signal.

        Mirrors the gate in :func:`should_skip_by_prior`: the FP rate is
        at or above :data:`PRIOR_SKIP_THRESHOLD` AND the sample is large
        enough (:data:`PRIOR_MIN_SAMPLE_SIZE`) to trust the estimate.
        This is the anomaly a human should catch by inspection.
        """
        return (
            self.sample_size >= PRIOR_MIN_SAMPLE_SIZE
            and self.fp_rate >= PRIOR_SKIP_THRESHOLD
        )


@dataclass(frozen=True)
class RecentRetro:
    """One row of the dashboard's recent-retros list.

    ``status`` is the :func:`_retro_status` display label; ``state`` is the
    GitHub issue state (``"open"``/``"closed"``).
    """

    number: int
    title: str
    status: str
    state: str


@dataclass(frozen=True)
class TriageReport:
    """Cross-retro aggregate: triage-status counts plus per-signal stats.

    ``total`` is the size of the observed retro population. ``label_counts``
    maps each triage label (and the :data:`_UNLABELLED_KEY` bucket) to the
    number of retros carrying it; a single retro may carry more than one
    triage label, so the label counts are independent tallies and need not
    sum to ``total``. ``signal_stats`` is ordered by :data:`_SIGNAL_NAMES`.

    The remaining fields back the #1386 dashboard sections and default to
    empty/zero so older construction sites and tests stay valid:
    ``open_untriaged`` counts open retros carrying no triage label;
    ``recent`` is the most-recent slice (newest first) for the recent-retros
    table; ``fp_rate_all``/``fp_triaged`` are the all-time retro-level FP
    rate and its triaged denominator; ``fp_rate_recent``/``fp_recent_triaged``
    are the same over the trailing :data:`_FP_TREND_WINDOW` for the trend.
    """

    total: int
    label_counts: dict[str, int]
    signal_stats: tuple[SignalStat, ...]
    open_untriaged: int = 0
    recent: tuple[RecentRetro, ...] = ()
    fp_rate_all: float = 0.0
    fp_triaged: int = 0
    fp_rate_recent: float = 0.0
    fp_recent_triaged: int = 0
    population_total: int = 0

    @property
    def anomalies(self) -> tuple[SignalStat, ...]:
        """Signals whose prior would skip a future retro; the headline set."""
        return tuple(s for s in self.signal_stats if s.is_anomaly)

    @property
    def truncated(self) -> bool:
        """True when the observed sample is smaller than the live population.

        Distinguishes a silent cap (issue #2413's root defect) from a
        genuinely complete read: ``population_total`` is the caller-supplied
        live count (defaults to ``total`` when unknown, so callers that never
        pass it render exactly as before).
        """
        return self.population_total > self.total

    # ------------------------------------------------------------------
    # Loop-health panel (issue #2434). All three metrics derive from
    # ``total`` and ``label_counts`` already computed by
    # :func:`compute_triage_report`, so no new stored field is needed.
    # ------------------------------------------------------------------

    @property
    def unlabelled(self) -> int:
        """Retros carrying none of :data:`ALL_RETRO_LABELS`."""
        return self.label_counts.get(_UNLABELLED_KEY, 0)

    @property
    def triaged(self) -> int:
        """Retros carrying at least one ``retro:*`` label."""
        return self.total - self.unlabelled

    @property
    def triage_rate(self) -> float:
        """Fraction of the observed population that carries a retro label.

        The counterpoint to the retro production count (``total``): a low
        triage rate means retros are being opened faster than they are
        classified.
        """
        return self.triaged / self.total if self.total else 0.0

    @property
    def sentinel_disposed(self) -> int:
        """Retros the sentinel auto-closed, i.e. carrying ``retro:expired``.

        ``retro:expired`` is applied only by ``sentinel_run`` before the
        ``not_planned`` close (Refs #2439), so this count is the sentinel
        disposal volume over the observed population.
        """
        return self.label_counts.get(RETRO_EXPIRED, 0)

    @property
    def sentinel_disposal_rate(self) -> float:
        """Fraction of the observed population auto-closed by the sentinel."""
        return self.sentinel_disposed / self.total if self.total else 0.0

    @property
    def unlabelled_ratio(self) -> float:
        """Fraction of the observed population carrying no retro label."""
        return self.unlabelled / self.total if self.total else 0.0

    @property
    def unlabelled_anomaly(self) -> bool:
        """True when a majority of a large-enough population is unlabelled.

        The loop-health counterpart to :meth:`SignalStat.is_anomaly`: it
        makes the all-unlabelled degenerate visible as an Anomaly in its
        own right, so a "no anomalies" headline cannot mean "nothing was
        ever labelled". Gated by :data:`_UNLABELLED_MIN_SAMPLE` so a tiny
        early population is reported as insufficient signal rather than a
        false alarm. Refs #2434.
        """
        return (
            self.total >= _UNLABELLED_MIN_SAMPLE
            and self.unlabelled_ratio >= _UNLABELLED_ANOMALY_RATIO
        )


def compute_triage_report(
    past_retros: list[PastRetro],
    signal_names: tuple[str, ...] = _SIGNAL_NAMES,
    total_live: int | None = None,
) -> TriageReport:
    """Aggregate *past_retros* into a :class:`TriageReport`.

    Pure and GitHub-independent: the caller supplies the population
    (typically from :func:`fetch_past_retro_population`). Triage-label tallies
    count each label independently (a retro may carry several); the
    ``unlabelled`` bucket counts retros with none of
    :data:`ALL_RETRO_LABELS`. Per-signal FP statistics are taken verbatim
    from :func:`compute_prior_from_labels` so the report and the live skip
    decision can never disagree on the numbers. Refs #1042.

    *total_live* is the live population size BEFORE any fetch cap (e.g. a
    search API's ``total_count``); pass it whenever the caller knows the
    population may be larger than ``len(past_retros)`` so the rendered
    report can declare truncation instead of silently under-reporting
    (refs #2413). Defaults to ``len(past_retros)`` (no truncation) when the
    caller does not know or the population was read in full.
    """
    total = len(past_retros)
    population_total = total if total_live is None else total_live
    label_counts: dict[str, int] = {
        label: sum(1 for r in past_retros if label in r.labels)
        for label in _TRIAGE_LABELS
    }
    label_counts[_UNLABELLED_KEY] = sum(
        1 for r in past_retros if not (r.labels & ALL_RETRO_LABELS)
    )
    prior = compute_prior_from_labels(past_retros, signal_names)
    signal_stats: list[SignalStat] = []
    for name in signal_names:
        fp_rate, sample = prior[name]
        # numer is an exact integer (fp_rate == numer / sample), so
        # round() recovers it without float drift for any realistic
        # population size.
        fp_count = round(fp_rate * sample)
        fire_rate = sample / total if total else 0.0
        signal_stats.append(
            SignalStat(
                name=name,
                fire_count=sample,
                fire_rate=fire_rate,
                fp_count=fp_count,
                fp_rate=fp_rate,
                sample_size=sample,
            )
        )
    open_untriaged = sum(
        1
        for r in past_retros
        if r.state == "open" and not (r.labels & ALL_RETRO_LABELS)
    )
    by_recency = sorted(past_retros, key=lambda r: r.number, reverse=True)
    recent = tuple(
        RecentRetro(
            number=r.number,
            title=r.title,
            status=_retro_status(r.labels),
            state=r.state,
        )
        for r in by_recency[:_RECENT_RETRO_COUNT]
    )
    fp_rate_all, fp_triaged = _retro_fp_rate(past_retros)
    fp_rate_recent, fp_recent_triaged = _retro_fp_rate(
        by_recency[:_FP_TREND_WINDOW]
    )
    return TriageReport(
        total=total,
        label_counts=label_counts,
        signal_stats=tuple(signal_stats),
        open_untriaged=open_untriaged,
        recent=recent,
        fp_rate_all=fp_rate_all,
        fp_triaged=fp_triaged,
        fp_rate_recent=fp_rate_recent,
        fp_recent_triaged=fp_recent_triaged,
        population_total=population_total,
    )


def render_triage_report_markdown(report: TriageReport) -> str:
    """Render a :class:`TriageReport` as the checked-in Markdown document.

    The shape lets a human detect an anomaly by inspection (CLAUDE.md
    section 6): the Anomalies block sits at the top, a Mermaid pie shows
    the triage-status mix, the FP-rate trend and recent-retros list make
    the live backlog visible, and the per-signal table flags every signal
    whose prior would skip a future retro. The report depends on live
    GitHub label state, so it is a non-deterministic snapshot and is NOT
    part of the deterministic generated docs. Refs #1042, #1386.
    """
    observed_line = f"Retros observed: **{report.total}**"
    if report.truncated:
        observed_line = (
            f"Retros observed: **{report.total} of {report.population_total} "
            "(truncated)**"
        )
    lines: list[str] = [
        "# Auto-retro triage report",
        "",
        "This file is generated from live GitHub retro-issue labels by "
        "`python3 scripts/auto_retro.py triage-report`. Do not edit it by "
        "hand. Unlike the per-script AST docs it is a non-deterministic "
        "snapshot of repository state, so it is refreshed on merge by the "
        "`post-merge.yml` workflow (which opens a pull request when the "
        "snapshot drifts) rather than as part of the deterministic generated docs.",
        "",
        observed_line,
        "",
        f"Open untriaged: **{report.open_untriaged}**",
        "",
        "## Anomalies",
        "",
    ]
    if report.anomalies or report.unlabelled_anomaly:
        if report.anomalies:
            lines.append(
                f"Signals whose prior FP rate is at or above "
                f"{PRIOR_SKIP_THRESHOLD:.2f} (n >= {PRIOR_MIN_SAMPLE_SIZE}); "
                f"these signals now suppress new retros via "
                f"`should_skip_by_prior`:"
            )
            lines.append("")
            for stat in report.anomalies:
                lines.append(
                    f"- `{stat.name}`: FP rate {stat.fp_rate:.2f} "
                    f"(n={stat.sample_size})"
                )
        if report.unlabelled_anomaly:
            if report.anomalies:
                lines.append("")
            lines.append(
                f"- **unlabelled ratio {report.unlabelled_ratio:.2f}**: "
                f"{report.unlabelled} of {report.total} observed retros carry "
                f"no `retro:*` label (>= {_UNLABELLED_ANOMALY_RATIO:.2f}, "
                f"n >= {_UNLABELLED_MIN_SAMPLE}); retros are being opened "
                f"faster than they are triaged."
            )
    else:
        lines.append(
            "None: no fired signal clears both the FP-rate and "
            "sample-size thresholds, and the unlabelled ratio is below "
            f"{_UNLABELLED_ANOMALY_RATIO:.2f}."
        )
    lines.extend(_render_loop_health(report))
    lines.extend(["", "## Triage status", ""])
    if report.total == 0:
        lines.append("No retros observed yet.")
    else:
        lines.append("```mermaid")
        lines.append("pie showData")
        lines.append('    title Triage status')
        for label in (*_TRIAGE_LABELS, _UNLABELLED_KEY):
            lines.append(f'    "{label}" : {report.label_counts[label]}')
        lines.append("```")
    lines.extend(
        [
            "",
            "## Signal occurrence and false-positive rates",
            "",
            "| Signal | Fired | Fire rate | FP | FP rate | n | Anomaly |",
            "| --- | --: | --: | --: | --: | --: | :-: |",
        ]
    )
    for stat in report.signal_stats:
        marker = "!!" if stat.is_anomaly else ""
        lines.append(
            f"| `{stat.name}` | {stat.fire_count} | "
            f"{stat.fire_rate:.2f} | {stat.fp_count} | "
            f"{stat.fp_rate:.2f} | {stat.sample_size} | {marker} |"
        )
    lines.extend(_render_fp_trend(report))
    lines.extend(_render_recent_retros(report))
    return "\n".join(lines) + "\n"


def _render_loop_health(report: TriageReport) -> list[str]:
    """Render the loop-health panel (issue #2434).

    Surfaces three metrics over the observed population so an operator can
    see by inspection (CLAUDE.md section 6) whether the retro loop is
    converging: the triage rate (production vs classification), the
    sentinel disposal rate (how much is auto-closed without engagement),
    and the unlabelled ratio (flagged as an Anomaly above in the headline
    when it crosses :data:`_UNLABELLED_ANOMALY_RATIO`). This section is
    descriptive; the anomaly determination lives in the Anomalies block.
    """
    lines = ["", "## Loop health", ""]
    if report.total == 0:
        lines.append("No retros observed yet.")
        return lines
    lines.append(
        f"- Triage rate: **{report.triaged} / {report.total}** "
        f"({report.triage_rate:.0%}) of observed retros carry a `retro:*` "
        f"label; **{report.unlabelled}** ({report.unlabelled_ratio:.0%}) "
        f"remain unlabelled."
    )
    lines.append(
        f"- Sentinel disposal: **{report.sentinel_disposed}** "
        f"({report.sentinel_disposal_rate:.0%}) auto-closed via "
        f"`retro:expired` without operator engagement."
    )
    return lines


def _render_fp_trend(report: TriageReport) -> list[str]:
    """Render the retro-level FP-rate trend section.

    Compares the all-time FP rate against the trailing
    :data:`_FP_TREND_WINDOW`-retro window so a human can see at a glance
    whether triaged retros are trending more or less false-positive.
    """
    lines = ["", "## False-positive rate trend", ""]
    if report.fp_triaged == 0:
        lines.append("No triaged retros yet (no `retro:tp`/`retro:fp` labels).")
        return lines
    delta = report.fp_rate_recent - report.fp_rate_all
    if report.fp_recent_triaged == 0:
        direction = "n/a"
    elif abs(delta) < 0.005:
        direction = "flat"
    elif delta > 0:
        direction = "rising"
    else:
        direction = "falling"
    lines.append(
        f"- All-time: {report.fp_rate_all:.2f} (n={report.fp_triaged} triaged)"
    )
    lines.append(
        f"- Last {_FP_TREND_WINDOW} retros: {report.fp_rate_recent:.2f} "
        f"(n={report.fp_recent_triaged} triaged); {direction}"
    )
    return lines


def _render_recent_retros(report: TriageReport) -> list[str]:
    """Render the most-recent-retros table (newest first)."""
    lines = ["", "## Recent retros", ""]
    if not report.recent:
        lines.append("No retros observed yet.")
        return lines
    lines.append("| # | State | Status | Title |")
    lines.append("| --: | :-- | :-- | :-- |")
    for r in report.recent:
        title = r.title or "(no title)"
        lines.append(f"| {r.number} | {r.state} | {r.status} | {title} |")
    return lines


def _max_active_fp(
    signals: dict[str, bool],
    prior: dict[str, tuple[float, int]],
    min_sample_size: int,
) -> tuple[float, str | None, int]:
    """Return ``(max_fp_rate, signal_name, sample_size)`` over active signals.

    Only signals that fired on the current PR AND have a sample_size of
    at least ``min_sample_size`` are considered. When no qualifying
    signal exists, returns ``(0.0, None, 0)``. Shared helper used by
    both :func:`should_skip_by_prior` and :func:`is_tentative_by_prior`
    to keep the "max wins" rule centralised.
    """
    best: tuple[float, str | None, int] = (0.0, None, 0)
    for name, fired in signals.items():
        if not fired:
            continue
        rate, sample = prior.get(name, (0.0, 0))
        if sample < min_sample_size:
            continue
        if rate >= best[0]:
            best = (rate, name, sample)
    return best


def should_skip_by_prior(
    signals: dict[str, bool],
    prior: dict[str, tuple[float, int]],
    skip_threshold: float = PRIOR_SKIP_THRESHOLD,
    min_sample_size: int = PRIOR_MIN_SAMPLE_SIZE,
) -> tuple[bool, str]:
    """Return ``(skip, reason)`` based on the label-derived prior.

    Skips when the MAX fp_rate over signals that fired on the current
    PR (and meet the sample-size floor) is greater than or equal to
    ``skip_threshold``. The "worst signal wins" rule matches
    :func:`scripts.scan_retro_followup_drift.aggregate_drift`. When
    no signal qualifies, returns ``(False, "")``; the empty-prior
    safety net.
    """
    rate, name, sample = _max_active_fp(signals, prior, min_sample_size)
    if name is not None and rate >= skip_threshold:
        return True, (
            f"prior FP rate {rate:.2f} for signal {name!r} "
            f"(n={sample}) >= {skip_threshold}"
        )
    return False, ""


def is_tentative_by_prior(
    signals: dict[str, bool],
    prior: dict[str, tuple[float, int]],
    tentative_threshold: float = PRIOR_TENTATIVE_THRESHOLD,
    skip_threshold: float = PRIOR_SKIP_THRESHOLD,
    min_sample_size: int = PRIOR_MIN_SAMPLE_SIZE,
) -> bool:
    """True when the prior places the retro in the tentative band.

    The tentative band is ``[tentative_threshold, skip_threshold)``:
    the prior is high enough that the retro might be a false positive
    but not high enough to skip outright. The caller (``run``) records
    this verdict by adding ``retro:tentative`` to the issue labels so
    operators see the uncertainty at triage time.

    Sample-size gating matches :func:`should_skip_by_prior` so the
    same population is considered for both decisions.
    """
    rate, name, _sample = _max_active_fp(signals, prior, min_sample_size)
    if name is None:
        return False
    return tentative_threshold <= rate < skip_threshold
