# Retrospective -- PR #229 Layer Responsibility Boundary Repair Loops

This document is the retrospective for [#230](https://github.com/tvna/claude-md/issues/230) -- the post-merge review of PR [#229](https://github.com/tvna/claude-md/pull/229), which closed issue [#227](https://github.com/tvna/claude-md/issues/227) ("docs(agent-rules): correct layer responsibility boundaries"). The retrospective framework lives in `.apm/instructions/master.instructions.md` §3: classify each pre-merge repair, identify the earliest deterministic gate that should have prevented it, and state the no-repair reproduction path for the next similar PR.

## Scope

- Target PR: [#229](https://github.com/tvna/claude-md/pull/229), merged as commit `6a403ad` on 2026-05-24.
- Requested issue: [#227](https://github.com/tvna/claude-md/issues/227) -- concrete responsibility-boundary corrections to `.apm/instructions/master.instructions.md` (compiled into `CLAUDE.md` / `AGENTS.md`).
- Out of scope: the substance of the merged layer-responsibility changes themselves -- those were accepted.

## Repair history

PR #229 landed via four commits on branch `codex/bounded-layer-responsibilities`. Three repair loops are observable from the diff between the initial draft and the final merge state:

| # | Repair | What the reviewer caught |
|---|---|---|
| A | The initial implementation added a standalone DDD / "bounded-context" meta-rule to the universal instructions. Issue #227 had explicitly forbidden it ("This issue is not asking to add a DDD explanation ... Do not add a standalone DDD or bounded-context meta-rule"). | Semantic mismatch with issue scope. |
| B | Compiled `CLAUDE.md` / `AGENTS.md` referenced repo-local artifacts (`scripts/plan_language_context.py`, `scripts/preflight_non_ascii.py`, `.github/owners.yaml`, `CODEOWNERS`, `mcp__github__*`). These artifacts do not exist in downstream projects that consume the compiled rules standalone. | Portability regression. |
| C | The owner-language requirement was expressed in two places (one in §1 for plan-file language, one in §6 for chat-response language) before being deduplicated under §6. | Duplication. |

## Classification

Per the `.apm/instructions/master.instructions.md` §3 taxonomy ("missing deterministic gate / unclear agent instruction / external or human decision"):

| Repair | Classification | Reasoning |
|---|---|---|
| A | unclear agent instruction | Issue #227 contained the negative constraint in prose. The implementer did not weigh the "Do not add ..." line as a hard veto. No deterministic gate can semantically detect "this PR added meta-language the issue forbade"; the gap is at the instruction-interpretation layer, not the harness layer. |
| B | missing deterministic gate | The compile pipeline produces artifacts intended for standalone downstream consumption, but no gate enforced "no repo-local references in compiled rules." `verify-apm-drift.yml` only verified source-output equivalence, not portability. The companion PR closes that gap. |
| C | missing deterministic gate (deferred) | A near-duplicate-bullet check could in principle catch this. Practical implementations (shingle similarity, embedding distance) carry a false-positive rate that exceeds the historical hit rate for repair C. Recorded as a follow-up candidate; not implemented here. |

## Earliest prevention point

- **Repair A**: Plan-mode review must extract the issue's negative constraints ("Do not ...", "not asking to ...") and treat them as test cases for the proposed diff. The earliest point is the Plan phase, before any source edit. A follow-up issue can consider an Issue Form "Non-goals / Out of scope" section to surface negative constraints structurally; the gate itself remains a review checklist item, not an automated check.
- **Repair B**: `scripts/scan_apm_portability.py` (introduced alongside this document) plus `.github/workflows/verify-apm-portability.yml`. The gate runs on every PR touching `.apm/**`, `CLAUDE.md`, or `AGENTS.md`. The earliest point is the first `apm compile` after editing the source: the developer can run the scanner locally and catch leaks before pushing.
- **Repair C**: Reviewer attention remains the prevention point until a low-false-positive automated dedup is designed. The follow-up issue should weigh implementation effort against historical incidence rate before committing.

## No-repair reproduction path

For the next PR that follows the same shape as #229 (agent-rule responsibility-boundary correction), the path to a repair-free merge is:

1. **Plan phase**: enumerate the requesting issue's "Do not ..." / "not asking to ..." lines as explicit non-goals in the plan. Each non-goal becomes a self-check on the proposed diff.
2. **Edit phase**: change only `.apm/instructions/master.instructions.md`. Do not introduce new meta-vocabulary unless the issue explicitly requested it.
3. **Compile phase**: run `uv run --with "apm-cli==0.12.1" --exclude-newer "14 days" apm compile`.
4. **Local verify phase**: run `python3 scripts/scan_apm_portability.py verify --path .apm/instructions/master.instructions.md --path CLAUDE.md --path AGENTS.md`. Fix any hit by either rewording the source line to be portable or, if a normative downstream reference is required, append `<!-- portability-ack -->` to the line.
5. **Test phase**: run `uv run pytest`.
6. **PR phase**: open the PR; both `verify-apm-drift.yml` (source-output equivalence) and `verify-apm-portability.yml` (no repo-local refs) run automatically. CI green = ready for review.

## Gates introduced alongside this retrospective

| Gate | Introduced here | Reasoning |
|---|---|---|
| Portability scanner (`scan_apm_portability.py` + `verify-apm-portability.yml`) | yes | Repair B is purely structural; a deterministic literal-token scan with an ack-marker escape hatch closes it without semantic ambiguity. |
| Issue Form "Non-goals" section | no -- follow-up issue | Repair A's prevention point is a review/Plan-phase practice, not a check the harness can run. A template hint is a separate proposal. |
| Near-duplicate-bullet check | no -- follow-up issue | Repair C's automation requires false-positive control that has not been designed yet. |

## References

- Issue: [#230](https://github.com/tvna/claude-md/issues/230) (this retrospective).
- PR: [#229](https://github.com/tvna/claude-md/pull/229) (merge commit `6a403ad`).
- Closed issue: [#227](https://github.com/tvna/claude-md/issues/227).
- Parent tracker: [#226](https://github.com/tvna/claude-md/issues/226).
- Framework: `.apm/instructions/master.instructions.md` §3, codified in commit `daa5179` (#225).
