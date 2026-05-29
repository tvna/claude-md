# PRD and Design Notes

This lane is the compatibility entrypoint for agents and reviewers that
look for "PRD" material. Keep it for design-stage documents, decision
records, rationale, and judgment aids that have not become an adopted
repository rule.

Use this lane when a document answers questions such as:

- Why does this rule or workflow need to exist?
- Which alternatives were considered?
- Which risks, phases, or open questions should reviewers remember?
- Which future standard or runbook might this design eventually become?

Do not put adopted policy here. Once a document defines a rule that
reviewers or CI use to decide yes/no, move it to `docs/standards/`.
Once a document primarily tells an operator how to perform a task, move
it to `docs/runbooks/`.

Current compatibility notes:

- `agent-rules-design-philosophy.md` belongs here because it defines the
  repository's documentation and instruction responsibility model.
- `repair-loops-proliferation-analysis.md` belongs here because it is
  read-only analysis that feeds future follow-up issues.
- Existing adopted contracts that still live in this lane are legacy
  placement debt; migrate them to `docs/standards/` in a scoped follow-up
  instead of adding new adopted contracts here.
