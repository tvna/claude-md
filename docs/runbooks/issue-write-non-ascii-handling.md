# Issue write non-ASCII handling

This runbook covers GitHub issue updates that mutate issue bodies or acceptance
checkboxes. It exists because the #63 / #475 retrospective recorded a repeatable
failure path: a one-line GitHub UI edit spawned a sub-issue, an attempted parent
body update was rejected by `scripts/preflight_non_ascii.py`, and an acceptance
checkbox was left checked even though the matching implementation update had not
landed.

## Issue threshold

Open a GitHub issue before any branch, commit, or PR. Do not open a sub-issue
for a single GitHub UI-only edit that creates no branch, commit, or PR. Examples
include updating an issue body, changing an issue title, assigning labels, or
toggling an acceptance checkbox.

When a UI-only edit grows into repository work, stop and use the normal harness:
open or reuse an issue, create a branch, cite the issue in the commit and PR, and
run the relevant verification.

## Body re-validation

`mcp__github__issue_write` with `method=update` re-scans the complete `body`
argument through `scripts/preflight_non_ascii.py`. The scan covers the full body
that will be sent to GitHub, not only the line being changed.

If the existing body contains non-ASCII text, choose exactly one path:

- Omit the `body` argument when updating only state-mutating fields such as
  labels, assignees, milestone, or state.
- Translate the existing body to ASCII before sending the updated body.
- Append the `non-ascii-ack` opt-out marker when preserving non-ASCII is the
  deliberate and reviewed choice.

Failure symptom from #63: an issue body update that looked local to one
acceptance item failed because the full existing body still contained non-ASCII
content and lacked the opt-out marker.

## Checkbox ordering

Acceptance checkboxes are tracker state. Update them only after the
corresponding implementation or issue-body update succeeds.

When consistency matters, use serial issue writes:

1. Apply the implementation or body change.
2. Re-read the issue and verify the change is present.
3. Update the acceptance checkbox.
4. Re-read the issue and verify the checkbox matches the implementation state.

Do not update acceptance checkboxes in parallel with the implementation they
represent. The #63 / #475 retrospective cites acceptance item 4 as the motivating
case: the checkbox was checked while the matching #56 body update had been
rejected by preflight.

## Verification

- Confirm a UI-only edit does not create a branch, commit, PR, or sub-issue.
- Confirm any body update with existing non-ASCII content uses one of the three
  explicit body re-validation paths.
- Confirm acceptance checkboxes are updated after, not alongside, the
  implementation state they report.
