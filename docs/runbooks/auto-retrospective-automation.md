# Auto-retrospective automation -- operator runbook

Operator entry point for the auto-retrospective pipeline: the `open-retro`
job in [`.github/workflows/post-merge.yml`](../../.github/workflows/post-merge.yml)
that runs [`scripts/auto_retro.py`](../../scripts/auto_retro.py) on every
merged PR. This runbook tells an operator how the automation fires, what it
produces, how it decides to skip, how to verify a run, and how to pause or
roll it back.

The normative six-control contract for this operation lives in
[`docs/prd/privileged-operation-runbooks.md`](../prd/privileged-operation-runbooks.md)
section 9; this runbook holds the concrete operational commands that the
contract defers to.

## 1. Trigger surface

- **Event.** `pull_request_target: closed`, job-gated on
  `github.event.pull_request.merged == true`. There is no human dispatch
  path; the job runs automatically on every merged PR.
- **Entry point.** `python3 scripts/auto_retro.py run`.
- **Permissions.** `contents: read`, `issues: write`,
  `pull-requests: write` (scoped to the `open-retro` job).
- **Concurrency.** `auto-retro-pr-<number>` with `cancel-in-progress: false`,
  so a re-run for the same PR serializes behind the first.

## 2. What it produces

A new retrospective issue titled
`chore(auto-retro): review PR #<N> repair loops`, with body sections
`## Scope`, `## Facts`, `## Proposed work`, `## Verification`,
`## Acceptance criteria`, and `## Parent`. The pre-filled repair-history
table is built by `_build_repair_history_table` from five signal classes
(CI failures, fix-up commits, merge-from-main, multi-commit PRs, and failed
Verification pairs).

The source PR receives one back-link comment `Retrospective: #<n>`,
idempotent on the `<!-- auto-retro:back-link -->` marker.

## 3. Skip and idempotency rules

- **`should_skip`** returns skip for: retro-typed PRs (self-recursion guard;
  `chore(auto-retro)` and legacy `fix(auto-retro)` titles), bot-authored or
  bot-merged PRs (logins in [`scripts/_trusted_bots.py`](../../scripts/_trusted_bots.py)),
  and PRs with no repair signal. The post-signal gate also skips standalone
  retros whose repair rows are only exempt `[policy-artifact]` rows
  (merge-from-main, multi-commit policy artifacts) unless a review repair, CI
  failure, verification failure, or iteration commit makes the retro
  actionable.
- **`find_existing_retro`** short-circuits before `create_issue` when a retro
  for the same `PR #<N>` already exists (open or closed), with a
  substring-collision guard so `PR #249` does not match `PR #2490`.

The full branch logic is rendered in the generated
[`docs/generated/scripts/auto-retro-decision-tree.md`](../generated/scripts/auto-retro-decision-tree.md).

## 4. Verify a run

- Each run writes a one-section table to `$GITHUB_STEP_SUMMARY` recording the
  source PR, the action (`created` or `skip`), and the detail (existing retro
  number on duplicate, repair-signal aggregate on no-signal skip, or
  policy-artifact-only skip detail).
- The durable per-merge cadence trail is
  [`docs/archive/retrospective-pr-*.md`](../archive/). An unexpected gap or
  burst there is the first symptom of a regression.
- Dry-run-equivalent: [`tests/test_auto_retro.py`](../../tests/test_auto_retro.py)
  mocks the `gh_api` boundary and exercises every branch of `run()`. For a
  specific payload,
  `python3 scripts/auto_retro.py run --event-file <fixture.json> --repo tvna/claude-md`
  exits without side effects on the read-only paths (skip or existing-retro
  short-circuit).

## 5. Pause / resume

Use this for a runaway-issue incident while the cause is still under
investigation. It halts further auto-creates without touching existing retro
issues.

```sh
gh workflow disable .github/workflows/post-merge.yml --ref main   # pause
gh workflow enable  .github/workflows/post-merge.yml --ref main   # resume
```

## 6. Roll back the implementation

`git revert <merge-sha>` of the workflow or script PR removes the
deterministic trigger. Prefer the smallest revert set; see
[`revert-first-rollback.md`](revert-first-rollback.md).

Runaway retro issues are identifiable by label `type:docs + layer:meta` plus
title prefix `chore(auto-retro)` (legacy retros use `fix(auto-retro)`; Refs
#1069). Close them individually:

```sh
gh api --method PATCH /repos/tvna/claude-md/issues/<n> \
  -f state=closed -f state_reason=not_planned
```

The retrospective body is recoverable from the workflow run log, so a
wrongful close is reversible by re-opening.

## 7. Related procedures

- [`retro-labels.md`](retro-labels.md) -- classify retro issues (TP/FP) and
  the scanner-applied label set the generator consumes as prior information.
- [`retrospective-noise-flooding-procedure.md`](retrospective-noise-flooding-procedure.md)
  -- spot noise-commit and flooding patterns during the retrospective.
- [`pre-merge-retro-survey.md`](pre-merge-retro-survey.md) -- the
  complementary pre-merge survey Stop hook (a distinct gate).
- [`docs/standards/pr-subscription-lifecycle.md`](../standards/pr-subscription-lifecycle.md)
  -- terminal-state signal contract after the pipeline opens or reuses the
  retro issue.

## References

- [`.github/workflows/post-merge.yml`](../../.github/workflows/post-merge.yml) -- trigger.
- [`scripts/auto_retro.py`](../../scripts/auto_retro.py) -- generator.
- [`tests/test_auto_retro.py`](../../tests/test_auto_retro.py) -- branch coverage and dry-run surface.
- [`docs/prd/privileged-operation-runbooks.md`](../prd/privileged-operation-runbooks.md) section 9 -- six-control contract.
- [#149](https://github.com/tvna/claude-md/issues/149) -- tracking issue.
- [#1454](https://github.com/tvna/claude-md/issues/1454) -- this runbook's issue.
