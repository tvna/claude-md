# ATT&CK coverage review cadence -- Runbook

Operator-facing companion to
[`.github/workflows/attack-coverage-review-reminder.yml`](../../.github/workflows/attack-coverage-review-reminder.yml).
Tracks [#184](https://github.com/tvna/claude-md/issues/184) under parent
[#178](https://github.com/tvna/claude-md/issues/178) (MITRE ATT&CK
coverage).

This runbook is the single source of truth for the review-comment
template that the reminder workflow extracts and posts. The drift report
runbook (`docs/runbooks/security-control-drift-report.md`) covers the
weekly live-signal channel; this runbook covers the quarterly
structured-review channel they sit alongside.

## Purpose

ATT&CK coverage on #178 is not a one-time snapshot. Every quarter a
human (or operator running the reminder workflow) re-reads the 14
tactic rows against fresh evidence, updates any row whose status
changed, and records the review as a dated comment on the tracking
issue. Without a recurring review, drift accumulates silently between
the data-driven weekly drift report and the human-driven snapshot.

The cadence answers the only unchecked item on the #178 Tracking
checklist: "Define a recurring review cadence for this issue and
record each review as a comment with date, evidence checked, gaps
opened, and residual risk."

## Cadence

Quarterly. The reminder workflow runs at 00:00 UTC (09:00 JST) on
the first Monday of January, April, July, and October.

| Quarter | UTC trigger window | Posted on |
|---|---|---|
| Q1 | 00:00 UTC, first Monday of January | First Monday of January |
| Q2 | 00:00 UTC, first Monday of April | First Monday of April |
| Q3 | 00:00 UTC, first Monday of July | First Monday of July |
| Q4 | 00:00 UTC, first Monday of October | First Monday of October |

GitHub Actions cron treats `day-of-month` and `day-of-week` as OR
when both are set, so the workflow uses `0 0 1-7 1,4,7,10 *` (every
day 1-7 of those months) and gates to Monday inside the job with
`test "$(date -u +%u)" = "1"`. Days 2-7 fall through the guard and
exit 0 without posting.

Weekly is left to the drift report (#180), monthly would overlap with
that channel, and annual would let the sub-issue and tactic state
drift too far between reviews. Quarterly is the smallest cadence that
materially differs from the weekly drift report.

## Trigger

| Trigger | Effect |
|---|---|
| `schedule` (`0 0 1-7 1,4,7,10 *`) | Day-of-week guard limits posting to Monday. `dry_run` is forced to `false`; the workflow posts a fresh review reminder comment on #178. |
| `workflow_dispatch` | Manual; the `dry_run` input defaults to `true` so an operator can preview the assembled comment in the run's Summary tab without posting. Day-of-week guard is bypassed. |

The reminder posts a **new** comment each quarter (it is not a rolling
comment). Quarterly review records form a timeline on #178 that a
reviewer can scroll; collapsing them into one rolling comment would
erase the history the cadence is meant to preserve.

## Evidence sources to re-check

Each review pulls from a fixed list of evidence so reviews are
reproducible and comparable across quarters:

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
   without movement for the whole quarter as `stale`.
5. **Recent merges to security-relevant surfaces.** `git log
   --since="3 months ago" --pretty=format:"%h %s" -- .github
   scripts docs/prd docs/runbooks .apm pyproject.toml uv.lock`
   then map each match to the inventory section it touches.
6. **`docs/runbooks/workflow-permissions-audit.md`.** Re-check the
   least-privilege matrix for any workflow added or modified in the
   quarter.
7. **`docs/runbooks/downstream-instruction-review-checklist.md`.**
   Confirm any change touching `.apm/instructions/master.instructions.md`
   or compiled `CLAUDE.md` / `AGENTS.md` was reviewed against the
   checklist before merge.

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
- [ ] `git log --since="3 months ago"` on security-relevant surfaces reviewed.
- [ ] `docs/runbooks/workflow-permissions-audit.md` matrix reviewed.
- [ ] `docs/runbooks/downstream-instruction-review-checklist.md` reviewed.

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

List any row whose gap is not being closed this quarter and is being
held as accepted residual risk, with the reason and the conditions under
which the acceptance must be re-evaluated. If no residual risks, write
`none`.

-

### Stale sub-issues or blocked work

List any sub-issue or related issue that has been open the whole quarter
with no movement, or any review item that could not be checked because
its evidence source was unavailable. If nothing is stale, write `none`.

-

### Next review date

YYYY-MM-DD (UTC). Set to the first Monday of the next quarter; this is
the date the reminder workflow will fire again.

<!-- attack-coverage-review-template:end -->

## How to post the review

1. **Preview (recommended).** Go to **Actions -> ATT&CK coverage review
   reminder -> Run workflow**, leave `dry_run` at the default `true`,
   and start the run. After it completes, open the run page and read
   the **Summary** tab -- the assembled comment is appended to
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

## Rollback

The workflow is read-only on the repository side -- it only `POST`s
one comment per quarter to a tracking issue. To roll back:

- **Stop further posts.** **Actions -> ATT&CK coverage review reminder
  -> Disable workflow**.
- **Remove a stray comment.** Delete the comment on #178 via the GitHub
  UI. Comments are append-only history; deleting a single quarterly
  review does not affect repository state.
- **Revert the runbook + workflow.** `git revert <merge-commit-sha>`
  pulls back this runbook, the workflow file, and the `docs/INDEX.md`
  row in one step.

## Verify

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
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/attack-coverage-review-reminder.yml'))"
```

## References

- [`.github/workflows/attack-coverage-review-reminder.yml`](../../.github/workflows/attack-coverage-review-reminder.yml) --
  the reminder workflow this runbook drives.
- [#178](https://github.com/tvna/claude-md/issues/178) -- ATT&CK coverage
  tracking issue (target of every review comment).
- [#184](https://github.com/tvna/claude-md/issues/184) -- the sub-issue
  this runbook closes.
- [`docs/prd/security-control-inventory.md`](../prd/security-control-inventory.md) --
  per-surface inventory that backs the ATT&CK table.
- [`docs/runbooks/security-control-drift-report.md`](security-control-drift-report.md) --
  weekly drift channel that the quarterly review reads alongside.
- [`docs/runbooks/workflow-permissions-audit.md`](workflow-permissions-audit.md) --
  least-privilege matrix referenced by evidence item 6.
- [`docs/runbooks/downstream-instruction-review-checklist.md`](downstream-instruction-review-checklist.md) --
  downstream review checklist referenced by evidence item 7.
- [CLAUDE.md](../../CLAUDE.md) section 3 -- "After each merge, auto-open
  a retrospective issue -- make this deterministic, not operator-memory."
  The reminder workflow applies the same discipline to the quarterly
  review.
