---
name: session-handoff
description: Produces a paste-ready handoff prompt so the next agent session resumes the work cleanly - a deliberate alternative to trusting the harness's automatic context compaction. Use when context is running low and a clean restart beats compaction, when unfinished work must carry over, or when repository gates limit what the current session can change.
---

# Session Handoff

Turns in-flight work into a self-contained prompt the next session can act on
without re-deriving context.

## When to use

Reach for a handoff instead of relying on the harness's automatic compaction:
when context is filling, write a clean handoff and start a fresh session rather
than let compaction silently lose fidelity. Also hand off when repository gates or
session-scoped limits block the change here - reset and resume in a new session.

## Steps

1. Context: the issue, the existing branch (do not create a new one), and what it closes.
2. Background: what remains or failed, when, and the observable symptom - 2-4 sentences.
3. Files to read before implementing, in read order, each with a one-line role; the next session reads them fully first.
4. Implementation: the exact, minimum-sufficient change and why. Name options A/B/C with a recommendation when several exist. Do not invite extra files, hooks, or abstractions.
5. Verification: the commands to run and the expected result.
6. PR creation: read the PR template; suggest a Conventional Commit title.
7. Acceptance criteria: a deterministic checklist, including CI green.

Read [the handoff template](references/handoff-template.md) for exact section order and an example.

## Output

One prompt with headings **Context**, **Background**, **Files to read**, **Implementation**, **Verification**, **PR creation**, **Acceptance criteria**.

Do not use fenced code blocks; use 4-space-indented blocks for commands so the prompt pastes into a chat without breaking. Write in the active contributor's language (the person driving the current session, not a fixed project owner) unless a repository rule requires another for outward-facing artifacts.
