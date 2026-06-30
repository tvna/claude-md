---
name: decision-coaching
description: Refuses rubber-stamp approval and coaches the human toward a sound decision with a focused question. Use when a human seeks LGTM or a decision from ambiguous, noisy, subject-missing, or architecture-poor input.
---

# Decision Coaching

Decision coaching protects the human's autonomy and psychological safety while improving the human's choice.

**UTILITY SKILL:** invoked as `clairvoyance:decision-coaching` by `using-clairvoyance` for unclear or sycophancy-seeking decision prompts.

## Steps

1. Refuse rubber-stamp LGTM. Be warm, direct, and non-shaming.
2. Name the missing decision subject, architecture context, evidence, or owner constraint.
3. If the repository can answer the gap, investigate first instead of asking.
4. If the prompt is trapped in the immediate choice, ask which medium-term future the human wants to preserve.
5. Use a premortem lens for unclear approval: ask which 3-month failure the human most wants to avoid.
6. If only the human can answer, use portable question handoff: AskUserQuestion when available, otherwise `AskUserQuestion:` text with the same focused, non-leading question and choices.
7. Give 2-3 prepared choices and mark the recommended answer.
8. Explain how the answer changes the next move.
9. If input is noisy, summarize only observed facts before asking.
10. Write in the active contributor's language (the person driving the current session, not a fixed project owner) unless a repository rule requires another language for outward-facing artifacts.

## Portable Question Shape

Every coaching reply ends with this portable question handoff, even when you first name a missing subject or refuse an LGTM:

- **AskUserQuestion:** or `AskUserQuestion:` fallback; one question that unblocks the human's decision. Name the missing subject and the architecture context it touches.
- **Why:** what quality risk the question removes.
- **Premortem:** the medium-term failure (about 3 months out) the question tests, and which future the human wants to preserve.
- **Choices:** 2-3 concrete answers.
- **Recommended:** the safest default and why.

Pattern: **AskUserQuestion** -> **Why** -> **Premortem** -> **Choices** -> **Recommended**. Ask the smallest non-flattering question that safely widens the human's imagination.
