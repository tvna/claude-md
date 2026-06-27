# ATT&CK coverage review cadence; Runbook

Operator-facing companion to the `remind` job in
[`.github/workflows/monthly-maintenance.yml`](../../.github/workflows/monthly-maintenance.yml).
Tracks [#184](https://github.com/tvna/claude-md/issues/184) under parent
[#178](https://github.com/tvna/claude-md/issues/178) (MITRE ATT&CK
coverage).

This runbook is the single source of truth for the review-comment
template that the reminder workflow extracts and posts. The drift report
runbook (`docs/runbooks/security-control-drift-report.md`) covers the
weekly live-signal channel; this runbook covers the monthly
structured-review channel they sit alongside.

## Scope

This runbook governs the monthly structured review of MITRE ATT&CK coverage
recorded on #178: which evidence an operator re-reads, how the review is posted,
and how the reminder workflow is operated. Reach for it once a month, or when
running the reminder workflow; not for the weekly automated drift signal, which
the security-control drift report (#180) covers.

## Why

ATT&CK coverage on #178 is not a one-time snapshot. Every month a
human (or operator running the reminder workflow) re-reads the 14
tactic rows against fresh evidence, updates any row whose status
changed, and records the review as a dated comment on the tracking
issue. Without a recurring review, drift accumulates silently between
the data-driven weekly drift report and the human-driven snapshot.

The cadence answers the only unchecked item on the #178 Tracking
checklist: "Define a recurring review cadence for this issue and
record each review as a comment with date, evidence checked, gaps
opened, and residual risk."

## Why not

Do not use this runbook for the weekly, data-driven drift signal; that is the
security-control drift report (#180), and running this monthly review more often
would only duplicate it. Monthly is deliberate, widened from an earlier
quarterly cadence at operator request: weekly overlaps the drift report, and
annual would let tactic state drift too far between reviews. Do not collapse the
per-month comments into a single rolling comment either; the timeline of dated
reviews is the history this cadence exists to preserve.

## Cadence

Monthly. The reminder workflow runs at 20:00 UTC on the 1st of every
month (cron `0 20 1 * *`), aligned with the weekly-maintenance slot.

| Trigger | UTC window | Posted on |
|---|---|---|
| Monthly | 20:00 UTC, 1st of each month | 1st of each month |

The cadence was widened from an earlier quarterly schedule (cron
`0 0 1-7 1,4,7,10 *` gated to the first Monday of January, April, July,
and October) to monthly at operator request when the reminder moved into
`monthly-maintenance.yml`. With a fixed monthly day-of-month the old
Monday-only job gate is gone: the cron fires once, on the 1st, so no
day-of-week guard is needed.

Weekly is left to the drift report (#180), and annual would let the
sub-issue and tactic state drift too far between reviews. Monthly is the
cadence the consolidated maintenance workflow runs and the smallest that
still adds a human-judgement pass on top of the weekly drift report.

## Trigger

| Trigger | Effect |
|---|---|
| `schedule` (`0 20 1 * *`) | Fires at 20:00 UTC on the 1st of every month. `dry_run` is forced to `false`; the workflow posts a fresh review reminder comment on #178. |
| `workflow_dispatch` | Manual; the `dry_run` input defaults to `true` so an operator can preview the assembled comment in the run's Summary tab without posting. |

The reminder posts a **new** comment each month (it is not a rolling
comment). Monthly review records form a timeline on #178 that a
reviewer can scroll; collapsing them into one rolling comment would
erase the history the cadence is meant to preserve.

## Evidence sources to re-check

Each review pulls from a fixed list of evidence so reviews are
reproducible and comparable across months:

1. **#178 ATT&CK table.** Re-read the 14 tactic rows. Update the
   `status` column for any row whose evidence has shifted.
2. **`docs/prd/security-control-inventory.md`.** Walk the
   per-surface entries (workflows, scripts, rulesets, labels, APM,
   dependencies, docs/runbooks) and confirm the Cross-reference
   table at the bottom still rolls up to each ATT&CK row correctly.
3. **Latest `security-control-drift-report` rolling comment on #178.**
   The comment identified by the HTML marker
   `<!-- security-control-drift-report -->`. Note any family whose
   status was `drift` or `error` for two or more weeks in a row.
4. **Sub-issue state.** Verify the open/closed state of the #178
   sub-issues (#179, #180, #181, #182, #183, #184, #341) and the
   related issues kept in the "Existing related issues reused"
   list (#56, #63, #102, #120, #170). Flag any that have been open
   without movement since the previous monthly review as `stale`.
5. **Recent merges to security-relevant surfaces.** `git log
   --since="1 month ago" --pretty=format:"%h %s"; .github
   scripts docs/prd docs/runbooks .apm pyproject.toml uv.lock`
   then map each match to the inventory section it touches.
6. **`docs/runbooks/workflow-permissions-audit.md`.** Re-check the
   least-privilege matrix for any workflow added or modified in the
   month.
7. **`docs/runbooks/downstream-instruction-review-checklist.md`.**
   Confirm any change touching `.apm/instructions/master.instructions.md`
   or compiled `CLAUDE.md` / `AGENTS.md` was reviewed against the
   checklist before merge.
8. **OWASP Agentic Top 10 (ASI01-ASI10) mapping.** Re-read the
   `OWASP Top 10 for Agentic Applications 2026` section of
   `docs/prd/security-control-inventory.md`; the peer axis to the
   ATT&CK table. Confirm every ASI item still carries a status and that
   the ASI03 / ASI08 / ASI10 residual-risk notes are still accurate.
   Completeness is gated deterministically by
   `scripts/owasp_asi_mapping.py verify` (PR time and weekly), so this
   review checks the *judgement* (are the statuses still correct?), not
   the presence of the rows.

If an evidence source is missing or unreadable, the review records
that fact under `Stale sub-issues or blocked work` rather than
silently skipping the row.

## Review comment template

The block delimited by the two markers below is the canonical
review-comment template. The reminder workflow extracts it via an awk
range expression matching the begin and end markers (each marker lives
on its own line; see the workflow file for the exact command) and
prepends a header line carrying the run date. Do not insert any prose
between the markers that is not part of the posted template.

<!-- attack-coverage-review-template:begin -->

### Review date

YYYY-MM-DD (UTC). Replace with the date the review is performed.

### Evidence checked

- [ ] #178 ATT&CK 14-row table re-read.
- [ ] `docs/prd/security-control-inventory.md` re-walked.
- [ ] Latest `security-control-drift-report` rolling comment on #178 reviewed.
- [ ] Sub-issue state confirmed (#179, #180, #181, #182, #183, #184, #341, #56, #63, #102, #120, #170).
- [ ] `git log --since="1 month ago"` on security-relevant surfaces reviewed.
- [ ] `docs/runbooks/workflow-permissions-audit.md` matrix reviewed.
- [ ] `docs/runbooks/downstream-instruction-review-checklist.md` reviewed.
- [ ] OWASP ASI01-ASI10 mapping in `security-control-inventory.md` re-walked (peer axis).

### ATT&CK tactic rows that changed status

List each row whose status moved (for example `partially covered` ->
`covered`). One bullet per row, citing the evidence link that drove the
status change. If no rows changed, write `none`.

-

### New gaps opened

List any ATT&CK row that is now `partially covered` or `not covered` and
does not yet have a follow-up issue. For each, name the follow-up issue
opened during this review. If no new gaps, write `none`.

-

### Accepted residual risks

List any row whose gap is not being closed this month and is being
held as accepted residual risk, with the reason and the conditions under
which the acceptance must be re-evaluated. If no residual risks, write
`none`.

-

### Stale sub-issues or blocked work

List any sub-issue or related issue that has been open the whole month
with no movement, or any review item that could not be checked because
its evidence source was unavailable. If nothing is stale, write `none`.

-

### Next review date

YYYY-MM-DD (UTC). Set to the 1st of the next month; this is
the date the reminder workflow will fire again.

<!-- attack-coverage-review-template:end -->

## Procedure

Post the monthly review:

1. **Preview (recommended).** Go to **Actions -> ATT&CK coverage review
   reminder -> Run workflow**, leave `dry_run` at the default `true`,
   and start the run. After it completes, open the run page and read
   the **Summary** tab; the assembled comment is appended to
   `$GITHUB_STEP_SUMMARY`.
2. **Post.** When the preview looks correct, re-run with `dry_run` set
   to `false`. The workflow `POST`s the assembled comment on #178.
3. **Edit in place.** After the comment lands, edit it directly on
   GitHub to fill in the per-section fields (review date, status
   changes, gaps, residual risks, stale items, next review date). The
   workflow never edits a comment it already posted; subsequent runs
   post a fresh comment.
4. **Fallback (no workflow access).** When Actions is unavailable, copy
   the block between the two markers in this runbook into a new comment
   on #178 manually, then fill it in.

## Verification

```sh
# 1. The runbook is ASCII-only (must pass issue-pr-triage.yml / scan).
python3 -c "import pathlib; assert pathlib.Path('docs/runbooks/attack-coverage-review-cadence.md').read_text().isascii()"

# 2. The template block extracts cleanly and contains all seven required H3 sections.
#    Markers are passed as awk variables so this command itself does not collide
#    with the workflow's literal-pattern awk range.
begin_marker='<!-- attack-coverage-review-template:begin'' -->'
end_marker='<!-- attack-coverage-review-template:end'' -->'
awk -v b="${begin_marker}" -v e="${end_marker}" '$0 ~ b, $0 ~ e' \
  docs/runbooks/attack-coverage-review-cadence.md \
  | grep -E '^### ' \
  | wc -l
# Expected: 7

# 3. The reminder workflow file is well-formed YAML.
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/monthly-maintenance.yml'))"
```

## Pause / Resume

This drives a recurring monthly reminder.

- **Pause.** **Actions -> ATT&CK coverage review reminder -> Disable workflow**
  stops the monthly post. Before pausing, record the date of the last posted
  review comment on #178 so the next review knows which month was last covered.
- **Resume.** Re-enable the workflow; the next first-of-month trigger posts a
  fresh reminder. A month missed while paused is recovered through the manual
  fallback (copy the template block into a new comment on #178) rather than
  waiting a full month for the next automated post.

## Rollback

The workflow is read-only on the repository side; it only `POST`s
one comment per month to a tracking issue. To roll back:

- **Stop further posts.** **Actions -> ATT&CK coverage review reminder
  -> Disable workflow**.
- **Remove a stray comment.** Delete the comment on #178 via the GitHub
  UI. Comments are append-only history; deleting a single monthly
  review does not affect repository state.
- **Revert the runbook + workflow.** `git revert <merge-commit-sha>`
  pulls back this runbook, the workflow file, and the `docs/INDEX.md`
  row in one step.

## References

- [`.github/workflows/monthly-maintenance.yml`](../../.github/workflows/monthly-maintenance.yml) --
  the `remind` job (monthly cadence) this runbook drives.
- [#178](https://github.com/tvna/claude-md/issues/178); ATT&CK coverage
  tracking issue (target of every review comment).
- [#184](https://github.com/tvna/claude-md/issues/184); the sub-issue
  this runbook closes.
- [`docs/prd/security-control-inventory.md`](../prd/security-control-inventory.md) --
  per-surface inventory that backs the ATT&CK table and carries the
  peer-axis OWASP Agentic Top 10 (ASI01-ASI10) mapping (#1378), gated by
  `scripts/owasp_asi_mapping.py`.
- [`docs/runbooks/security-control-drift-report.md`](security-control-drift-report.md) --
  weekly drift channel that the monthly review reads alongside.
- [`docs/runbooks/workflow-permissions-audit.md`](workflow-permissions-audit.md) --
  least-privilege matrix referenced by evidence item 6.
- [`docs/runbooks/downstream-instruction-review-checklist.md`](downstream-instruction-review-checklist.md) --
  downstream review checklist referenced by evidence item 7.
- [CLAUDE.md](../../CLAUDE.md) section 3; "After each merge, auto-open
  a retrospective issue; make this deterministic, not operator-memory."
  The reminder workflow applies the same discipline to the monthly
  review.
