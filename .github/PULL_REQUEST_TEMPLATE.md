<!--
Per CLAUDE.md section 3, every PR must reference its issue (`#<number>`).
The line below is validated by .github/workflows/verify-issue-link.yml
on every `pull_request` event and enforced as a required status check
on `main` (see .github/rulesets/main.json).

Default: `Closes #<number>` so the linked issue auto-closes on merge.
GitHub auto-closes on: Closes, Closed, Fixes, Fixed, Resolves, Resolved
(case-insensitive, including conjugations).

Use `Refs #<number>` instead ONLY when this PR is partial work whose
merge must NOT close the linked issue, AND one of the following holds:
  - the linked issue carries the `type:tracking` label (umbrella issue
    that lives on while children land), OR
  - add a literal `<!-- partial -->` line below to opt out of the
    closing-keyword gate (see scripts/issue_link.py and #216).
-->

## Summary


## Related Issue

Closes #

<!--
Facts -- CLAUDE.md section 2.
State only what is observable: diffs, command output, test names, log lines.
No speculation in this section. If you cannot point to evidence, move the
line to Assumptions below.
-->
## Facts

-

<!--
Assumptions -- CLAUDE.md section 2.
List what you are trusting but did not verify (library behavior, runtime
environment, upstream contracts, reviewer intent). Tag each line with
"speculation:" when it is a guess rather than a documented fact.
-->
## Assumptions

-

<!--
Risk & blast radius -- CLAUDE.md section 4.
Who or what is affected if this change is wrong, and how reversible is it?
Call out destructive or irreversible operations (deletes, force-push,
schema migrations, outbound sends, payments).
-->
## Risk & blast radius

-

<!--
Rollback -- CLAUDE.md section 4.
Exact steps to revert or disable this change when it misbehaves in prod.
For low-risk changes a single `git revert <sha>` is fine; say so explicitly.
For risky changes list the feature flag, config toggle, or migration-down
command a responder would run.
-->
## Rollback

-

<!--
Verification -- CLAUDE.md section 1.
Each entry is one observed verification, listed as a `command:` line and
its `result:` line. Treat these as Facts-tier evidence (CLAUDE.md section
2): only what was actually run, no plans, no speculation. Multiple
entries are encouraged when multiple commands were run.

Required shape (enforced by scripts/body_policy.py verify_pr_verification_pairs
for PRs created on or after 2026-05-26):

- command: `<inline-code>`
  result: `<exit code, log line, OK marker, or short observation>`
-->
## Verification

- command: ``
  result: ``

<!--
Checklist -- CLAUDE.md section 3.
Three H3 subsections separate items by automation layer. Required shape
enforced by scripts/body_policy.py verify_pr_checklist_subsections for
PRs created on or after 2026-05-26.
-->
## Checklist

### Bootstrap

<!--
Human cognition only. The author must judge each item; no CI or hook can
verify them. Leaving any item unchecked is a deliberate signal that the
author has not yet finished bounding the change.
-->

- [ ] Facts vs. Assumptions split is honest (no speculation lurking in Facts)
- [ ] Risk & blast radius assessed; Rollback steps are runnable
- [ ] Issue number recorded on the `Closes #` line above (or `Refs #` with rationale per the template comment)

### After-merge (CI)

<!--
Deterministic gates. CI verifies these. The Verification section above
should already contain matching command/result pairs for each item.
Check the box only when the matching pair is present.
-->

- [ ] `pytest -q` exits 0 (paired in Verification above)
- [ ] CI green on the merge commit (all required status checks)
- [ ] CLAUDE.md / AGENTS.md regenerated if applicable (`apm compile` produced no diff)
- [ ] If this PR touches `.apm/instructions/**`, `CLAUDE.md`, or `AGENTS.md`: `verify-apm-portability.yml` green; any `portability-ack:` marker cites its authorizing sub-issue
- [ ] If this PR touches `.apm/instructions/**`, `CLAUDE.md`, or `AGENTS.md`: `verify-apm-drift.yml` green; reviewer applied `docs/downstream-instruction-review-checklist.md`

### Post-merge (auto-retro signal)

<!--
auto_retro.py reads this subsection. An UNCHECKED item here becomes a
repair-history row in the retro issue auto-opened by
.github/workflows/auto-retro.yml. Operators check items only after
observing them post-merge; leaving items unchecked is the deliberate
signal that the retro should record that gate as missing.
-->

- [ ] Linked issue closed by the merge (or `Refs #` with rationale recorded)
- [ ] auto-retro issue opened by `.github/workflows/auto-retro.yml`
- [ ] No follow-up `fix(...)` PR needed within 24h of merge
