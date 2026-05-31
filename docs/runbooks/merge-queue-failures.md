# Merge queue failures runbook

Operator-facing companion to the GitHub Merge Queue rollout (issue #895).
Merge Queue lands each approved PR by building a transient
`merge_group` integration ref that stacks the queued PR on top of the
current `main` (plus any PRs ahead of it in the queue), runs the
required status checks against that ref, and squash-merges only when the
checks pass. This removes the author-side need to rebase a branch onto
`main` solely to satisfy an up-to-date-branch gate -- the root cause of
the force-push recovery trap in #895.

## Required checks on `merge_group`

For a required status check to gate the queue, its workflow must trigger
on `merge_group` in addition to `pull_request`. The required contexts
pinned in `.github/rulesets/main.json` are produced by:

| Required context | Workflow |
|---|---|
| `Portable PR policy / gate` | `.github/workflows/portable-pr-policy.yml` |
| `Verify repository scripts / gate` | `.github/workflows/verify-agents.yml` |
| `Verify dependabot labels / verify` | `.github/workflows/verify-dependabot-labels.yml` |
| `Verify design philosophy doc / verify` | `.github/workflows/verify-design-philosophy.yml` |
| `Verify ruleset sync / gate` | `.github/workflows/verify-ruleset-sync.yml` |

Each of those workflows carries a `merge_group:` trigger so the same job
that produces the `pull_request` check_run also produces the
`merge_group` check_run under the identical context name. The ruleset
contexts do not change -- only the trigger surface widens.

Steps whose only input is the PR body or title (title policy, body
structure, issue link, linked-issue titles, README translation parity)
are skipped on `merge_group` via
`if: ${{ github.event_name != 'merge_group' }}`, because no
`pull_request` payload exists on the integration ref. Those properties
were already validated when the PR was open; the queue re-validates only
the integrated working tree (APM portability, compile drift, checksums,
prek, the static script gates, and the ruleset sync check, which falls
back to `BASE_REF=main`).

## Triaging a red queue run

When a queued entry fails, classify the failure before re-queuing:

1. **Source defect in the queued PR.** The same check fails on the PR's
   own `pull_request` run. Fix it on the PR branch and re-queue.
2. **Semantic conflict with an earlier queued PR.** The PR is green on
   its own `pull_request` run but red on `merge_group` because a PR
   ahead of it in the queue changed the integrated state. Rebase or
   re-open the PR against the new `main` once the earlier PR lands, then
   re-queue.
3. **Missing merge-group CI coverage.** A required context never reports
   on the `merge_group` ref (the check sits pending forever). This means
   a workflow producing a required context lacks the `merge_group:`
   trigger. Add it, regenerate
   `docs/generated/workflows/<name>-if-branches.md` with
   `python3 scripts/workflow_diagram.py diagram-doc`, and confirm
   `python3 scripts/verify_required_check_contexts.py verify` still
   passes (the context name is unchanged; only the trigger widened).
4. **External flake.** A transient network or runner failure. Re-queue
   without code changes; if it recurs, treat it as a source defect and
   investigate.

## Adding a new required check

When a new required status check is added to
`.github/rulesets/main.json`, its producing workflow MUST also trigger on
`merge_group`, or the queue will stall waiting for a context that never
reports on the integration ref. The `verify_required_check_contexts`
gate enforces that the context name matches a workflow job, but it does
not assert the `merge_group:` trigger -- that remains an operator
checklist item until a deterministic gate covers it.

## Companion

- `.github/workflows/portable-pr-policy.yml` -- required PR policy gate
- `.github/workflows/verify-agents.yml` -- required repository-scripts gates
- `.github/workflows/verify-dependabot-labels.yml` -- required dependabot-labels gate
- `.github/workflows/verify-design-philosophy.yml` -- required design-philosophy gate
- `.github/workflows/verify-ruleset-sync.yml` -- required ruleset-sync gate
- `.github/rulesets/main.json` -- required-status-check SoT and `merge_queue` rule
- `docs/runbooks/rulesets.md` -- apply / verify / rollback for the ruleset SoT
- Refs #895
