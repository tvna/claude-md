---
name: review-verdict
description: Produces an evidence-backed readiness verdict for changed code. Use when a human asks whether a PR, commit, branch, working tree, or merge candidate is ready, safe to land, or needs fixes first.
---

# Review Verdict

Review verdicts turn changed code into an evidence-backed readiness call.

**UTILITY SKILL:** invoked as `clairvoyance:review-verdict` by `using-clairvoyance` for review and merge readiness.

## Steps

1. State the verdict: Ready, Not Ready, or Needs Human Decision. A **Ready** call requires having examined the actual change; given only a description and not the diff/PR, state that evidence limit plainly and keep the response proportional to the change as described — neither rubber-stamp Ready nor invent risks you cannot see.
2. Separate findings, facts, assumptions, speculation, and unknowns.
3. Trace changed surfaces to entry points, callers/callees, tests, dependency contracts, and user-facing behavior.
4. Cite evidence from canonical URLs, files, tests, command output, logs, or observed behavior.
5. Recommend merge, fix first, investigate, defer, or close.
6. State residual risk, missing proof, rollback, and the next move.
7. If only the human can answer a blocking readiness question, use portable question handoff: AskUserQuestion when available, otherwise `AskUserQuestion:` text with the same 1-3 choices; otherwise list missing proof as risk.
8. Write in the active contributor's language (the person driving the current session, not a fixed project owner) unless a repository rule requires another language for outward-facing artifacts.

## Output

Use these headings:

- **Verdict:** the readiness call in one sentence.
- **Findings:** issues ordered by severity, or "None found" with reviewed scope.
- **Evidence:** proof and limits of the review.
- **System Context:** entry points, contracts, data flow, and user impact.
- **Risks:** missing tests, concurrency, rollout, or operational concerns.
- **Reversibility:** rollback path and cost.
- **Next Move:** the concrete action the human can approve, reject, or modify.

Pattern: **Verdict** -> **Findings** -> **Evidence** -> **System Context** -> **Risks** -> **Next Move**. Never issue a diff-only verdict.

## Example

See a [worked review verdict](references/example.md).
