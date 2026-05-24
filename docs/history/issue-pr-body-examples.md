# Issue/PR body worked examples

This document was the "Worked examples" section of [`docs/issue-pr-body-standard.md`](../issue-pr-body-standard.md). It supplies one example issue body per `type:*` label and one example PR body. The examples are calibration material: they show the body shape the standard describes, but the standard itself (required H2 sections, ordering, rationale mapping) is the source of truth in the body doc.

## Worked examples

All examples are ASCII-only so they pass the `scan-non-ascii.yml` gate
unmodified.

### `type:feat` issue

```
## Scope
Add a workflow that posts a comment on every newly opened issue with the
routing decision derived from its labels.

## Why
Fact: docs/issue-triage.md defines the routing table but the decision is
applied manually today.
Speculation: posting the decision as a comment will shorten the time
between issue open and first agent action.

## Proposed work
- Add .github/workflows/post-routing-comment.yml triggered on
  issues:opened and issues:labeled.
- Reuse the existing routing table; do not duplicate it in YAML.

## Acceptance criteria
- A new issue with type:fix receives a comment naming the auto-fix
  candidate path within five minutes of open.
- The workflow exits 0 on a label-only issue with no type:* set.

## Parent
Refs #197
```

### `type:fix` issue

```
## Scope
verify-issue-link.yml rejects PRs whose Refs line uses lowercase
"refs" even though the script claims case-insensitive matching.

## Why
Fact: scripts/issue_link.py _REF_LINE uses re.IGNORECASE, but PR #NNN
was rejected with the "no issue reference" error despite carrying
"refs #NNN" on its own line.
Speculation: the regex anchor or the HTML-comment strip is consuming
the line before the match runs.

## Proposed work
- Add a failing test in tests/test_issue_link.py that feeds a body with
  "refs #1" on a line.
- Fix extract_refs so the test passes.

## Acceptance criteria
- The new test passes.
- The original symptom no longer reproduces:
  `python scripts/issue_link.py verify --repo tvna/claude-md
  --body-file <fixture>` exits 0 for the lowercase body.
```

### `type:refactor` issue

```
## Scope
Extract the Refs-line regex and the trusted-bot lookup from
scripts/issue_link.py into a separate scripts/_body_policy.py module.

## Why
Fact: scripts/issue_link.py currently owns the regex and the trusted-bot
import side-by-side with the gh-api shelling logic.
Speculation: pulling the policy primitives into their own module will
make a future body-section gate (sibling sub-issue) easier to compose.
No behaviour change is intended.

## Proposed work
- Move _REF_LINE and the trusted-bot lookup into scripts/_body_policy.py.
- Re-import them from scripts/issue_link.py.

## Acceptance criteria
- pytest -q exits 0 with no test changes.
- ripgrep finds no remaining definition of _REF_LINE outside the new
  module.

## Parent
Refs #197
```

### `type:docs` issue

This very issue, #206, is itself a worked example. See its rendered
body on GitHub.

```
## Scope
Publish a contributor-facing runbook that explains each section of the
issue/PR templates, why it exists, and what an agent does with it.

## Why
Fact: docs/issue-triage.md already documents the label taxonomy and the
routing table, but does not describe body section semantics.
Speculation: without a written standard, the new templates become
tribal knowledge.

## Proposed work
- Add docs/issue-pr-body-standard.md.
- Link the new doc from docs/issue-triage.md.

## Acceptance criteria
- docs/issue-pr-body-standard.md exists with required sections,
  rationale, and worked examples.
- The runbook is linked from docs/issue-triage.md.

## Parent
Refs #197
```

### `type:tracking` issue

```
## Goal
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
