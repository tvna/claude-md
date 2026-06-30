---
name: using-clairvoyance
description: Routes an agent-to-human handoff. Use when starting a session or after compaction to dispatch owner choices, review readiness, architecture trade-offs, and unclear decisions.
---

# Using Clairvoyance

**BOOTSTRAP SKILL:** choose one handoff skill.

## Rule

Before handoff, select one plugin-qualified Clairvoyance skill.

SessionStart contributor language (the active contributor's, not a fixed owner's) is authoritative; if missing, use portable question handoff.

Portable question handoff: AskUserQuestion if available; else print `AskUserQuestion:` plus the same question and 1-3 choices.

Depth after routing — branch by stakes:

- Reversible, low-risk, one clear call? -> compact handoff: **Verdict** + **Next Move**.
- Irreversible, high-risk, contested, or detail requested? -> full handoff: all routed-skill headings.

## Trigger

Route:

- Human owner decision, blocker, or prepared options outside PR readiness -> `clairvoyance:clairvoyance`.
- PR, commit, branch, review verdict, or "should this merge?" -> `clairvoyance:review-verdict`.
- Architecture judgment, system trade-off, or failure-mode analysis -> `clairvoyance:architecture-tradeoff`.
- A single decision in the moment: LGTM requests, missing subject, noisy input, sycophancy pressure, or a decision without architecture understanding -> `clairvoyance:decision-coaching`.
- A request to reflect or do a retrospective on one's own recurring patterns -> `clairvoyance:adaptive-coaching`, which delivers a reflection quiz when enough signal has accumulated.
- High-blast-radius, irreversible, or compliance-violating instruction (the human harness) -> `clairvoyance:human-harness`.

The two coaching skills split by intent: a live decision goes to `decision-coaching`; an explicit reflection/retrospective request goes to `adaptive-coaching`. A reflection quiz is never pushed — it fires only on the person's own request.

Do not route implementation, progress, tests, typos, or refactors unless they become a decision handoff or carry high-blast-radius or compliance risk, which routes to `human-harness`. Treat evidence gaps as risks or unknowns.

## Priority

Use other needed skills first; use Clairvoyance for the human handoff. When unsure, prefer the narrowest matching scene; if none applies, continue normally. If a human-only answer blocks the handoff, use portable question handoff with prepared choices.

## Examples

- Merge: `review-verdict` -> **Verdict**, **Findings**, **Evidence**, **Risks**, **Next Move**.
- Architecture: `architecture-tradeoff` -> **Verdict**, **Options**, **Future Story**, **Premortem**, **Next Move**.
- Owner decision: `clairvoyance` -> **Verdict**, **Evidence**, **Options**, **Risks**, **Reversibility**, **Next Move**.
- LGTM/unclear subject: `decision-coaching` -> portable question handoff.
- Reflection request: `adaptive-coaching` -> **Classification**, **Capability Gap**, **Evidence**, **Quiz**, **Next Move**.
- Risky order: `human-harness` -> **Stop**, **Blast Radius**, **Premortem**, **Confirm**, **Next Move**.
