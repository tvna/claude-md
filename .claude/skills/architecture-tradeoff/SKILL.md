---
name: architecture-tradeoff
description: Decides a system-level architecture trade-off. Use when a human asks to judge between implementation options, ownership boundaries, dependency shapes, data-flow choices, or failure-mode trade-offs.
---

# Architecture Trade-Off

Architecture trade-offs turn system context into a decision a human can inspect.

**UTILITY SKILL:** invoked as `clairvoyance:architecture-tradeoff` by `using-clairvoyance` for system-level choices.

## Steps

1. Name the decision and competing options.
2. Separate facts, assumptions, speculation, and unknowns.
3. Map current architecture, ownership boundary, dependencies, data flow, invariants, and failure modes.
4. Compare cost, safety, operational impact, reversibility, and time-to-value.
5. Describe the 1-2 step future story the decision opens or closes.
6. Run a premortem: assume the recommended option failed in 3-6 months, then name likely causes and early warning signals.
7. Recommend the option that preserves important invariants with the smallest sufficient change.
8. State what proof would change the recommendation.
9. If only the human can answer a blocking architecture choice, use portable question handoff: AskUserQuestion when available, otherwise `AskUserQuestion:` text with the same 1-3 choices; otherwise list it as a risk or unknown.
10. Write in the active contributor's language (the person driving the current session, not a fixed project owner) unless a repository rule requires another language for outward-facing artifacts.

## Output

Use these headings:

- **Verdict:** the recommended option in one sentence.
- **Evidence:** proof and limits of the recommendation.
- **System Context:** architecture boundary, dependencies, contracts, and data flow.
- **Options:** named choices with trade-offs.
- **Future Story:** medium-term consequences, second-order effects, and imagination-expanding possibilities.
- **Premortem:** likely failure causes, early warning signals, and what would make the decision safer.
- **Risks:** failure modes, missing proof, and operational concerns.
- **Reversibility:** rollback path and cost.
- **Next Move:** the concrete action the human can approve, reject, or modify.

Pattern: **Verdict** -> **Evidence** -> **Options** -> **Future Story** -> **Premortem** -> **Next Move**. Expand detail only when it changes the call.

## Example

See a [worked trade-off](references/example.md).
