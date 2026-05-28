# Measure verify-agents.yml timings

Operator runbook for the `measure-timings` job in [`.github/workflows/weekly-maintenance.yml`](../../.github/workflows/weekly-maintenance.yml).

## Purpose

Lift `scripts/analyze_ci_timings.py` from an operator-only offline procedure
(the docstring lines 13-23 record the gh-api / jq / python sequence) to a CI
job whose output lands in three places per run:

1. a workflow step summary (visible on the run page),
2. a 90-day-retained artifact named `ci-timings-report` (one `report.md`),
3. an optional comment on a `workflow_dispatch`-supplied issue.

The motivating consumer is issue #545 acceptance criterion 1 ("baseline timing
data posted as a comment before the implementation PR opens"). The workflow
makes that AC reachable by linking a run URL, instead of by an operator
copy-paste from a local shell. Future performance audits (e.g. heirs of #474)
should be able to satisfy the same shape by passing the audit's issue number.

The workflow is read-only against `verify-agents.yml` job metadata. It does
not edit `scripts/analyze_ci_timings.py`, does not write to any branch, and
does not open any issue.

## Trigger

| Trigger | Cron | Effect |
|---|---|---|
| `schedule` | `0 20 * * 0` (UTC) -- Monday 05:00 JST | Always assembles the report; uploads the artifact and appends the step summary. No issue comment (the input is unset on cron). |
| `workflow_dispatch` | manual | Select `task=measure-timings`. Same artifact + summary. When `measure_issue_number` is supplied, the workflow additionally posts the report as a comment on that issue. When `measure_cutoff` is supplied (a UTC `YYYY-MM-DD`), the report switches to compare mode: pre-cutoff (baseline) and post-cutoff (post-change) tables side-by-side with a delta p50 column. |

The timing report now runs with the rest of weekly maintenance at JST Monday
05:00 to keep weekly scheduled workflow entry points consolidated.

## Dispatching with an issue number

1. Actions -> "Weekly maintenance" -> Run workflow.
2. Select `task=measure-timings` and enter the issue number (no leading `#`) in the `measure_issue_number` input.
3. After the run completes:
   - the run page Summary tab shows the markdown report,
   - the `ci-timings-report` artifact is downloadable for 90 days,
   - a new comment with `report.md` appears on the supplied issue.

Leave `issue_number` blank to preview the report (artifact + summary only).
The conditional `if:` on the comment step covers both `null` and empty-string
inputs.

## Dispatching with a cutoff (compare mode)

Compare mode answers a single question: did a performance-claiming change
actually move p50, and by how much. The cutoff is the UTC date the change
landed on `main` (use the merge timestamp's calendar day). Samples with
`started_at` strictly before UTC midnight of the cutoff go into the
baseline column; samples at or after the cutoff go into the post-change
column.

1. Actions -> "Weekly maintenance" -> Run workflow.
2. Select `task=measure-timings` and enter the `measure_cutoff` input as `YYYY-MM-DD` (UTC). Optionally enter `measure_issue_number` to mirror the comment onto a tracking issue.
3. The report's per-job and per-step tables become
   `pre count | pre p50 | post count | post p50 | delta p50`. The delta
   column carries one of:
   - `+X.Y%` / `-X.Y%` -- both windows have samples; signed change.
   - `new` -- no pre-cutoff sample (the row appeared after the change).
   - `gone` -- no post-cutoff sample (the row existed only before).
   - `+inf` -- pre p50 was zero but post samples exist (edge case).

The single-window mode (no cutoff) remains the cron default, so the
scheduled weekly report is unchanged.

## Dispatching for issue #545 (closing AC1 and AC7)

To close issue #545 acceptance criteria AC1 (baseline timing data) and AC7
(post-change p50 strictly lower than baseline) with one workflow run:

1. Dispatch the workflow with `issue_number: 545` and
   `cutoff: 2026-05-28` (UTC calendar day of the PR #549 merge at
   `2026-05-27T21:53:06Z`; samples started at or after UTC midnight of
   `2026-05-28` land in the post-change column).
2. Confirm the new comment on #545 contains both the per-job and per-step
   compare tables with a `delta p50` column.
3. Read the row whose `job` is the longest matrix leg (today
   `lint-scripts-pytest-gate`, or one of the four `lint-scripts-pytest
   (preflight|policy|ci_ops|default)` rows when the matrix is itemized).
   AC7 holds when its delta is a negative percentage (post p50 strictly
   less than pre p50). If the delta is `+...%` or `new` paired with a
   pre p50 that the longest pre-cutoff job (`lint-scripts-pytest`)
   exceeded, file the revert decision per #545 AC7.
4. Reply on the AC1 thread linking the run URL and the resulting
   comment. Update retro #550's "earliest prevention point" column with
   "compare-mode dispatch of `weekly-maintenance.yml` before
   PR open" as the deterministic gate that would have caught the
   missing-baseline repair.

## What the report says

`scripts/analyze_ci_timings.py` renders two markdown tables. The column
shape depends on whether `--cutoff` is set:

| Mode | Section | Columns | What to look for |
|---|---|---|---|
| single-window (default) | Per-job durations | `count | p50 | p95 | max | trend(5)` | Critical-path candidates: the job with the highest `p95`. |
| single-window (default) | Per-step durations | `count | p50 | p95 | max | trend(5)` | Inside that job, the slowest steps; sustained `^` trend marks regressions. |
| compare (`--cutoff`) | Per-job durations | `pre count | pre p50 | post count | post p50 | delta p50` | Did the post-cutoff change move p50? Negative deltas confirm a win; `gone` / `new` flag rows that changed shape across the cutoff. |
| compare (`--cutoff`) | Per-step durations | `pre count | pre p50 | post count | post p50 | delta p50` | Same question at step granularity; pinpoints which step inside the longest job carried the change. |

Trend legend (printed below the second table in single-window mode):
`^` = newer half >10% slower, `v` = newer half >10% faster,
`=` = within +/-10%, `?` = fewer than 2 samples.

Delta legend (printed below the second table in compare mode):
`+X.Y%` post slower than pre, `-X.Y%` post faster, `new` row appeared
post-cutoff, `gone` row vanished post-cutoff, `+inf` pre p50 was zero
with post samples.

Both legends are intentionally ASCII so the comment passes
`scripts/preflight_non_ascii.py` without escaping.

## Permissions

- `contents: read` -- checkout only.
- `issues: write` -- only used by the optional comment step on
  `workflow_dispatch`.

No fine-grained PAT or app installation is required. The GitHub-managed
`GITHUB_TOKEN` is sufficient for both `gh api .../actions/runs` and
`gh issue comment`.

## Out of scope

- Long-term storage of historical reports (commit-to-branch, releases): the
  90-day artifact retention is the only persistence layer.
- Cross-workflow timing: only `verify-agents.yml` runs are pulled here. Add a
  separate workflow or generalize the script in a follow-up if other
  workflows need the same surface.
- Regression alerts: only the `trend(5)` indicator already produced by
  `analyze_ci_timings.py` is surfaced. No threshold-based notification is
  emitted.
- Edits to `scripts/analyze_ci_timings.py`: the script stays offline by
  design; the workflow is its CI-side caller, not its replacement.
