# ADR Template

Use this template for every new architecture decision record so each decision
captures its context, the choice, and the rejected alternatives in the same
order (MADR-style). Copy the body below the divider into a new
`docs/adr/NNNN-short-title.md`, fill each section, and register the file in
[`../INDEX.md`](../INDEX.md). Number files sequentially; do not reuse a
number.

See the `adr/` section of [`../INDEX.md`](../INDEX.md) for the lane
description, or [`0001-hook-manager-prek.md`](0001-hook-manager-prek.md) for a
worked example.

---

## Template

---

# [NNNN. Short decision title]

Date: [YYYY-MM-DD]
Refs: [#NNNN](https://github.com/tvna/claude-md/issues/NNNN)

[Date is the day the decision was accepted. Refs lists the tracking issues as
full canonical URLs; CLAUDE.md section 3 requires citing the issue number in
every artifact. Keep both lines so each ADR matches the shape of
`0001-hook-manager-prek.md`.]

## Status

[Proposed | Accepted | Superseded by ADR-NNNN. Owner-approved decisions are
Accepted; record the approval source.]

## Context

[The forces at play: the problem, the constraints, and what made a decision
necessary now.]

## Decision

[The decision that was made, stated in active voice ("We will ...").]

## Why

[Why this decision is the right one given the context: the decision drivers
that favored it.]

## Why not

[Why the rejected alternatives lost, summarized. The detailed enumeration
lives in Considered Alternatives below.]

## Consequences

[What becomes easier and what becomes harder as a result. Include negative
consequences honestly, not only the benefits.]

## Considered Alternatives

[Each alternative weighed, with the reason it was rejected. Separate fact from
speculation (CLAUDE.md section 2).]
