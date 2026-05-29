# Standards

This lane holds adopted repository rules, contracts, schemas, and quality
gates. A standard should help a reviewer, CI job, or local preflight
answer whether a future change satisfies the repository's current
requirements.

Use this lane when a document defines:

- Required or forbidden behavior.
- A source-of-truth schema or classification.
- A deterministic gate or the criteria behind one.
- Review criteria that are already expected on incoming changes.
- Exception rules and the evidence required to use them.

Do not put exploratory design notes here unless the document clearly
states the adopted contract. Design-only material belongs in `docs/prd/`;
step-by-step operator procedures belong in `docs/runbooks/`.

When a standard needs an operator recipe, keep the normative rule here
and link to a runbook for the procedure.
