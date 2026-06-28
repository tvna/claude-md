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

## Authoring checklist

Before submitting a new ADR, confirm each item below:

- For each claim about hook or toolchain wiring (e.g. "hook X activates
  automatically"), verify the claim against `.pre-commit-config.yaml`, the
  relevant runbook, and the tool's documented default behaviour before writing.
  Do not infer activation from config presence alone. (Refs #1824, PR #1822 R3:
  ADR-0001 rationale point 5 originally implied prek activates pre-push hooks
  automatically, when `prek install --hook-type pre-push` is still required.)

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
