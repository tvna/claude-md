# Decision tree replay (calibration check)

This document was section 5 of [`docs/agent-rules-design-philosophy.md`](../agent-rules-design-philosophy.md). It traces closed sub-issues of [#226](https://github.com/tvna/claude-md/issues/226) through the decision tree in section 4 of that document. The traces are append-only calibration evidence that the tree reproduces this repository's historical lane assignments; they are not normative and should not be read for current rules.

## 5. Boundary patterns and worked examples

This section traces concrete cases through the decision tree. Each
trace shows which question fired, why, and which lane the rule
landed in. The traces are not normative; they are evidence that the
tree reproduces this repository's historical decisions.

### 5.1 PR #225 - repository-specific wording in a universal sentence

**What happened.** A universal instruction sentence was edited to
include wording that named a repository-specific concept, then the
wording was removed before merge.

**Decision tree trace.**

- Q1: Is the rule tool-agnostic? Yes (the underlying rule was about
  retrospective contracts, not about any tool).
- Q2: Can it be enforced deterministically? No - the contract is
  about how a human or agent should write retrospective issues.
- Q3: Does it require agent judgment and apply to every downstream
  consumer? Yes.
- Q4: Does the wording need a repository-specific noun? Yes - the
  added wording referenced repository-internal artifacts.
- **Lane: repo-local doc (demoted).** The abstract rule belongs in
  the universal text; the concrete repository-specific elaboration
  belongs in a repo-local doc (a retrospective or a runbook). The
  outcome of PR #225 is consistent with this trace.

### 5.2 #75 - per-principle Layer subtitles

**What happened.** Each principle gained a `*Layer: ...*` subtitle
to make cross-section conflicts structurally impossible.

**Decision tree trace.**

- Q1: Tool-agnostic? Yes.
- Q2: Deterministic? No - the rule is about how to organize the
  universal text itself.
- Q3: Agent judgment plus universal? Yes.
- Q4: Needs a repository-specific noun? No - "layer" is an abstract
  concept.
- **Lane: universal text.** Consistent with the historical outcome
  (the subtitles landed in `master.instructions.md`).

### 5.3 #227 - corrected layer responsibility boundaries

**What happened.** A bullet that mixed plan-language responsibility
and GitHub-post ASCII enforcement was split so each concern lived in
its owning section.

**Decision tree trace.**

- Q1: Tool-agnostic? Yes.
- Q2: Deterministic? Partially - the ASCII discipline is enforced by
  `scan-non-ascii.yml` and `preflight_non_ascii.py`. The plan-
  language rule is enforced by `plan_language_context.py`.
- Q3: Agent judgment and universal? Yes for the split decision
  itself.
- Q4: Needs a repository-specific noun? No - "the GitHub post
  boundary" and "the plan artifact boundary" are abstract.
- **Lane: universal text (a structural correction to existing
  universal text).** Consistent with the historical outcome.

### 5.4 #43 - integrate ownership-and-proof concepts

**What happened.** Concepts from an external CLAUDE.md (Boris) were
integrated into the universal text without embedding the source.

**Decision tree trace.**

- Q1: Tool-agnostic? Yes (the integrated concepts were abstract).
- Q2: Deterministic? Some derivative gates exist (issue-first), but
  the concepts themselves are agent judgment.
- Q3 and Q4: Universal and abstract.
- **Lane: universal text.** Consistent.

### 5.5 #45 - resolve principle contradictions

**What happened.** Pairwise contradictions between principles were
resolved through reordering and rewording, not by adding cross-
references.

**Decision tree trace.**

- Q1: Tool-agnostic? Yes.
- Q2: Deterministic? No - it is a structural edit of the universal
  text.
- Q3 and Q4: Universal and abstract.
- **Lane: universal text.** Consistent.

### 5.6 #47 - compress source by approximately 25%

**What happened.** The source was compressed while preserving the
disambiguations from #45.

**Decision tree trace.** Same lane as #45.

- **Lane: universal text.** Consistent.

### 5.7 #73 - reframe uncertainty control

**What happened.** Section 2 was reframed to make ambiguity-vs-
evidence the central distinction.

**Decision tree trace.** Same lane as #45 and #47 (structural edit
of universal text, abstract wording, agent judgment).

- **Lane: universal text.** Consistent.

### 5.8 #77 - move debug logging safety rule

**What happened.** A bullet about debug instrumentation as attack
surface was moved into section 4 (artifact code, safety).

**Decision tree trace.** Same lane as #227 (a structural correction
of which section owns the concern).

- **Lane: universal text.** Consistent.

### 5.9 Replay summary

Seven closed sub-issues replayed; all seven resolved to the lane the
repository historically used. The decision tree reproduces the
historical record without exception. This is the calibration check
that the tree is fit for use; it does not prove that the tree will
classify every future case correctly.
