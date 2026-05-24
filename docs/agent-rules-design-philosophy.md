# Agent Rules Design Philosophy and Responsibility Boundaries

This document is the meta-runbook for how this repository evolves
`.apm/instructions/master.instructions.md` and its compiled artifacts
(`CLAUDE.md` / `AGENTS.md`). It is the operator-facing companion to
[#226](https://github.com/tvna/claude-md/issues/226) and is the
deliverable for [#246](https://github.com/tvna/claude-md/issues/246).

It exists because the boundary between universal agent instructions
and repository-local material has, until now, lived only in reviewer
memory. PR #225 surfaced the cost of that gap when repository-specific
wording was added to a universal sentence and removed before merge.
This document replaces that memory with a responsibility matrix, a
decision tree, and a gap-analysis procedure that any reviewer (human
or agent) can apply reproducibly.

It is a judgment aid, not a deterministic gate. The deterministic
gates are the harness (`scripts/`, `.github/workflows/`, hooks). This
document tells reviewers which lane a rule belongs in *before* the
harness gets a chance to enforce or fail to enforce it.

## 1. Purpose and non-goals

**Purpose.**

- Name the four ownership lanes used by this repository: universal
  text, harness, repo-local doc, and project-local instructions.
- Map every section of `master.instructions.md` to the lanes that
  carry, enforce, or exemplify it.
- Provide a decision tree for placing a new candidate rule in the
  correct lane the first time.
- Provide a procedure for periodically scanning the repository for
  gaps (concepts present in one lane and missing from another that
  should own them) and for duplication (concepts present in two lanes
  with concrete wording that drifts).

**Non-goals.**

- Adding domain-driven-design vocabulary or any other meta-framework
  to the universal instructions. Per
  [#227](https://github.com/tvna/claude-md/issues/227), universal
  instruction text stays free of DDD terminology and
  repository-specific case studies.
- Becoming a hard gate. The repository already has
  `verify-apm-drift.yml`, `verify-body-policy.yml`,
  `verify-title-policy.yml`, `scan-non-ascii.yml`,
  `verify-apm-portability.yml`, and the `preflight_non_ascii.py`
  `PreToolUse` hook for the deterministic checks. This document does
  not duplicate those gates; it tells reviewers which lane each gate
  serves.
- Reframing the six principles. The principle text and the
  `*Layer: ...*` subtitles ([#75](https://github.com/tvna/claude-md/issues/75))
  are inputs to this document, not outputs.
- Extracting reusable examples into a separate examples document.
  The decision tree (section 4) and the worked examples (section 5)
  cross-reference each other on every trace; splitting them would
  force every change to update two docs and would expand the drift
  sweep (section 6.3) without a measurable navigability gain at the
  current document length. The repo-local retrospective docs
  (`docs/retrospective-pr-*.md`) already serve as the open-ended
  examples corpus that lives outside this document, and section 6.4
  governs how those retrospectives feed back into instruction
  changes.

## 2. Vocabulary - the four ownership lanes

A rule that an agent must follow can live in exactly one of four
lanes. The lane determines who enforces it, who reads it, and how it
changes.

| Lane | Source of truth | Audience | Change mechanism |
|---|---|---|---|
| Universal text | `.apm/instructions/master.instructions.md` | Every agent in every project that imports this repository | Edit the APM source; `apm compile` regenerates `CLAUDE.md` / `AGENTS.md`; `verify-apm-drift.yml` enforces no drift |
| Harness | `scripts/*.py` + `.github/workflows/*.yml` + Claude Code hooks declared in `.claude/settings.json` | The repository itself; runs without agent involvement | Edit the script or workflow; add or update a paired test in `tests/test_<name>.py` per `docs/workflow-script-quality.md` |
| Repo-local doc | `docs/*.md` in this repository | Contributors and reviewers of this repository; not exported to downstream consumers | Edit the doc; cross-link from the universal text only by abstract reference, never by literal example |
| Project-local instructions | Downstream consumer projects (`.apm/`, `CLAUDE.md` delta, project-specific runbooks) | Agents working in that one project | Owned entirely by the downstream consumer; this repository neither ships nor reviews it |

The four lanes are not interchangeable. Moving a rule from one to
another changes its blast radius, its enforcement guarantee, and its
audience. The decision tree in [section 4](#4-decision-tree) makes
that move explicit.

### 2.1 What "universal" means here

A universal rule is one that holds across every project that imports
this repository's compiled `CLAUDE.md` or `AGENTS.md`. Concretely:

- It does not name a specific tool, vendor, or product (Claude,
  Codex, Cursor, GitHub MCP, etc.). It may name abstract categories
  ("the harness", "the deterministic gate", "the issue tracker").
- It does not name a specific file, script, workflow, label, issue
  number, or PR number in this repository.
- It does not assume a specific build system, language ecosystem, or
  CI provider.
- It survives the consumer using a completely different stack, as
  long as that consumer adopts the underlying principle.

If any of the above is violated, the rule is not universal. It may
still be correct and useful, but it belongs in a different lane.

### 2.2 What "harness" means here

A harness rule is one that has been converted to a deterministic
check: a script, a workflow, a hook, or a ruleset. The harness rule
replaces reviewer memory with executable code. Per `CLAUDE.md`
section 3, deterministic work belongs in hooks and CI rather than
agent prompts.

The universal text refers to the harness only abstractly ("push
deterministic work into hooks"). The concrete harness lives in
`scripts/` and `.github/workflows/`, and its quality is governed by
`docs/workflow-script-quality.md`.

### 2.3 What "repo-local doc" means here

A repo-local doc captures everything that is true about this
repository but not true about every downstream consumer. This
includes:

- Operator runbooks for repository-specific workflows
  (`branch-cleanup.md`, `dependabot-automerge.md`, `rulesets.md`).
- Standards that are repository-wide but not universal
  (`issue-pr-body-standard.md`, `non-ascii-defense.md`,
  `workflow-script-quality.md`).
- Inventories of repository surfaces
  (`security-control-inventory.md`, `repo-scope.md`).
- Retrospective case studies (`retrospective-pr-*.md`).
- Measurement frameworks (`performance-metrics.md`).

A repo-local doc is allowed to name specific files, scripts, issues,
PRs, and tools. That is precisely what disqualifies it from the
universal lane.

### 2.4 What "project-local" means here

A project-local rule is anything the downstream consumer must define
for themselves. The classic example is `.github/owners.yaml` and
`.github/CODEOWNERS`: this repository defines the schema and the
harness (`scripts/plan_language_context.py`), but the actual
ownership-to-language mapping is repository-local and would differ in
every consumer.

This repository does not enforce, review, or ship project-local
material. The universal text simply requires that the consumer set
it up ("In plan mode, write user-facing plan artifacts and chat
responses in the primary project owner's native language. If the
project lacks ownership-language metadata, prepare it before relying
on this rule.").

## 3. Responsibility matrix - six layers by four lanes

Each row is one of the six principles in `master.instructions.md`,
identified by its `*Layer: ...*` subtitle. Each column is one of the
four ownership lanes from section 2. Cells contain the concrete
artifacts that own the concern, or `(gap)` if no artifact owns it
today.

The `Boundary risk` column records the pattern most likely to cause
the wrong lane to absorb a concern, drawn from the historical record
of merged PRs and closed sub-issues of #226.

| Layer (principle) | Universal text owns | Harness owns | Repo-local doc owns | Project-local owns | Boundary risk |
|---|---|---|---|---|---|
| P1 - goal and plan structure | Plan-mode trigger; document weight rule; verification design in the plan | `scripts/plan_language_context.py` (SessionStart hook); `tests/test_plan_language_context.py` | `docs/issue-pr-body-standard.md` (body shape encodes the plan); `docs/performance-metrics.md` (measurement is a verification artifact) | The consumer's plan-mode trigger discipline | Mixing plan-language responsibility with GitHub-post ASCII enforcement in one rule (corrected by [#227](https://github.com/tvna/claude-md/issues/227)) |
| P2 - pre-code reasoning | Fact-vs-speculation tagging; assumption enumeration; simpler-path proposal | `(none - agent judgment, not deterministic)` | `docs/issue-pr-body-standard.md` (Facts / Assumptions sections); `docs/issue-triage.md` (label-driven routing) | The consumer's own ambiguity policy | Speculation slipping into universal text disguised as a fact (PR #225) |
| P3 - delivery harness | Issue-first; ASCII discipline; declarative module management; auto-subscribe to PR activity; retrospective auto-open; classify each repair | `scripts/issue_link.py`, `body_policy.py`, `title_policy.py`, `pr_body_close_keyword_advisory.py`, `auto_retro.py`, `scan_non_ascii.py`, `preflight_non_ascii.py`, `branch_cleanup.py`, `rulesets_apply.py`, `ruleset_drift.py`, `labels_apply.py`, `dependabot_automerge.py`, `dependabot_labels.py`, `threat_intel_triage.py`, `uv_pin.py`, `scan_apm_portability.py`; 16 paired workflows; 19 paired tests | `docs/issue-pr-body-standard.md`, `docs/issue-triage.md`, `docs/non-ascii-defense.md`, `docs/rulesets.md`, `docs/branch-cleanup.md`, `docs/dependabot-automerge.md`, `docs/remote-environment.md`, `docs/repo-scope.md`, `docs/security-control-inventory.md`, `docs/retrospective-pr-*.md` | The consumer's own CI provider, issue tracker, and dependency manager | Naming a specific tool (gh CLI, GitHub Actions, dependabot) inside universal text; embedding a specific PR number as an example |
| P4 - artifact code | Minimum code; safety-bounded simplicity; fail-loud over silent default; debug instrumentation as attack surface | `(lint and type gates exist in workflow-script-quality.md M8; behavioral check is reviewer judgment)` | `docs/workflow-script-quality.md` (M1 to M9 must-have checklist; O1 to O7 optional enhancements) | The consumer's own language ecosystem and code style | Embedding a stack-specific example (Python, pytest, pydantic) into universal text |
| P5 - change scope and agent split | Touch-only-what-you-must; clean only your own orphans; sub-agent vs skill split; separate implementation and verification agents | `(none - agent judgment)` | `(gap candidate - no doc explicitly governs scope discipline today)` | The consumer's own agent inventory and roster | Mentioning a Claude-only feature (sub-agents, skills) by literal name as universal terminology |
| P6 - handoff and communication | Native-language plan artifacts; show procedure and case studies; visualize workflow; refuse LGTM; explain trade-offs | `scripts/plan_language_context.py` (owner-language metadata recovery); `.github/owners.yaml`; `.github/CODEOWNERS` | `docs/retrospective-pr-*.md` (case studies are the force-multiplier evidence); `docs/security-control-inventory.md` (visualization of the harness coverage); `docs/performance-metrics.md` (visualization of measurement) | The consumer's own `owners.yaml` entries | Treating "case studies" as universal content rather than as repo-local artifacts that the universal text merely *requires* |

Empty cells marked `(none ...)` are intentional: the layer's concern
is not enforceable by a script today. Cells marked `(gap candidate)`
are unintentional: a doc or harness should exist but does not. Gap
candidates are tracked by the procedure in
[section 6](#6-gap-analysis-procedure).

### 3.1 How to read a row

Take row P3. The universal text owns the abstract principle ("open a
GitHub issue before any branch, commit, or PR; cite its number in
every commit and PR"). The harness owns the deterministic enforcement
(`scripts/issue_link.py` plus `verify-issue-link.yml` plus
`tests/test_issue_link.py`). The repo-local doc owns the operator
runbook (`docs/issue-pr-body-standard.md` tells contributors exactly
what to put in the body). The project-local lane is the consumer's
own issue tracker, which this repository cannot enforce.

No single concrete artifact appears in two lanes with the same
wording. The universal text says "cite an issue number"; the
repo-local doc says exactly how (which section, which heading);
the harness says whether the body parses; the project-local lane is
whether the issue tracker exists at all. The lanes nest, they do not
overlap.

## 4. Decision tree - where does a new candidate rule belong?

When a new rule is proposed (in a sub-issue, in a PR description, in
a review comment), walk it through the questions below in order. The
first answer that fires determines the lane.

```
Q1. Is the rule tool-agnostic? (Does it avoid naming Claude, Codex,
    Cursor, GitHub MCP, gh CLI, or any other vendor or product?)

    No  -> Project-local lane. The rule is correct only for one
           ecosystem and must not appear in universal text. If the
           rule is also useful inside this repository, restate the
           tool-specific form in a repo-local doc and write a
           tool-agnostic abstract form in the universal text.

    Yes -> Q2.

Q2. Can the rule be enforced by a deterministic check (a script, a
    workflow, a hook, a ruleset)?

    Yes -> Harness lane. The universal text may say "build the
           harness for X"; the harness itself lives in
           scripts/ + .github/workflows/ + tests/ following
           docs/workflow-script-quality.md. The repo-local doc lane
           may also gain a runbook for the harness.

    No  -> Q3.

Q3. Does the rule require agent judgment and apply to every
    downstream consumer of this repository?

    Yes -> Q4.

    No  -> Q5.

Q4. Does the rule need a repository-specific noun (a file path, a
    script name, a PR number, an issue number, a tool name) to be
    understandable?

    Yes -> Repo-local doc lane (demoted). The universal text would
           need that noun to be intelligible, which makes it
           non-universal. Write the concrete form in a repo-local
           doc; the universal text may carry only the abstract form,
           and only if the abstract form survives without the noun.

    No  -> Universal text lane. Edit
           .apm/instructions/master.instructions.md; apm compile;
           verify-apm-drift.yml enforces the drift gate.

Q5. Is the rule a description of a past event (a retrospective, a
    repaired wording, an audit finding)?

    Yes -> Repo-local doc lane: docs/retrospective-pr-<N>.md or a
           new case-study doc. Case studies are explicitly required
           by P6 to exist somewhere, but they must not be embedded
           in the universal text.

    No  -> Hold. Open a sub-issue of #226 and treat the rule as a
           gap candidate until one of Q1 to Q5 resolves it.
```

### 4.1 Notes on the questions

- Q1 is first because tool-coupling is the cheapest disqualifier; if
  it fires, the rest of the tree is moot.
- Q2 is second because moving a concern into the harness removes it
  from reviewer memory entirely. If the harness can do it, the
  harness should do it.
- Q3 and Q4 together separate "universal in principle" from
  "universal in wording". Many rules pass Q3 but fail Q4; that is
  the typical pattern that produces a repo-local doc lane entry.
- Q5 catches case-study material that would otherwise drift into the
  universal text.

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

## 6. Gap analysis procedure

Run the three sweeps below whenever a new universal text bullet, a
new harness script, or a new repo-local doc lands. Each sweep
produces a list of cells in the matrix that need attention.

### 6.1 Forward sweep - universal to harness and doc

For each bullet in `.apm/instructions/master.instructions.md`,
identify which harness artifact or repo-local doc carries it. Bullets
with no carrier are gap candidates.

```sh
# Enumerate universal bullets (approximately 30 lines)
grep -nE '^- ' .apm/instructions/master.instructions.md
```

For each line, walk the matrix in section 3 and look for a cell that
names a concrete artifact carrying the concern. If none exists, open
a sub-issue of #226 proposing either:

- a new harness script (per `docs/workflow-script-quality.md`), or
- a new repo-local doc, or
- a justification for leaving the cell empty (some concerns are
  intentionally agent-judgment only).

### 6.2 Backward sweep - harness and doc to universal

For each harness artifact and repo-local doc, identify which
universal principle it serves.

```sh
# Enumerate harness artifacts
ls scripts/*.py .github/workflows/*.yml

# Enumerate repo-local docs
ls docs/*.md
```

For each artifact, walk the matrix and look for the row whose
universal text describes the principle it implements. Artifacts that
do not map to a row are either orphans (universal text gap - the
principle exists implicitly but is not stated) or out-of-scope
(should be deleted or moved). Open a sub-issue of #226 for each
orphan with a recommendation.

### 6.3 Drift sweep - duplication across lanes

For each cell in the matrix, check whether the same concrete wording
appears in another cell of the same row. Universal text should be
abstract; concrete wording should appear in at most one of harness,
repo-local doc, or project-local. If concrete wording is duplicated,
the two cells will drift over time.

```sh
# Spot-check by searching for a distinctive phrase in master + docs
grep -F "<phrase>" .apm/instructions/master.instructions.md docs/*.md
```

The fix for a drift hit is to keep the abstract form in the
universal text, keep the concrete form in exactly one lower lane,
and update the other lane to reference the canonical form.

### 6.4 Retrospective classification to action lane mapping

The retrospective harness (`scripts/auto_retro.py`) classifies each
repair found between PR open and merge into one of three taxonomy
categories. Each category maps onto a primary ownership lane; the
secondary lane is where the corresponding documentation or worked
example lands.

| Retrospective category | Primary lane | Typical secondary lane | Field example |
|---|---|---|---|
| Missing deterministic gate | Harness | Universal text (only if the gate enforces a new universal principle) | `docs/retrospective-pr-229.md` records a body-policy preflight gap surfaced between PR open and merge; the durable fix was a new `scripts/` preflight, not a universal-text edit |
| Unclear agent instruction | Universal text | Repo-local doc (a worked example or runbook clarification) | `docs/retrospective-pr-235.md` records an auto-retro skip-rule ambiguity; the durable fix was a wording tightening in the harness rule plus a clarifying note in the repo-local retrospective doc |
| External or human decision | Project-local | Repo-local doc (an escalation note describing the unresolved item) | `docs/retrospective-pr-237.md` records a no-repair merge where outstanding follow-up items required human judgment; nothing landed in universal text or harness |

The mapping is a router, not a deterministic gate: it tells the
contributor which lane to draft into first. The decision tree in
section 4 then validates whether that draft lane is the correct
final destination.

### 6.5 Cadence

Run all three sweeps at least once per merge that touches
`master.instructions.md`, `scripts/`, or `docs/`. The retrospective
auto-opened by `scripts/auto_retro.py` is the natural place to
record the sweep result; if a retrospective is not auto-opened (as
discussed in #226), the contributor of the touching PR runs the
sweeps manually.

## 7. Instruction-PR review criteria

Reviewers apply this section when a PR touches the universal source
or its compiled artifacts. The criteria below complement, but do not
replace, the deterministic gates listed in the project's PR template
and in section 7.2.

### 7.1 Applicability

A PR is in scope for this section if and only if its diff includes
at least one of:

- `.apm/instructions/master.instructions.md` (the universal source).
- `CLAUDE.md` (the compiled artifact; should change only as the
  verbatim output of `apm compile`).
- `AGENTS.md` (the compiled artifact; same constraint).

PRs that touch only `docs/`, `scripts/`, `tests/`, or
`.github/workflows/` fall outside this section; they have their own
review surface (`docs/workflow-script-quality.md` for harness PRs,
the body and title policies for every PR).

### 7.2 Deterministic gates the reviewer can rely on

Before any manual review begins, confirm the following automated
gates are green on the PR head commit:

- `verify-apm-drift.yml` confirms that `CLAUDE.md` and `AGENTS.md`
  are the verbatim output of `apm compile` for the current
  `.apm/instructions/master.instructions.md`.
- `verify-apm-portability.yml` runs
  `scripts/scan_apm_portability.py` and blocks repository-specific
  references (`#NNN` issue numbers, `docs/<name>.md` paths, script
  names, tool product names) inside universal text unless an
  explicit `portability-ack:` marker on the same line cites the
  authorizing sub-issue.
- `verify-body-policy.yml` and `verify-title-policy.yml` confirm
  the PR body and title follow `docs/issue-pr-body-standard.md`.
- `scan-non-ascii.yml` confirms no non-ASCII characters slipped
  into files that must remain ASCII.

A red light on any of the above is a hard block; do not advance to
the manual review questions in section 7.3 until the deterministic
gates pass. If a gate is missing for a category of risk that the
reviewer must still check, that gap itself is a candidate for the
gap analysis procedure in section 6.

### 7.3 Manual reviewer questions

For each non-trivial wording change in the PR diff, walk the
decision tree from [section 4](#4-decision-tree) (Q1 through Q5).
The source of truth for the questions is section 4; this subsection
does not re-derive them. The reviewer states the answer to each
question explicitly in a PR comment or review thread whenever the
answer is not obvious from the diff itself.

The three lane outcomes for a universal-text edit are:

- **Universal text** (Q1 yes, Q2 no, Q3 yes, Q4 no). Approve if the
  edit keeps the abstract form and avoids repository nouns.
- **Repo-local doc** (Q4 yes). Request changes; the concrete
  wording belongs in `docs/`, not in the universal text.
- **Harness** (Q2 yes). Request changes; the rule belongs in a
  script and workflow pair, not in agent prompt text.

If the diff touches `CLAUDE.md` or `AGENTS.md` directly without a
corresponding `.apm/instructions/master.instructions.md` change, the
review is also a hard block: those files are compiled artifacts and
the source of truth must move first.

### 7.4 Portability-ack escape hatch policy

`scripts/scan_apm_portability.py` recognizes a
`portability-ack: refs #<N>` marker that allows a single line of
otherwise-banned wording (a vendor name, a specific PR number, a
file path) inside universal text. The escape hatch exists because a
small amount of bootstrap text must name the repository it ships
from in order to be self-locating.

When the diff introduces or modifies a `portability-ack:` marker:

- The marker must cite a sub-issue of #226 (or its successor
  tracking issue) that explicitly authorizes the exception.
- The cited sub-issue must explain why the deterministic
  alternative (abstract wording, harness check, or repo-local doc)
  was rejected.
- The marker must not be used to bypass the section 7.3 Q4
  outcome; "wording needs a repository-specific noun" is the
  signal that the wording belongs in `docs/`, not the signal that
  an exception should be granted.

If any of the three conditions fails, request changes.

### 7.5 Worked case: PR #225

The repair loop on PR #225 (replayed in
[section 5.1](#51-pr-225---repository-specific-wording-in-a-universal-sentence))
is the canonical example for this section. A reviewer running the
criteria above on that PR's pre-repair state would have observed
Q4 = yes in the diff (the wording needed a repository-specific
noun) and would have requested the demotion to a repo-local doc
before merge, instead of allowing the repair to happen between PR
open and merge. The criteria in section 7 are designed to make that
catch reproducible.

## 8. Validation strategy

This document is valid only if:

- **Replay calibration.** Each of the seven closed sub-issues
  replayed in [section 5](#5-boundary-patterns-and-worked-examples)
  resolves through the decision tree to the lane the repository
  historically used. Today: seven of seven match.
- **Inverted self-consistency.** Each existing bullet of
  `.apm/instructions/master.instructions.md` resolves through
  Q1 to Q4 to the universal text lane. Bullets that do not resolve
  to universal text are themselves candidates for the same
  correction as #227.
- **Drift containment.** The gap analysis procedure in section 6
  detects newly added duplication or orphans before the next merge.
  This is enforced socially today; promoting it to a workflow is a
  potential follow-up.
- **No universal-text change.** This document does not modify
  `.apm/instructions/master.instructions.md` and does not cause
  `verify-apm-drift.yml` to fail. It is a repo-local doc and lives
  entirely in the repo-local lane.

If any of the four conditions starts failing, this document is the
problem, not the source it describes.

## 9. Update procedure and rollback

To update this document (add a row, add a worked example, fix a
boundary risk):

1. Open a sub-issue of [#226](https://github.com/tvna/claude-md/issues/226)
   describing the proposed change per
   `docs/issue-pr-body-standard.md` (Scope / Facts / Assumptions /
   Acceptance criteria / Verification / Parent).
2. Open a single PR that edits only this document and, if the
   addition requires it, the cross-link headers in
   `docs/repo-scope.md`, `docs/security-control-inventory.md`,
   `docs/issue-pr-body-standard.md`, `docs/non-ascii-defense.md`,
   and `docs/workflow-script-quality.md`.
3. Re-run the validation strategy in section 8. The replay table in
   section 5 must remain at 100 percent match; if a new closed sub-
   issue is added to the replay set, trace it explicitly.
4. Reference the parent #226 on the `Refs #` line of the PR body.

To roll back an addition: open a sub-issue of #226 explaining why
the addition no longer serves the goal in section 1, then revert in
a single PR that touches only this document.

This document does not modify `.apm/instructions/master.instructions.md`,
`CLAUDE.md`, or `AGENTS.md` under any circumstance. Any rule that
would require such a change goes through the universal-text update
flow, not this update flow.

## 10. References

- [#226](https://github.com/tvna/claude-md/issues/226) - parent
  tracking issue for `CLAUDE.md` evolution policy.
- [#246](https://github.com/tvna/claude-md/issues/246) - sub-issue
  that this document is the deliverable for.
- [#225](https://github.com/tvna/claude-md/pull/225) - the PR whose
  repaired wording motivated #226 and is replayed in section 5.1.
- [#75](https://github.com/tvna/claude-md/issues/75) - per-principle
  `*Layer: ...*` subtitles.
- [#227](https://github.com/tvna/claude-md/issues/227) - corrected
  layer responsibility boundaries; defines the no-DDD-vocabulary,
  no-repo-specific-case-study constraint that this document
  honors.
- [#43](https://github.com/tvna/claude-md/issues/43),
  [#45](https://github.com/tvna/claude-md/issues/45),
  [#47](https://github.com/tvna/claude-md/issues/47),
  [#73](https://github.com/tvna/claude-md/issues/73),
  [#77](https://github.com/tvna/claude-md/issues/77) - additional
  closed sub-issues replayed in section 5.
- [#79](https://github.com/tvna/claude-md/issues/79) - currently
  open structural sub-issue; out of scope for this document.
- `.apm/instructions/master.instructions.md` - the universal text
  this document describes; not modified by this document.
- `docs/repo-scope.md` - content-based prohibition of tool-specific
  configuration; theoretical grounding for the Q1 disqualifier.
- `docs/security-control-inventory.md` - five-column evidence table
  precedent; harness-lane coverage source.
- `docs/issue-pr-body-standard.md` - body shape standard; carries
  the Facts / Assumptions discipline from P2.
- `docs/non-ascii-defense.md` - the three-layer ASCII discipline
  enforced by the harness for P3 GitHub posts.
- `docs/workflow-script-quality.md` - the must-have checklist for
  harness scripts; the closest thing this repo has to a P4 quality
  gate beyond reviewer judgment.
- `docs/retrospective-pr-*.md` - case-study lane precedent for P6;
  individual retrospectives (PR #229, #235, #237) supply the field
  examples cited in section 6.4.
- `scripts/auto_retro.py` - retrospective harness whose
  three-category taxonomy (missing deterministic gate, unclear
  agent instruction, external or human decision) drives the
  section 6.4 mapping.
- `scripts/scan_apm_portability.py` - the portability gate cited by
  section 7.2 and section 7.4; rejects repository-specific
  references inside universal text and recognizes the
  `portability-ack:` marker.
