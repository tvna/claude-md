# Standard Template

Use this template for every new standard so reviewers and CI find the
normative rule, its exceptions, and how it is enforced in the same order.
Copy the body below the divider into a new `docs/standards/<name>.md`, fill
each section, and register the file in [`../INDEX.md`](../INDEX.md). Remove a
section only when it genuinely does not apply, and replace it with a one-line
reason rather than leaving it blank.

See [`README.md`](README.md) for which documents belong in this lane.

---

## Template

---

# [Standard title]

## Scope

[The files, operations, or changes this rule applies to, and the boundary of
what it does not cover.]

## Rule

[The normative contract: the behavior that is required or forbidden. State it
so a reviewer or CI job can answer yes/no for a future change.]

## Why

[Why this rule exists: the failure it prevents or the property it guarantees.
Tie it to the concrete cost of not having the rule.]

## Why not

[Why a weaker rule, or no rule, was not adopted. If the rule was scoped down
from a broader version, record what was deliberately left out and why.]

## Exceptions and Evidence

[The conditions under which the rule may be waived and the evidence required
to use the exception. If there are no exceptions, say so explicitly.]

## Enforcement

[How the rule is enforced: the deterministic gate (script or CI job) that
checks it, or a statement that it remains review guidance until it can be
made deterministic. Per CLAUDE.md section 3, if the gate does not exist yet,
say so and link the tracking issue.]

## Verification

[The command(s) that confirm a change satisfies this standard, with expected
output.]
