# Proposals -- Pre-Decision Evaluations

This lane holds design-stage evaluations whose requirements are not yet
decidable: documents that still carry one or more open questions that
block a yes/no decision, typically because they need a human follow-up,
a live API response, or evidence that does not yet exist.

Use this lane when a document answers questions such as:

- Should we adopt this change at all, and what is still unknown before
  that decision can be made?
- Which open questions are blocking the decision, and what is the status
  of each (answered, answered-with-caveat, pending)?
- What would the migration look like if the decision were "yes"?

A proposal is provisional by construction. Keep the open questions and
their status visible in the document so a reviewer can see at a glance
what still blocks the decision.

## Difference from `prd/`

`docs/prd/` is for design-stage rationale and **decision records** -- the
reasoning behind a choice that has already been made. `docs/proposals/`
is for evaluations where the decision is still **pending** because a
requirement cannot yet be resolved. Do not place a document with an
unresolved open question in `prd/`; place it here until the question is
answered.

## Graduation path

Once every open question is resolved:

- if the outcome is a settled design decision or rationale record, move
  the document to `docs/prd/`;
- if it defines a yes/no rule that reviewers or CI use, move it to
  `docs/standards/`;
- if it primarily tells an operator how to perform a task, move it to
  `docs/runbooks/`;
- if the proposal is rejected, record the rejection in the tracking
  issue and let the document follow the `archive/` retention policy.

Update `docs/INDEX.md` whenever a document enters, moves within, or
leaves this lane.
