---
name: clairvoyance
description: Prepares an evidence-backed owner decision. Use when an agent is blocked by a human-owned choice and must present a prepared decision, approval, deferral, rollback, or 2-3 concrete options with evidence.
---

# Clairvoyance

Clairvoyance turns a blocker or owner decision into an evidence-backed handoff a human can inspect, trust, and safely disagree with.

**UTILITY SKILL:** invoked as `clairvoyance:clairvoyance` by `using-clairvoyance` for owner decisions and blockers.

## Steps

1. Classify the handoff: owner decision, blocked state, approval, deferral, sequencing, or rollback.
2. Separate facts, assumptions, speculation, and unknowns.
3. Gather evidence: canonical URLs, local files, tests, command output, screenshots, logs, or observed behavior.
4. State what is blocked or what the human must decide.
5. Prepare named options when the human must decide. Prefer 2-3 reversible choices.
6. Recommend one option and explain why.
7. State risks, reversibility, missing proof, and the next move.
8. If only the human can unblock the decision, use portable question handoff: AskUserQuestion when available, otherwise `AskUserQuestion:` text with the same 1-3 choices.
9. Write in the active contributor's language (the person driving the current session, not a fixed project owner) unless a repository rule requires another language for outward-facing artifacts.

## References

Read [decision handoffs](references/decision-handoff.md) for owner choices, blockers, and human-only decisions, or a [worked example](references/example.md).

## Output

A full handoff uses every heading:

- **Verdict:** the recommendation in one sentence.
- **Evidence:** what proves or limits the recommendation.
- **System Context:** blocked surface, ownership boundary, and affected workflow.
- **Options:** named choices with trade-offs when a decision is required.
- **Risks:** known failure modes and missing proof.
- **Reversibility:** how hard the chosen option is to undo.
- **Next Move:** the concrete action the human can approve, reject, or modify.
- **Open Questions:** blockers that remain after portable question handoff.

Pattern: **Verdict** -> **Evidence** -> **Options** -> **Risks** -> **Next Move**. Expand context or open questions only for uncertainty, risk, or human request.
