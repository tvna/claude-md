# PRD / Design Note Template

Use this template for every new design-stage document so reviewers find the
problem, the decision, and the rationale in the same order. Copy the body
below the divider into a new `docs/prd/<name>.md`, fill each section, and
register the file in [`../INDEX.md`](../INDEX.md).

Scale the document to its blast radius (CLAUDE.md section 1): a heavyweight,
multi-PR design fills every section; a lightweight design note keeps the core
sections and marks the rest `N/A` with a one-line reason. Sections marked
*(optional)* below are the first to drop for a small note.

See [`README.md`](README.md) for which documents belong in this lane, and
[`../proposals/README.md`](../proposals/README.md) for documents that still
carry an unresolved open question.

---

## Template

---

# [Design title]

## Purpose

[What this design is for, in one or two sentences.]

## Background

[The context a reader needs: what exists today, what changed, what prompted
this work.]

## Target Users

[Who consumes the result: operators, reviewers, downstream agents, end users.]

## Use Cases

[The concrete scenarios this design must serve.]

## Goals

[What success looks like, stated as outcomes.]

## Success Metrics

[How a reader can tell the goals were met: observable, ideally measurable
signals.]

## Non-Goals

[What this design deliberately does not do, to bound scope (CLAUDE.md
section 4).]

## Requirements

[Functional and non-functional requirements. Separate the two if the
non-functional set (performance, security, cost) is non-trivial.]

## Why

[Why this design was chosen: the reasoning that makes it the right answer to
the problem.]

## Why not

[Why the considered alternatives were not chosen, summarized. The detailed
enumeration lives in Considered Alternatives below.]

## Considered Alternatives

[Each alternative considered, with the reason it was rejected. Separate fact
from speculation (CLAUDE.md section 2).]

## Acceptance Criteria

[The deterministic conditions that mark the design as delivered.]

## Scope

[What is in scope for the work this design drives.]

## Priority

[Relative priority and any sequencing constraints.]

## Release Plan

[How the change rolls out: phases, flags, or migration steps. *(optional)*]

## Milestones

[Dated or ordered checkpoints. *(optional)*]

## Graduation Path

[Where this document goes once the decision settles: to `docs/standards/`
when it becomes an adopted yes/no rule, or to `docs/runbooks/` when it
primarily tells an operator how to perform a task.]
