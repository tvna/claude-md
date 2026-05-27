# Measure verify-agents.yml timings

Operator runbook for [`.github/workflows/measure-lint-pytest-timings.yml`](../../.github/workflows/measure-lint-pytest-timings.yml).

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
| `schedule` | `0 1 * * 1` (UTC) -- Monday 10:00 JST | Always assembles the report; uploads the artifact and appends the step summary. No issue comment (the input is unset on cron). |
| `workflow_dispatch` | manual | Same artifact + summary. When `issue_number` is supplied, the workflow additionally posts the report as a comment on that issue. |

Cron offset rationale: the Sunday cluster (`branch-cleanup.yml` at
`0 20 * * 0`, `ruleset-drift.yml` at `0 21 * * 0`,
`security-control-drift-report.yml` at `0 23 * * 0`) reads from the same
GitHub REST API surface as this workflow. Shifting to Monday early UTC
avoids API contention and lands the report inside the JST business-day
window where reviewers will look at it.

## Dispatching with an issue number

1. Actions -> "Measure verify-agents.yml timings" -> Run workflow.
2. Enter the issue number (no leading `#`) in the `issue_number` input.
3. After the run completes:
   - the run page Summary tab shows the markdown report,
   - the `ci-timings-report` artifact is downloadable for 90 days,
   - a new comment with `report.md` appears on the supplied issue.

Leave `issue_number` blank to preview the report (artifact + summary only).
The conditional `if:` on the comment step covers both `null` and empty-string
inputs.

## Dispatching for issue #545 (closing AC1)

To satisfy issue #545 acceptance criterion 1 via a workflow run instead of an
operator-pasted comment:

1. Dispatch the workflow with `issue_number: 545`.
2. Confirm the new comment on #545 contains the markdown table whose shape is
   documented in `scripts/analyze_ci_timings.py` lines 30-34 (per-job and
   per-step aggregates with `count | p50 | p95 | max | trend(5)` columns).
3. Reply on the AC1 thread linking the run URL and the resulting comment.

## What the report says

`scripts/analyze_ci_timings.py` renders two markdown tables:

| Section | Columns | What to look for |
|---|---|---|
| Per-job durations | `count | p50 | p95 | max | trend(5)` | Critical-path candidates: the job with the highest `p95`. |
| Per-step durations | `count | p50 | p95 | max | trend(5)` | Inside that job, the slowest steps; sustained `^` trend marks regressions. |

Trend legend (also printed below the second table): `^` = newer half >10%
slower, `v` = newer half >10% faster, `=` = within +/-10%, `?` = fewer than
2 samples. The trend is intentionally ASCII so the comment passes
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
