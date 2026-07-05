# PRD / Design Note Template

Use this template for every new design-stage document so reviewers find the
problem, the decision, and the rationale in the same order. Copy the body
below the divider into a new `docs/prd/<name>.md`, fill each section, and
register the file in [`../INDEX.md`](../INDEX.md) (and in
[`../../.gitapex/doc-dependencies.toml`](../../.gitapex/doc-dependencies.toml) when the
document is a node other documents or gates depend on).

## Two profiles

This lane holds two genres (see [`README.md`](README.md)). Pick the profile
that matches the document, then scale to its blast radius (CLAUDE.md
section 1):

- **Design PRD / decision record** - proposes a change or records a decision.
  Fill the whole skeleton. A heavyweight, multi-PR design fills every section;
  a lightweight note keeps the core sections and marks the rest `N/A` with a
  one-line reason.
- **Analysis / judgment aid** - a durable reasoning artifact (a responsibility
  matrix, a control inventory, a gap analysis) that records *how to reason*,
  not a single build decision. Keep the **core sections**; the sections tagged
  *(design PRD / decision record)* below are optional - omit them, or mark
  `N/A` with a one-line reason. Put the document's real substance (the matrix,
  the inventory, the findings, the figures) under `Requirements / Content`.

Sections tagged *(optional)* are the first to drop for a small note.

See [`README.md`](README.md) for which documents belong in this lane and
[`../proposals/README.md`](../proposals/README.md) for documents that still
carry an unresolved open question.

---

## Template

---

# [Design title]

Date: [YYYY-MM-DD]
Refs: [#NNNN](https://github.com/tvna/claude-md/issues/NNNN)

[Date is the day the design was written or the decision accepted. Refs lists
the tracking issues as full canonical URLs; CLAUDE.md section 3 requires
citing the issue number in every artifact, and section 6 requires full
canonical URLs in a decision brief. List the territory and companion files in
the relevant sections below so this document and `../INDEX.md` /
`README.md` stay in agreement.]

## Purpose

[What this design is for, in one or two sentences.]

## Background

[The context a reader needs: what exists today, what changed, what prompted
this work.]

## Facts

[The verified state that motivates the work. Per CLAUDE.md section 2, prefix
each verified statement with `Fact:` and each hypothesis or predicted
consequence with `Speculation:`, so a reviewer knows which lines need
pushback. This is the same Facts discipline `docs/standards/issue-pr-body-standard.md`
requires of issue and PR bodies.]

## Assumptions

[What the design trusts but has not verified. Enumerate these before
implementing (CLAUDE.md section 2); verify the unverified, or ask.]

## Target Users *(design PRD / decision record)*

[Who consumes the result: operators, reviewers, downstream agents, end users.]

## Use Cases *(design PRD / decision record)*

[The concrete scenarios this design must serve.]

## Goals *(design PRD / decision record)*

[What success looks like, stated as outcomes.]

## Success Metrics *(design PRD / decision record)*

[How a reader can tell the goals were met: observable, ideally measurable
signals.]

## Non-Goals

[What this design deliberately does not do, to bound scope (CLAUDE.md
section 4).]

## Requirements / Content

[For a design PRD: the functional and non-functional requirements (separate
the two if the non-functional set - performance, security, cost - is
non-trivial). For an analysis / judgment aid: the document's substance - the
responsibility matrix, the inventory table, the gap analysis, the figures, or
the findings. This is where an analysis note carries its weight.]

## Why

[Why this design was chosen, or why the analysis reaches its conclusion: the
reasoning that makes it the right answer to the problem.]

## Why not *(design PRD / decision record)*

[Why the considered alternatives were not chosen, summarized. The detailed
enumeration lives in Considered Alternatives below.]

## Considered Alternatives *(design PRD / decision record)*

[Each alternative considered, with the reason it was rejected. Separate fact
from speculation (CLAUDE.md section 2).]

## Acceptance Criteria *(design PRD / decision record)*

[The deterministic conditions that mark the design as delivered. For an
analysis note, fold the equivalent checks into Verification below.]

## Verification

[The runnable check that confirms the document's claims still hold: a command
that exits 0, a gate name, a re-verification procedure a reviewer can re-run
later. Per CLAUDE.md section 1, completion needs live proof, not plan-time
intent; name the check rather than describing it in prose. This is distinct
from Acceptance Criteria (a one-time delivery gate) - Verification is the
re-runnable invariant.]

## Scope

[What is in scope for the work this design drives, or the boundary of the
analysis.]

## Priority *(design PRD / decision record, optional)*

[Relative priority and any sequencing constraints.]

## Release Plan *(design PRD / decision record, optional)*

[How the change rolls out: phases, flags, or migration steps.]

## Milestones *(design PRD / decision record, optional)*

[Dated or ordered checkpoints.]

## Maintenance and Rollback

[How this document is updated (the change procedure, the code-owner or merge
gate that governs it) and how a change it drives is rolled back. Per CLAUDE.md
section 3, prefer `git revert` of the original commit(s) over hand-authored
inverse edits; name the smallest revert set.]

## Open Questions / Future Work *(optional)*

[Non-blocking unresolved questions, deferred or parked items, and non-binding
future-work candidates that the document records but does not act on now. Keep
only items that do NOT block a yes/no decision: an open question that blocks a
decision belongs in [`../proposals/`](../proposals/README.md), not here (see
[`README.md`](README.md)). Each item should say why it is deferred and what
would promote it to a tracked issue.]

## References

[Full canonical URLs and repository-relative paths for the issues, companion
documents, scripts, and workflows this document depends on or is depended on
by. Mirror the `Companion` column the lane README records for this file.]

## Graduation Path

[Where this document goes once the decision settles: to `docs/standards/`
when it becomes an adopted yes/no rule, or to `docs/runbooks/` when it
primarily tells an operator how to perform a task. An analysis / judgment aid
that is meant to stay a durable reasoning artifact records that here instead.]
