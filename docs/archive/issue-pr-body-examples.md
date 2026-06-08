# Issue/PR body worked examples

This document was the "Worked examples" section of [`docs/issue-pr-body-standard.md`](../issue-pr-body-standard.md). It supplies one example issue body per `type:*` label and one example PR body. The examples are calibration material: they show the body shape the standard describes, but the standard itself (required H2 sections, ordering, rationale mapping) is the source of truth in the body doc.

## Worked examples

All examples are ASCII-only so they pass the `scan-non-ascii.yml` gate
unmodified.

Each fenced example below is gated against `scripts/body_policy.py` by
`tests/test_body_policy_examples.py` so the published examples cannot drift
from the validator. The test reads a machine-readable directive placed
immediately before each fenced block:

- `<!-- body-policy-example: kind=issue -->` - validate the block as an
  issue body (baseline H2/H3 required-section check).
- `<!-- body-policy-example: kind=pull_request shape=yes -->` - validate
  the block as a PR body (baseline required sections plus the
  post-2026-05-26 shape: Verification command/result pairs and Checklist
  H3 subsections). The agent-attribution footer is intentionally excluded:
  a static documentation example must not embed a live session footer.
- `<!-- body-policy-example: skip="reason" -->` - exclude the block from
  validation (used for the historical pre-cutoff PR sample). The reason is
  recorded so the exemption stays visible.

Every fenced block must carry one of these directives; the test fails loudly
if one is missing.

<!-- body-policy-example: kind=issue -->

### `type:feat` issue

```
## Scope
Add a workflow that posts a comment on every newly opened issue with the
routing decision derived from its labels.

## Facts
Fact: docs/issue-triage.md defines the routing table but the decision is
applied manually today.
Speculation: posting the decision as a comment will shorten the time
between issue open and first agent action.

## Proposed work
- Add .github/workflows/post-routing-comment.yml triggered on
  issues:opened and issues:labeled.
- Reuse the existing routing table; do not duplicate it in YAML.

## Verification
- actionlint .github/workflows/post-routing-comment.yml exits 0.

## Acceptance criteria
- A new issue with type:fix receives a comment naming the auto-fix
  candidate path within five minutes of open.
- The workflow exits 0 on a label-only issue with no type:* set.

## Parent
Refs #197
```

<!-- body-policy-example: kind=issue -->

### `type:fix` issue

```
## Scope
verify-issue-link.yml rejects PRs whose Refs line uses lowercase
"refs" even though the script claims case-insensitive matching.

## Facts
Fact: scripts/issue_link.py _REF_LINE uses re.IGNORECASE, but PR #NNN
was rejected with the "no issue reference" error despite carrying
"refs #NNN" on its own line.
Speculation: the regex anchor or the HTML-comment strip is consuming
the line before the match runs.

## Proposed work
- Add a failing test in tests/test_issue_link.py that feeds a body with
  "refs #1" on a line.
- Fix extract_refs so the test passes.

## Verification
- python -m pytest tests/test_issue_link.py -q exits 0.

## Acceptance criteria
- The new test passes.
- The original symptom no longer reproduces:
  `python scripts/issue_link.py verify --repo tvna/claude-md
  --body-file <fixture>` exits 0 for the lowercase body.
```

<!-- body-policy-example: kind=issue -->

### `type:refactor` issue

```
## Scope
Extract the Refs-line regex and the trusted-bot lookup from
scripts/issue_link.py into a separate scripts/_body_policy.py module.

## Facts
Fact: scripts/issue_link.py currently owns the regex and the trusted-bot
import side-by-side with the gh-api shelling logic.
Speculation: pulling the policy primitives into their own module will
make a future body-section gate (sibling sub-issue) easier to compose.
No behaviour change is intended.

## Proposed work
- Move _REF_LINE and the trusted-bot lookup into scripts/_body_policy.py.
- Re-import them from scripts/issue_link.py.

## Verification
- python -m pytest -q exits 0 with no test changes.

## Acceptance criteria
- pytest -q exits 0 with no test changes.
- ripgrep finds no remaining definition of _REF_LINE outside the new
  module.

## Parent
Refs #197
```

<!-- body-policy-example: kind=issue -->

### `type:docs` issue

This very issue, #206, is itself a worked example. See its rendered
body on GitHub.

```
## Scope
Publish a contributor-facing runbook that explains each section of the
issue/PR templates, why it exists, and what an agent does with it.

## Facts
Fact: docs/issue-triage.md already documents the label taxonomy and the
routing table, but does not describe body section semantics.
Speculation: without a written standard, the new templates become
tribal knowledge.

## Proposed work
- Add docs/issue-pr-body-standard.md.
- Link the new doc from docs/issue-triage.md.

## Verification
- python -c "import pathlib; assert pathlib.Path('docs/issue-pr-body-standard.md').exists()" exits 0.

## Acceptance criteria
- docs/issue-pr-body-standard.md exists with required sections,
  rationale, and worked examples.
- The runbook is linked from docs/issue-triage.md.

## Parent
Refs #197
```

<!-- body-policy-example: kind=issue -->

### `type:tracking` issue

```
## Scope
Track contributor-facing standards for issue and PR bodies, templates,
and the body-policy gate.

## Facts
- The de facto issue body pattern is documented in
  docs/issue-pr-body-standard.md.
- No issue templates and no comprehensive body-policy gate exist yet.

## Assumptions
- Each missing piece (template per type, gate, gate report shape) is
  scoped to its own child issue so each PR stays small.

## Initial child issues
- #206 docs(harness): document issue/PR body standard
- (sibling) feat(harness): add .github/ISSUE_TEMPLATE/*.yml
- (sibling) feat(harness): add comprehensive body-policy gate

## Completion criteria
This issue can close only when every child issue has merged or been
explicitly parked.
```

<!-- body-policy-example: skip="historical pre-2026-05-26 PR shape, retained as a record" -->

### PR body

```
## Summary
Add docs/issue-pr-body-standard.md and cross-link it from
docs/issue-triage.md.

## Related Issue

Refs #206

## Changes

- Add docs/issue-pr-body-standard.md with required sections, rationale,
  worked examples, gate description, and trusted-bot reference.
- Add a one-line cross-reference in docs/issue-triage.md.

## Verification

- [x] Doc is ASCII-only:
      `python -c "import pathlib;
       assert pathlib.Path('docs/issue-pr-body-standard.md')
       .read_text().isascii()"`
- [x] `pytest -q` exits 0.
- [x] PR body itself satisfies scripts/issue_link.py verify
      (this very Refs #206 line).

## Checklist

- [x] Issue number recorded on the `Refs #` line above
- [x] CLAUDE.md / AGENTS.md regenerated if applicable
- [x] CI green
```

<!-- body-policy-example: kind=pull_request shape=yes -->

### PR body (post-2026-05-26 shape)

PRs created on or after 2026-05-26 UTC must use the shape below.
`scripts/body_policy.py` (server) and
`scripts/preflight_pr_template_shape.py` (MCP hook) both enforce it.
The prior sample remains as a historical record of the pre-cutoff
shape.

```
## Summary

Tighten the PR body shape so Verification is recoverable evidence and
Checklist items map cleanly onto Bootstrap / After-merge / Post-merge
automation layers.

## Facts

- scripts/body_policy.py now exposes verify_pr_verification_pairs and
  verify_pr_checklist_subsections; tests in tests/test_body_policy.py
  cover both.
- scripts/auto_retro.py reads extract_verification_pairs and
  extract_post_merge_checklist; failed pairs and unchecked Post-merge
  items become rows in the auto-opened retro issue.

## Assumptions

- speculation: BODY_POLICY_SHAPE_CUTOFF set to 2026-05-26T00:00:00Z is
  far enough in the future to give in-flight PRs time to land before
  the gate flips.

## Risk & blast radius

- The shape gate fails any PR whose Verification or Checklist is not
  in the new shape. Back-catalog PRs are exempt via cutoff.

## Rollback

- Revert this PR with `git revert <sha>` and clear
  BODY_POLICY_SHAPE_CUTOFF in .github/workflows/verify-body-policy.yml.

## Verification

- command: `python3 -m pytest tests/test_body_policy.py tests/test_auto_retro.py tests/test_preflight_pr_template_shape.py -q`
  result: `exit 0`
- command: `python3 scripts/body_policy.py verify --kind pull_request --body-file /tmp/pr-body.md --shape-cutoff 2026-05-26T00:00:00Z --created-at 2026-05-27T00:00:00Z`
  result: `OK: pull_request body contains all required sections.`

## Checklist

### Bootstrap

- [x] Facts vs. Assumptions split is honest
- [x] Risk & blast radius assessed; Rollback steps are runnable
- [x] Issue number recorded on the `Refs #` line above

### After-merge (CI)

- [x] `pytest -q` exits 0 (paired in Verification above)
- [x] CI green on the merge commit
- [x] CLAUDE.md / AGENTS.md regenerated if applicable

### Post-merge (auto-retro signal)

- [ ] Linked issue closed by the merge
- [ ] auto-retro issue opened by `.github/workflows/auto-retro.yml`
- [ ] No follow-up `fix(...)` PR needed within 24h of merge

## Resource Consumption

- Elapsed (session start to PR create): 0:06:42
- Total tokens: 230,127 (input 2,859 / output 7,480 / cache-create 57,108 / cache-read 162,680)
- Cost (USD): $0.6396
- Model(s): claude-opus-4-8

## Related Issue

Refs #343
```
