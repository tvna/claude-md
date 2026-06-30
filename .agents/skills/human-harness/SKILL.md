---
name: human-harness
description: Prevents human error before a major incident by pausing a risky instruction to confirm intent. Use when an instruction is high-blast-radius, irreversible, or breaks a governed rule or safety gate.
---

# Human Harness

The human harness pauses a risky instruction and makes the human confirm intent before it executes, catching error before it lands.

**UTILITY SKILL:** invoked as `clairvoyance:human-harness` by `using-clairvoyance` for high-blast-radius or non-compliant instructions.

## Steps

1. Do not execute yet. Name what makes it high-blast-radius or non-compliant: the irreversible operation, governed rule, or safety gate.
2. Measure blast radius and reversibility: what it touches, who it affects, whether it can be undone and at what cost.
3. Research the repository to settle your own questions first; ask the human only what evidence cannot.
4. Hand a decision-ready choice, not a raw question: prove the outcomes, then offer reversible named options with a recommendation and trade-off. No rubber-stamp.
5. Run a premortem: assume it ran and was regretted, then name the failure and its earliest warning signal.
6. For a compliance conflict, judge whether the rule is overridable: an overridable risk may proceed on a recorded override; a mandatory safety gate is not waivable - route to a safer path or refuse. When the class is unclear, read [compliance](references/compliance.md).
7. Stay non-shaming; for an overridable risk the human keeps authority to proceed after acknowledging it.
8. Use portable question handoff: AskUserQuestion when available, else `AskUserQuestion:` text with the same choices.
9. Write in the active contributor's language (the person driving the current session, not a fixed project owner) unless a repository rule requires another for outward-facing artifacts.

## Output

Use these headings. When the handoff format is unclear, read [a worked example](references/example.md).

- **Stop:** what the agent is holding back, and why.
- **Blast Radius:** affected objects, canonical URLs, reversibility cost.
- **Compliance:** the rule or gate and whether it is overridable, or "None".
- **Premortem:** the regret scenario and its earliest signal.
- **Safer Path:** a prepared, proven, reversible named option.
- **Confirm:** the human restates the irreversible outcome (no bare LGTM) and the recommended answer.
- **Next Move:** what happens per answer.

Pattern: **Stop** -> **Blast Radius** -> **Premortem** -> **Confirm** -> **Next Move**. Add Compliance and Safer Path when relevant.
