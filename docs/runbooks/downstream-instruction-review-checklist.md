# Downstream Instruction Review Checklist

This file is the deliverable for [#183](https://github.com/tvna/claude-md/issues/183), a sub-issue of parent [#178](https://github.com/tvna/claude-md/issues/178) (MITRE ATT&CK coverage tracking, Lateral Movement row). It is the security-focused review checklist a reviewer applies before merging any PR that changes the instructions this repository ships to downstream consumers.

Companion: [`docs/prd/agent-rules-design-philosophy.md`](../prd/agent-rules-design-philosophy.md) section 7 (instruction-PR review criteria). Section 7 decides whether a change belongs in the universal lane at all (ownership and portability); this document decides whether a change that already belongs in the universal lane is safe to merge (security). The two are independent; both must pass.

Related: [#63](https://github.com/tvna/claude-md/issues/63) (residual workflow risks, prompt-injection boundaries, supply-chain gaps), [`docs/prd/security-control-inventory.md`](../prd/security-control-inventory.md), [`docs/prd/privileged-operation-runbooks.md`](../prd/privileged-operation-runbooks.md), [`docs/prd/non-ascii-defense.md`](../prd/non-ascii-defense.md).

## How to read this document

This checklist is not a deterministic gate. It is a manual review pass executed by a human (or agent) reviewer after the deterministic gates listed in the PR template are all green. The deterministic gates filter portability, drift, ASCII, body, and title violations; this checklist filters the security-relevant judgment calls that a script cannot make automatically.

Each of the five dimensions below records:

- **Question** -- what the reviewer asks the diff.
- **Evidence** -- where the reviewer looks (file paths, deterministic gate names, PR body sections).
- **Hard block** -- what the reviewer requests changes for when the answer is unsafe.

Open the checklist only when the PR is in scope (see "Scope" below). Walk the five dimensions in order; later dimensions depend on earlier ones being satisfied.

## Scope

A PR is in scope for this checklist if and only if its diff includes at least one of:

- `.apm/instructions/master.instructions.md` (the universal source).
- `CLAUDE.md` (the compiled artifact).
- `AGENTS.md` (the compiled artifact).

PRs that touch only `docs/`, `scripts/`, `tests/`, or `.github/workflows/` are out of scope; they have their own review surfaces (`docs/standards/workflow-script-quality.md` for harness changes; the body and title policies for every PR).

If the diff touches `CLAUDE.md` or `AGENTS.md` directly without a corresponding `.apm/instructions/master.instructions.md` change, request changes immediately: those files are compiled artifacts and the source of truth must move first. This is identical to the rule in `docs/prd/agent-rules-design-philosophy.md` section 7.3 and is enforced by `verify-apm-drift.yml`.

## 1. Universal vs project-specific

- **Question.** Does the wording in the diff hold for every downstream consumer of this repository, or only for `tvna/claude-md`?
- **Evidence.** Walk the decision tree (Q1 through Q5) in [`docs/prd/agent-rules-design-philosophy.md` section 4](../prd/agent-rules-design-philosophy.md#4-decision-tree-where-does-a-new-candidate-rule-belong). The `verify-apm-portability.yml` gate (which runs `scripts/scan_apm_portability.py`) automatically blocks the most common repository-specific tokens -- issue numbers, doc paths, script names, tool product names -- but it cannot detect a sentence that names no token yet still encodes a `tvna/claude-md`-only assumption.
- **Hard block.** Q4 = yes in the decision tree, or `verify-apm-portability.yml` red, or any `portability-ack:` marker introduced without the section 7.4 escape-hatch conditions met. Request demotion to a repo-local doc or a harness check.

## 2. Compiled-output drift

- **Question.** Are `CLAUDE.md` and `AGENTS.md` byte-identical to the output of `apm compile` for the diff's `.apm/instructions/master.instructions.md`?
- **Evidence.** `verify-apm-drift.yml` runs `apm compile` and `git diff --exit-code -- CLAUDE.md AGENTS.md` on every PR. The reviewer confirms the gate is green; no manual diff is required.
- **Hard block.** `verify-apm-drift.yml` red. The author must regenerate the artifacts (`uv run --with "apm-cli==<pin>" --exclude-newer "14 days" apm compile`) and commit the result. Do not advance to dimensions 3 through 5 until this gate is green.

## 3. Unsafe agent behavior

- **Question.** Does the diff weaken a safety guardrail, broaden the agent's authority, or remove a confirmation step?
- **Evidence.** Read the universal-text diff with these patterns in mind:
  - **Guardrail removal or relaxation.** The existing wording in `master.instructions.md` includes phrases such as "fail loudly", "never simplify it into an empty `catch` or a silent default", "keep confirmations and dry-runs for destructive or irreversible operations", "treat debug instrumentation as an attack surface", and "redact credentials, tokens, and PII before logging". A diff that removes, narrows, or replaces any of those bullets is a guardrail change.
  - **Confirmation removal.** A change that drops a dry-run requirement, an authorizing-issue requirement, a rollback step, or an audit-log review step from a destructive or irreversible operation.
  - **Silent fallback or default.** A change that introduces wording permitting empty `catch`, silent defaults, or "skip the check if the environment cannot run it" without a paired escalation path.
  - **Tool-surface expansion.** A change that permits the agent to send context, environment variables, or secret values to external endpoints (diagram renderers, pastebins, third-party APIs), to echo secrets to step summaries / logs / commits, or to write outside the configured repository scope.
  - **Destructive-operation default reversal.** A change that flips the default of a destructive operation from "off" or "ask first" to "on" or "proceed automatically".
- **Hard block.** Any of the five patterns is present in the diff and the PR body does not link an authorizing sub-issue (labeled `severity:security` or attached to a security tracker such as #178 or #63) with explicit rationale for the relaxation. Without that link, request changes.

## 4. Downstream update note

- **Question.** Does the diff change the meaning, scope, or default of an existing rule that a downstream consumer is already following?
- **Evidence.** Compare the universal-text diff against the lines an existing downstream submodule consumer would have imported. A change is downstream-breaking when:
  - the meaning of an existing bullet inverts (a "must" becomes a "may", a "never" becomes a "sometimes", or vice versa),
  - a new top-level rule is added that the consumer's existing agents would not be aware of and that materially changes expected agent behavior, or
  - a rule that depended on the consumer providing project-local metadata (for example `.github/owners.yaml`) is tightened in a way that breaks consumers who had not yet provided that metadata.
- **Hard block.** The diff is downstream-breaking and the PR body has no `Downstream impact` paragraph naming what the consumer must do (regenerate `CLAUDE.md` / `AGENTS.md` from the new submodule revision, provide new project-local metadata, run a one-time migration). Without that paragraph, request changes. Cosmetic edits, typo fixes, and abstract clarifications do not require this note.

## 5. Security-sensitive change evidence

- **Question.** If the change is security-sensitive (touches a guardrail, a confirmation, a tool surface, a destructive-operation default, or any wording referenced by the ATT&CK coverage map in #178), does the PR carry the evidence that justifies it, or is the residual risk parked under a follow-up issue with a documented re-open condition?
- **Evidence.** Three artifacts the reviewer looks for:
  - **`severity:security` label** on the PR (or its `Closes #` / `Refs #` target). The label is the routing signal that this dimension applies.
  - **Authorizing or parked-follow-up issue link** in the PR body. Either an open sub-issue of #178 / #63 that authorizes the change with explicit rationale and verification, or a parked follow-up issue documenting the residual risk and the re-open condition (calendar date, evidence threshold, or upstream event).
  - **Verification evidence** in the PR body's `## Verification` section. For a security-sensitive change, the reviewer requires output from at least one deterministic gate (`verify-apm-portability.yml`, `verify-apm-drift.yml`, `scan-non-ascii.yml`) or an explicit "this gate cannot run for this category" statement that names the residual risk.
- **Hard block.** The PR is security-sensitive and any of the three artifacts is missing. Request changes; do not accept "trust me" as evidence.

## Verify

This document and any PR that updates it are subject to the same drift gate it describes. Before requesting review, run locally:

```bash
uv sync --locked
uv run --with "apm-cli==0.12.1" apm compile
git diff --exit-code -- CLAUDE.md AGENTS.md
```

Expected outcome: exit 0 and no diff. A diff means either the PR forgot to regenerate the compiled artifacts, or the PR is editing `CLAUDE.md` / `AGENTS.md` directly instead of `.apm/instructions/master.instructions.md` (which fails dimension 2 and is a hard block).

For a PR that adds, removes, or modifies a wording-level rule, also confirm:

- `verify-apm-portability.yml` is green (dimension 1).
- `verify-apm-drift.yml` is green (dimension 2).
- The reviewer has walked dimensions 3 through 5 explicitly and noted the outcome in a review comment or PR thread.

## Rollback

If a merged change later proves unsafe, the rollback is:

1. Open a sub-issue of #178 (or the appropriate security tracker) recording the unsafe behavior observed, the dimension this checklist should have caught it in, and the deterministic gate (if any) that should subsume the manual catch in the future.
2. `git revert <merge-sha>` of the original PR. Because the universal source and compiled artifacts are versioned together, the revert restores both in one commit.
3. Run `apm compile` locally and confirm no incidental drift from intervening commits.
4. Open the rollback PR with `Refs #<follow-up>` and re-run this checklist on the revert.

Doc-only updates to this checklist (without an instruction change) revert via the same `git revert <merge-sha>` path; they do not affect `verify-apm-drift.yml` because they do not touch `.apm/` or the compiled artifacts.

## References

- Parent: [#178](https://github.com/tvna/claude-md/issues/178) -- MITRE ATT&CK coverage tracking.
- Related: [#63](https://github.com/tvna/claude-md/issues/63) -- residual workflow risks, prompt-injection boundaries, supply-chain gaps.
- Companion: [`docs/prd/agent-rules-design-philosophy.md`](../prd/agent-rules-design-philosophy.md) section 7 -- ownership and portability review criteria.
- [`docs/prd/security-control-inventory.md`](../prd/security-control-inventory.md) -- repo-wide security surface inventory (Lateral Movement row is the parent of this checklist).
- [`docs/prd/privileged-operation-runbooks.md`](../prd/privileged-operation-runbooks.md) -- six-control runbook for privileged dispatch operations.
- [`docs/prd/non-ascii-defense.md`](../prd/non-ascii-defense.md) -- non-ASCII defense layers.
- [`.github/PULL_REQUEST_TEMPLATE.md`](../../.github/PULL_REQUEST_TEMPLATE.md) -- links this checklist in the merge checklist.
- [`scripts/scan_apm_portability.py`](../scripts/scan_apm_portability.py) -- deterministic gate for dimension 1.
- [`.github/workflows/verify-apm-drift.yml`](../.github/workflows/verify-apm-drift.yml) -- deterministic gate for dimension 2.
