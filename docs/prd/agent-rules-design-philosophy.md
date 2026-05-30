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
  `portable-pr-policy.yml`, `verify-github-content.yml`,
  `issue-pr-triage.yml` / `scan`, and the `preflight_non_ascii.py`
  `PreToolUse` hook for the deterministic checks. This document does
  not duplicate those gates; it tells reviewers which lane each gate
  serves.
- Reframing the six principles. The principle text and the
  `*Layer: ...*` subtitles ([#75](https://github.com/tvna/claude-md/issues/75))
  are inputs to this document, not outputs.
- Folding the decision tree into the historical replay. The decision
  tree (section 4) stays in this document because it is the live rule
  used on every PR; the historical replay (formerly section 5, now
  `docs/archive/decision-tree-replay.md`) is extracted because it is
  append-only calibration evidence that does not change when section
  4 changes. The repo-local retrospective docs
  (`docs/archive/retrospective-pr-*.md`) continue to serve as the
  open-ended examples corpus that lives outside this document, and
  section 6.4 governs how those retrospectives feed back into
  instruction changes.

## 2. Vocabulary - the four ownership lanes

A rule that an agent must follow can live in exactly one of four
lanes. The lane determines who enforces it, who reads it, and how it
changes.

| Lane | Source of truth | Audience | Change mechanism |
|---|---|---|---|
| Universal text | `.apm/instructions/master.instructions.md` | Every agent in every project that imports this repository | Edit the APM source; `apm compile` regenerates `CLAUDE.md` / `AGENTS.md`; `portable-pr-policy.yml` enforces no drift |
| Harness | `scripts/*.py` + `.github/workflows/*.yml` + Claude Code hooks declared in `.claude/settings.json` | The repository itself; runs without agent involvement | Edit the script or workflow; add or update a paired test in `tests/test_<name>.py` per `docs/standards/workflow-script-quality.md` |
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
`docs/standards/workflow-script-quality.md`.

### 2.3 What "repo-local doc" means here

A repo-local doc captures everything that is true about this
repository but not true about every downstream consumer. This
includes:

- Operator runbooks for repository-specific workflows
  (`runbooks/branch-cleanup.md`, `runbooks/dependabot-automerge.md`, `runbooks/rulesets.md`).
- Standards that are repository-wide but not universal
  (`standards/issue-pr-body-standard.md`, `prd/non-ascii-defense.md`,
  `standards/workflow-script-quality.md`).
- Inventories of repository surfaces
  (`prd/security-control-inventory.md`, `standards/repo-scope.md`).
- Retrospective case studies (`archive/retrospective-pr-*.md`).
- Measurement frameworks (`standards/performance-metrics.md`).

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
it up ("Write operator-facing output -- chat responses in every mode
and plan artifacts -- in the primary project owner's native language.
If the project lacks ownership-language metadata, prepare it before
relying on this rule.").

### 2.5 Glossary

This subsection is the single source of truth for terms that recur
across `master.instructions.md`, the compiled `CLAUDE.md` and
`AGENTS.md`, the responsibility matrix in section 3, and the harness
scripts. Each entry names the term, gives a one-sentence definition,
and cites the master section subtitle and any matrix row that uses
it. `scripts/scan_design_philosophy_drift.py` reads the headings
under this subsection to verify that no required entry has been
removed.

- **safety boundary**: The layer that limits simplicity when the
  cost of being wrong is high. Used as the `*Layer: ...*` subtitle of
  master section 4 and as the P4 row label in section 3.
- **defense-in-depth**: A safety pattern that keeps a control alive
  across multiple layers (prompts, code, hooks, CI, review, operator
  procedure) so that collapsing any one layer does not remove the
  control. Stated in master section 4 ("Preserve defense-in-depth
  ..."). The section 3 P4 row records the lanes that carry it.
- **deterministic gate**: A harness rule converted to an executable
  check (a script, a workflow, a hook, or a ruleset) that replaces
  reviewer memory. Defined operationally in section 2.2. Required by
  master section 3 ("push deterministic work into hooks, pre-commit,
  and CI/CD ... build the harness first if it's missing").
- **untrusted data**: External text such as issue bodies, PR
  descriptions, review comments, CI logs, webhook payloads,
  generated reports, pasted stack traces, and external docs,
  including quoted, pasted, forwarded, or attached content inside
  any message channel. Master section 2 forbids it from overriding
  trusted instruction sources at runtime; trust is governance-gated
  provenance, not channel name.
- **repair-free merge**: A PR that lands without any reviewer, CI,
  or hook repair between PR open and merge. The retrospective
  auto-opened after each merge counts the repairs. Required by
  master section 3 ("The retrospective must review repair-free
  merge reproducibility ...").
- **PRD**: Product Requirements Document. Required by master section
  1 ("Match the document weight to the blast radius: detailed PRD
  for architectural / multi-PR work, concise spec otherwise."). This
  document (`docs/prd/agent-rules-design-philosophy.md`) is the PRD for
  the universal-text and harness boundary; downstream consumers
  write their own PRDs for their own architectural changes.
- **P1 through P6**: The six numbered principles in
  `master.instructions.md`. Each principle is identified by its
  `*Layer: <text>*` subtitle. The matrix row label after `P<n> - `
  in section 3 must equal the subtitle `<text>` after normalization
  (`&` to `and`, case-insensitive, whitespace-collapsed); see
  section 3 for the invariant.
- **hardness contour**: The shape of a universal-text rule's
  enforcement edge, expressed by hardline phrasings such as "No
  exceptions" or "every commit and PR". Diluting the contour means
  attaching wording that softens, scopes-down, or carves out the
  hardline without removing the hardline itself, so a reader cannot
  tell from the text alone which rule actually binds. Reviewer
  questions for preservation are listed in section 7.6.
- **in-line carve-out**: A clause placed directly adjacent to a
  hardline phrasing that introduces an exception, scope reduction,
  or qualification without moving to a separate sub-bullet, runbook,
  or repo-local doc. The pattern is the primary failure mode that
  dilutes a hardness contour; section 7.6 lists it as an anti-pattern
  the reviewer must catch before merge.

## 3. Responsibility matrix - six layers by four lanes

Each row is one of the six principles in `master.instructions.md`,
identified by its `*Layer: ...*` subtitle. Each column is one of the
four ownership lanes from section 2. Cells contain the concrete
artifacts that own the concern, or `(gap)` if no artifact owns it
today.

**Matrix-subtitle invariant.** The row label after `P<n> - ` must
equal the master `*Layer: <text>*` subtitle text after normalization
(`&` to `and`, case-insensitive, whitespace-collapsed). The number
of rows must equal the maximum master section number. A change to
either side requires the same PR to update the other side and to
re-run `scripts/scan_design_philosophy_drift.py`. Without this
invariant, a row label rename can imply a structural change to
`master.instructions.md` without actually performing it (see retro
[#322](https://github.com/tvna/claude-md/issues/322)).

The `Boundary risk` column records the pattern most likely to cause
the wrong lane to absorb a concern, drawn from the historical record
of merged PRs and closed sub-issues of #226.

| Layer (principle) | Universal text owns | Harness owns | Repo-local doc owns | Project-local owns | Boundary risk |
|---|---|---|---|---|---|
| P1 - goal and plan structure | Plan-mode trigger; document weight rule; verification design in the plan | `scripts/plan_language_context.py` (SessionStart hook); `tests/test_plan_language_context.py` | `docs/standards/issue-pr-body-standard.md` (body shape encodes the plan); `docs/standards/performance-metrics.md` (measurement is a verification artifact) | The consumer's plan-mode trigger discipline | Mixing plan-language responsibility with GitHub-post ASCII enforcement in one rule (corrected by [#227](https://github.com/tvna/claude-md/issues/227)) |
| P2 - input and pre-code reasoning | Untrusted-data treatment of external text (including quoted/forwarded content in any channel); runtime no-override of trusted instruction sources anchored in governance-gated provenance; fact-vs-speculation tagging; assumption enumeration; simpler-path proposal | `scripts/preflight_non_ascii.py` (PreToolUse hook against non-ASCII injection); `scripts/body_policy.py`, `scripts/title_policy.py`, `scripts/pr_body_close_keyword_gate.py` (structural shape of external-authored bodies); `scripts/scan_non_ascii.py` (advisory drift detector); `scripts/sanitize_history.py` (historical-text cleansing) | `docs/runbooks/downstream-instruction-review-checklist.md` (reviewer-facing untrusted-text checklist); `docs/prd/non-ascii-defense.md` (Layer 1-2-3 defense narrative); `docs/standards/issue-pr-body-standard.md` (Facts / Assumptions sections); `docs/runbooks/issue-triage.md` (label-driven routing) | The consumer's own incoming-text and ambiguity policy | Treating external text as authority, or letting speculation slip into universal text disguised as a fact (PR #225) |
| P3 - delivery harness around the code | Issue-first; ASCII discipline; declarative module management; auto-subscribe to PR activity; retrospective auto-open; classify each repair | `scripts/issue_link.py`, `body_policy.py`, `title_policy.py`, `pr_body_close_keyword_gate.py`, `auto_retro.py`, `scan_non_ascii.py`, `preflight_non_ascii.py`, `branch_cleanup.py`, `rulesets_apply.py`, `ruleset_drift.py`, `labels_apply.py`, `dependabot_automerge.py`, `dependabot_labels.py`, `threat_intel_triage.py`, `uv_pin.py`, `scan_apm_portability.py`; 16 paired workflows; 19 paired tests | `docs/standards/issue-pr-body-standard.md`, `docs/runbooks/issue-triage.md`, `docs/prd/non-ascii-defense.md`, `docs/runbooks/rulesets.md`, `docs/runbooks/branch-cleanup.md`, `docs/runbooks/dependabot-automerge.md`, `docs/standards/remote-environment.md`, `docs/standards/repo-scope.md`, `docs/prd/security-control-inventory.md`, `docs/archive/retrospective-pr-*.md` | The consumer's own CI provider, issue tracker, and dependency manager | Naming a specific tool (gh CLI, GitHub Actions, dependabot) inside universal text; embedding a specific PR number as an example |
| P4 - safety boundary | Minimum code; safety-bounded simplicity; defense-in-depth preservation; destructive-operation safeguards; tool-scope confinement; external-disclosure and secret-log prevention; fail-loud over silent default; debug instrumentation as attack surface | `.github/CODEOWNERS` (repo-scope binding for MCP/agent tools); `.github/workflows/*.yml` `permissions:` declarations (least-privilege per workflow); `scripts/scan_apm_portability.py` (forbids naming repo-local tools in universal text); `(lint and type gates exist in workflow-script-quality.md M8; behavioral check is reviewer judgment)` | `docs/standards/workflow-script-quality.md` (M1 to M9 must-have checklist; O1 to O7 optional enhancements); `docs/standards/repo-scope.md` (allowed-repository policy and runbook); `docs/runbooks/workflow-permissions-audit.md` (per-workflow permission matrix); `docs/prd/security-control-inventory.md` (visualization of the harness coverage); `docs/prd/privileged-operation-runbooks.md` (escalation paths) | The consumer's own language ecosystem, code style, credential manager, external-endpoint policy, and per-agent tool inventory | Embedding a stack-specific example or a concrete tool endpoint inside universal text; widening a least-privilege workflow `permissions:` block for a one-off debug |
| P5 - change scope and agent split | The measurable proposition that quality stays proportional to the scope and scale of change, observed over time; narrow change surface; cleanup limited to artifacts made obsolete by the active change | The `superpowers` skills (subagent-driven-development, dispatching-parallel-agents, requesting-code-review) own the sub-agent-vs-skill selection and the implementation/verification split; implementation skills own concrete code-editing hygiene | `docs/runbooks/agent-provenance.md` (provenance review for skills, subagents, MCP servers, and comparable extensions) | The consumer's own agent inventory and roster | Mentioning a Claude-only feature (sub-agents, skills) by literal name as universal terminology; restating sub-agent orchestration or concrete code-editing technique that the skills already own |
| P6 - handoff and communication | Native-language plan artifacts; show procedure and case studies; visualize workflow; refuse LGTM; explain trade-offs | `scripts/plan_language_context.py` (owner-language metadata recovery); `.github/owners.yaml`; `.github/CODEOWNERS` | `docs/archive/retrospective-pr-*.md` (case studies are the force-multiplier evidence); `docs/prd/security-control-inventory.md` (visualization of the harness coverage); `docs/standards/performance-metrics.md` (visualization of measurement) | The consumer's own `owners.yaml` entries | Treating "case studies" as universal content rather than as repo-local artifacts that the universal text merely *requires*; plan-language drift slipping into English despite harness injection (corrected by [#269](https://github.com/tvna/claude-md/issues/269)) |

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
runbook (`docs/standards/issue-pr-body-standard.md` tells contributors exactly
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
           docs/standards/workflow-script-quality.md. The repo-local doc lane
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
           portable-pr-policy.yml enforces the drift gate.

Q5. Is the rule a description of a past event (a retrospective, a
    repaired wording, an audit finding)?

    Yes -> Repo-local doc lane: docs/archive/retrospective-pr-<N>.md
           or a new case-study doc. Case studies are explicitly required
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

Replayed in [`docs/archive/decision-tree-replay.md`](../archive/decision-tree-replay.md). The replay is a calibration check that section 4's decision tree reproduces the historical record; it is not normative.

### 5.1 PR #577 - in-line carve-out next to a hardline phrasing

**What happened.** PR #577 (closes #548) added the clause "When the
work is a single GitHub UI-only edit ... perform that edit directly
instead of opening a sub-issue." directly under the section 3
hardline "Open a GitHub issue before any branch, commit, or PR; cite
its number in every commit and PR. No exceptions -- typos, docs,
hotfixes included." The added clause is logically already covered by
the existing rule's "any branch, commit, or PR" scope, but its
in-line placement next to "No exceptions" softens the hardness
contour without removing the hardline phrasing.

**Decision tree trace.**

- Q1: Tool-agnostic? Yes (the rule is about issue ordering, not about
  any vendor or product).
- Q2: Deterministic? No (the threshold "single GitHub UI-only edit"
  is reviewer judgment, not script-checkable).
- Q3: Agent judgment plus universal? Yes.
- Q4: Needs a repository-specific noun? No.
- **Lane (decision tree only): universal text.** The four-question
  walk does not block the PR.

**Why the contour check is needed.** Section 4's tree is a
necessary but not sufficient gate for the universal-text lane. The
PR #577 edit passes the four questions yet still dilutes the
hardness contour by attaching an in-line carve-out to a hardline
phrasing and by re-stating a clause already implied by the existing
rule's scope. Section 7.6 records the three anti-patterns the
reviewer applies on top of the decision tree to catch this dilution
before merge; the PR #577 diff fires the first two anti-patterns
("in-line carve-out next to a hardline phrasing" and "redundant
clause already implied by the existing rule's scope") and would
have produced a "request changes" outcome under that subsection.

### 5.2 Issue #833 - Section 5 scenario-block boundary

**Facts.** Issue #833 revisited the two remaining Section 5 scenario
blocks from #79: "When editing existing code" and "When your changes
create orphans." The proof-of-correctness placement concern from #79
was already resolved by #80, and the Section 5 thesis was rebuilt as
a measurable quality-scale proposition by #820.

**Judgement.** The residual scenario blocks were concrete
code-editing hygiene, not the universal workflow definition or safety
boundary. Section 5 keeps the abstract scope-control rule because it
limits the change surface for every downstream consumer. Concrete
code-editing technique belongs in implementation skills and comparable
project-local procedure, where it can adapt to the active language,
framework, and codebase.

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

- a new harness script (per `docs/standards/workflow-script-quality.md`), or
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
| Missing deterministic gate | Harness | Universal text (only if the gate enforces a new universal principle) | `docs/archive/retrospective-pr-229.md` records a body-policy preflight gap surfaced between PR open and merge; the durable fix was a new `scripts/` preflight, not a universal-text edit |
| Unclear agent instruction | Universal text | Repo-local doc (a worked example or runbook clarification) | `docs/archive/retrospective-pr-235.md` records an auto-retro skip-rule ambiguity; the durable fix was a wording tightening in the harness rule plus a clarifying note in the repo-local retrospective doc |
| External or human decision | Project-local | Repo-local doc (an escalation note describing the unresolved item) | `docs/archive/retrospective-pr-237.md` records a no-repair merge where outstanding follow-up items required human judgment; nothing landed in universal text or harness |

The mapping is a router, not a deterministic gate: it tells the
contributor which lane to draft into first. The decision tree in
section 4 then validates whether that draft lane is the correct
final destination.

"Unclear agent instruction" findings default to the runbook layer
(a worked example or a repo-local runbook clarification); promotion
into universal text requires a separate scoped sub-issue of #226
with code-owner review and must preserve the hardness contour per
[section 7.6](#76-hardness-contour-preservation) before any edit to
`.apm/instructions/master.instructions.md` is proposed.

For the orthogonal concern of spotting noise-commit and flooding
patterns on a merged PR (high commit count, low-information
subjects, repeated repair commits, force-update churn, unrelated
churn), the retrospective writer applies the procedure in
[`docs/runbooks/retrospective-noise-flooding-procedure.md`](../runbooks/retrospective-noise-flooding-procedure.md).
That procedure maps each signal into the same three-category
taxonomy used here, and keeps any deterministic follow-up as a
separate sub-issue rather than bundling it into the design-doc
phase.

Hand-authored retrospective `.md` files land under
`docs/archive/retrospective-pr-<N>.md`. The auto-retro harness
(`scripts/auto_retro.py`) only opens the GitHub issue; the durable
write to disk happens when a contributor lands the retrospective doc
in the next PR, and that PR puts the file in `docs/archive/`.

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
review surface (`docs/standards/workflow-script-quality.md` for harness PRs,
the body and title policies for every PR).

### 7.2 Deterministic gates the reviewer can rely on

Before any manual review begins, confirm the following automated
gates are green on the PR head commit:

- `portable-pr-policy.yml` confirms that `CLAUDE.md` and `AGENTS.md`
  are the verbatim output of `apm compile` for the current
  `.apm/instructions/master.instructions.md`.
- `portable-pr-policy.yml` runs `scripts/scan_apm_portability.py`
  and blocks repository-specific
  references (`#NNN` issue numbers, `docs/<name>.md` paths, script
  names, tool product names) inside universal text unless an
  explicit `portability-ack:` marker on the same line cites the
  authorizing sub-issue.
- `portable-pr-policy.yml` confirms the PR body and title follow
  `docs/standards/issue-pr-body-standard.md`.
- `issue-pr-triage.yml` / `scan` confirms no non-ASCII characters slipped
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
[section 5.1 of `docs/archive/decision-tree-replay.md`](../archive/decision-tree-replay.md#51-pr-225---repository-specific-wording-in-a-universal-sentence))
is the canonical example for this section. A reviewer running the
criteria above on that PR's pre-repair state would have observed
Q4 = yes in the diff (the wording needed a repository-specific
noun) and would have requested the demotion to a repo-local doc
before merge, instead of allowing the repair to happen between PR
open and merge. The criteria in section 7 are designed to make that
catch reproducible.

### 7.6 Hardness contour preservation

The section 4 decision tree is a necessary but not sufficient gate
for the universal-text lane. A diff that resolves to universal text
through Q1 to Q4 can still dilute the hardness contour of an
existing rule -- the shape of its enforcement edge expressed by
hardline phrasings such as "No exceptions" or "every commit and
PR". Reviewers apply the three anti-pattern questions below in
addition to (not in place of) the decision tree. If any one fires
on the diff, the outcome is "request changes" and the wording
belongs in the runbook layer or in a separate scoped sub-issue
rather than in universal text.

The PR #577 worked case in [section 5.1](#51-pr-577---in-line-carve-out-next-to-a-hardline-phrasing)
is the canonical evidence that the decision tree alone does not
catch this dilution; section 5.1 records the four-question trace
that produced a universal-text verdict and the anti-pattern hits
that should have produced a "request changes" outcome instead.

**Anti-pattern A: in-line carve-out next to a hardline phrasing.**

- Reviewer question: Does the diff place an exception, scope
  reduction, or qualification clause directly adjacent to a hardline
  phrasing ("No exceptions", "every commit and PR", "always",
  "never") without moving it to a separate sub-bullet, runbook, or
  repo-local doc?
- Outcome on fire: request changes. The carve-out belongs in a
  runbook or a repo-local doc; the hardline phrasing in universal
  text must keep its enforcement edge intact.

**Anti-pattern B: redundant clause already implied by the existing rule's scope.**

- Reviewer question: Is the new clause already covered by the
  existing rule's scope as written (for example, a clause about "a
  single GitHub UI-only edit" added to a rule that already says "any
  branch, commit, or PR")?
- Outcome on fire: request changes. A redundant clause adds reader
  load without changing the binding rule, so it dilutes the contour
  without justifying its own existence; if a clarification is
  genuinely needed, the runbook layer is the correct destination.

**Anti-pattern C: retrospective-derived wording promoted into universal text without a runbook layover.**

- Reviewer question: Did the wording originate from a retrospective
  classified as "Unclear agent instruction" and arrive in universal
  text without first landing in a runbook clarification (per
  [section 6.4](#64-retrospective-classification-to-action-lane-mapping))?
- Outcome on fire: request changes. The default destination for
  "Unclear agent instruction" findings is the runbook layer;
  promotion into universal text is a separate scoped sub-issue that
  the reviewer must see cited on the PR before approving.

Section 7.3's three lane outcomes still apply; this subsection adds
a fourth implicit outcome for universal-text edits: even when Q1
through Q4 resolve to universal text, a fire on anti-pattern A, B,
or C produces "request changes" with the redirect destination
called out in the outcome line.

## 8. Validation strategy

This document is valid only if:

- **Replay calibration.** Each of the seven closed sub-issues
  replayed in [`docs/archive/decision-tree-replay.md`](../archive/decision-tree-replay.md)
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
  `portable-pr-policy.yml` to fail. It is a repo-local doc and lives
  entirely in the repo-local lane.

If any of the four conditions starts failing, this document is the
problem, not the source it describes.

## 9. Update procedure and rollback

To update this document (add a row, add a worked example, fix a
boundary risk):

1. Open a sub-issue of [#226](https://github.com/tvna/claude-md/issues/226)
   describing the proposed change per
   `docs/standards/issue-pr-body-standard.md` (Scope / Facts / Assumptions /
   Acceptance criteria / Verification / Parent).
2. Open a single PR that edits only this document and, if the
   addition requires it, the cross-link headers in
   `docs/standards/repo-scope.md`, `docs/prd/security-control-inventory.md`,
   `docs/standards/issue-pr-body-standard.md`, `docs/prd/non-ascii-defense.md`,
   and `docs/standards/workflow-script-quality.md`.
3. Re-run the validation strategy in section 8. The replay table in
   `docs/archive/decision-tree-replay.md` must remain at 100 percent
   match; if a new closed sub-issue is added to the replay set, trace
   it explicitly in that file.
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
  repaired wording motivated #226 and is replayed in
  `docs/archive/decision-tree-replay.md` section 5.1.
- [#577](https://github.com/tvna/claude-md/pull/577) - the PR whose
  in-line carve-out under a hardline phrasing motivated section 5.1
  of this document and the section 7.6 anti-pattern checklist.
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
  closed sub-issues replayed in `docs/archive/decision-tree-replay.md`.
- [#79](https://github.com/tvna/claude-md/issues/79) - currently
  open structural sub-issue; out of scope for this document.
- `.apm/instructions/master.instructions.md` - the universal text
  this document describes; not modified by this document.
- `docs/standards/repo-scope.md` - content-based prohibition of tool-specific
  configuration; theoretical grounding for the Q1 disqualifier.
- `docs/prd/security-control-inventory.md` - five-column evidence table
  precedent; harness-lane coverage source.
- `docs/standards/issue-pr-body-standard.md` - body shape standard; carries
  the Facts / Assumptions discipline from P2.
- `docs/prd/non-ascii-defense.md` - the three-layer ASCII discipline
  enforced by the harness for P3 GitHub posts.
- `docs/standards/workflow-script-quality.md` - the must-have checklist for
  harness scripts; the closest thing this repo has to a P4 quality
  gate beyond reviewer judgment.
- `docs/archive/decision-tree-replay.md` - the historical replay
  (formerly section 5 of this document) showing that the decision
  tree in section 4 reproduces this repository's past lane
  assignments.
- `docs/archive/retrospective-pr-*.md` - case-study lane precedent for P6;
  individual retrospectives (PR #229, #235, #237) supply the field
  examples cited in section 6.4.
- `docs/runbooks/retrospective-noise-flooding-procedure.md` - the Phase 8(D-3)
  deliverable for #315 (parent #63); applied by retrospective
  writers alongside the section 6.4 lane mapping to spot
  noise-commit and flooding patterns and to decide whether a
  deterministic follow-up gate is warranted.
- `scripts/auto_retro.py` - retrospective harness whose
  three-category taxonomy (missing deterministic gate, unclear
  agent instruction, external or human decision) drives the
  section 6.4 mapping.
- `scripts/scan_apm_portability.py` - the portability gate cited by
  section 7.2 and section 7.4; rejects repository-specific
  references inside universal text and recognizes the
  `portability-ack:` marker.
