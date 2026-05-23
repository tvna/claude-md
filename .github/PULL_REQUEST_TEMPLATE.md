<!--
Per CLAUDE.md §3, every PR must reference its issue (`#<number>`).
The `Refs #<number>` line below is validated by
.github/workflows/verify-issue-link.yml on every `pull_request` event
and enforced as a required status check on `main`
(see .github/rulesets/main.json). Accepted keywords (case-insensitive):
Refs, Closes, Fixes, Resolves.
-->

## Summary


## Related Issue

Refs #

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

## Verification

- [ ]

## Checklist

- [ ] Issue number recorded on the `Refs #` line above
- [ ] Facts vs. Assumptions split is honest (no speculation lurking in Facts)
- [ ] Risk & blast radius assessed; Rollback steps are runnable
- [ ] CLAUDE.md / AGENTS.md regenerated if applicable
- [ ] CI green
