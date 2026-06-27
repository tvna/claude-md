# Instruction-to-skill extraction

## Scope

Covers the audit that classifies each bullet or paragraph of
`.apm/instructions/master.instructions.md` as a constraint/fact (stays in the
universal text) or a procedural workflow (moves to a skill), and the procedure
to perform such an extraction when one is found. Reach for this whenever a
contributor proposes adding step-by-step how-to content to the universal
instructions, or audits the existing instructions for procedural content that
should live on demand instead of in the always-loaded base context. It does not
restate the four-lane placement decision tree itself, which lives in the
design-philosophy PRD; this runbook is the concrete extraction sequencing that
the PRD points at.

## Why

The compiled `CLAUDE.md` and `AGENTS.md` load on every session, so every line in
them is base-context cost. A procedural how-to sequence is invoked only for one
specific task, so it belongs in `.claude/skills/` (and the mirrored
`.agents/skills/`), which Claude Code and comparable agents load on demand.
Keeping the universal text to constraints plus one-line skill references holds
the always-loaded surface small while the procedures stay callable.

## Why not

Do not move a constraint or fact into a skill. A rule that must hold on every
task (a safety boundary, a commit convention, the issue-first ordering) is not a
procedure; demoting it to an on-demand skill would mean it is no longer always
loaded. Classify with the design-philosophy decision tree before moving
anything: a skill name is tool-specific, so the tree's Q1 disqualifier routes
the procedure into the project-local/skill lane while the universal text keeps
only an abstract reference to it. Section 5.2 of that PRD records the precedent
that concrete technique belongs in skills, and the P5 boundary-risk row warns
against restating skill-owned procedure inside the universal text.

## Procedure

Audit (the #1871 sweep):

1. Read every bullet in `.apm/instructions/master.instructions.md`.
2. For each bullet ask: is this an always-apply rule (constraint/fact), or a
   step-by-step how-to for one specific task (procedure)?
3. A bullet that already names a skill by abstract reference (for example "the
   brainstorming and writing-plans skills") is a constraint that points at an
   already-extracted procedure; it stays in the universal text.
4. Record the classification. A bullet classified as a procedure is an
   extraction candidate; a bullet classified as a constraint stays.

Extraction (only when step 4 finds a procedure):

1. Add the procedure as a packaged skill that `apm install` deploys into both
   `.agents/skills/<name>/SKILL.md` and `.claude/skills/<name>/SKILL.md`. The
   two trees are byte-identical by contract
   (`tests/test_superpowers_apm_install.py`), so never hand-author a file into
   one tree only.
2. Replace the procedural prose in `.apm/instructions/master.instructions.md`
   with a one-line abstract reference to the skill by name.
3. Run `apm compile` to regenerate `CLAUDE.md` and `AGENTS.md`.
4. Re-run the portability scan on the three instruction files and confirm the
   only diff is the intended source edit.
5. Add a `## Text delta` section to the PR body; it is required whenever the
   instruction text changes.

## Verification

Audit-only outcome (no procedure found, as in the #1871 sweep):

- command: `python3 scripts/scan_apm_portability.py verify --path .apm/instructions/master.instructions.md --path CLAUDE.md --path AGENTS.md`
  result: portability scan passes; instruction files unchanged.
- command: `git diff --exit-code CLAUDE.md AGENTS.md`
  result: exit 0 (no drift; the source was not modified).

Extraction outcome:

- command: `uv run python -m pytest -q tests/test_superpowers_apm_install.py`
  result: the skill-tree identity and deployment contracts pass.

## Pause / Resume

One-shot audit-and-extract procedure with no running automation to pause. The
audit can be re-run at any time against the current instruction source; record
the commit being audited so a later re-run is comparable.

## Rollback

The audit changes no files, so it has nothing to roll back. An extraction is
reverted with `git revert` of the extraction PR (master section 3 revert-first),
which restores the procedural prose to the universal text and removes the skill
from both trees in one step.

## References

- #1871 - the audit recorded here (migrate procedural CLAUDE.md sections to
  skills); sub-issue of #226.
- [../prd/agent-rules-design-philosophy.md](../prd/agent-rules-design-philosophy.md):
  the four-lane ownership model and decision tree; Q1 routes tool-specific
  procedure out of the universal text, section 5.2 records the
  technique-belongs-in-skills precedent, and the P5 boundary-risk row guards
  against restating skill-owned procedure.
- [parallel-agent-dispatch.md](parallel-agent-dispatch.md) - companion runbook
  for the dispatch skills referenced from `CLAUDE.md` section 3.
- `.apm/instructions/master.instructions.md` - the universal source audited
  here; not modified by the #1871 sweep.
