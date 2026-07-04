# Handoff: .gitapex/ssot.json phase 0 (introduce, validate, own)

## Context

- Issue: #2246 (design adopted in `docs/prd/gitapex-ssot-gate-registry.md`)
- Branch: open a fresh phase 0 issue first (CLAUDE.md section 3), then a
  new session branch for it; do not reuse the design branch
  `claude/ssot-gate-functions-design-sylxc6`.
- Closes: the phase 0 follow-up issue (open it as the first step; cite
  #2246 as Related, not Closes)

## Background

The design PRD defines `.gitapex/ssot.json` as the cross-plane gate
registry with a machine-readable label routing table. Phase 0 introduces
the registry, its JSON Schema, its validator gate, and CODEOWNERS
coverage, with zero behavior change to any existing gate. Later phases
(drift observation, consumer migration, enforcement) are separate issues
and are out of scope here.

## Files to read before implementing

Read every file fully before writing a single line.

1. `docs/prd/gitapex-ssot-gate-registry.md`: the adopted design; the
   Requirements / Content section is the spec, including the schema draft
   and the validator's referential-integrity rules.
2. `docs/proposals/config-ssot-duplicate-fact-inventory.md`: the #1984
   constraint (references, not values); the registry must never restate a
   value owned elsewhere.
3. `.github/label-policy.toml` and `.github/labels.json`: label catalog
   plus rename/retired tables the validator resolves label strings
   against.
4. `docs/runbooks/issue-triage.md` (section "Agent routing"): the prose
   routing table the `label_routing` block encodes verbatim.
5. `scripts/scan_doc_graph_registration.py`: the closest existing
   registry-gate; mirror its structure (pure functions, verify
   subcommand, `::error` annotations, exit codes 0/1/64).
6. `scripts/agent_hooks_source.json` and `scripts/preflight_steps.py`:
   the manifests whose gate entries seed the registry's `gates` array.
7. `.pre-commit-config.yaml` and `.github/workflows/verify-pr.yml`: where
   the validator wires in (mirror how existing scan gates register on
   both planes).
8. `docs/standards/workflow-script-quality.md`: quality bar for the new
   script.

## Implementation

Deliverables, all in one PR:

- `.gitapex/ssot.json`: meta (schema_version 1, tracking_issue, status,
  phase "phase-0"), policy_sources, gates (seed with the PreToolUse plane
  entries from `scripts/agent_hooks_source.json` first; other planes may
  land in phase 1 with the drift gate), clusters, label_routing (encode
  the runbook table exactly; first-match-wins, one default rule last),
  label_consumers (seed from the #1041 list).
- `.gitapex/ssot.schema.json`: JSON Schema draft 2020-12; carry field
  commentary in description fields.
- `scripts/scan_ssot_schema.py`: verify subcommand; validates shape
  against the schema AND referential integrity (paths tracked, ids
  resolve; `label_routing` labels resolve against labels.json ONLY,
  `label_consumers` labels resolve against labels.json unioned with
  label-policy rename_from and retired tables; `gates[].kind` is
  script or native, with `script` respectively `native_rule` present
  per kind). Fail loud, exit 1 with
  `::error` per violation; exit 64 on unknown subcommand. stdlib only if
  feasible; if jsonschema is needed, pin it via the existing uv
  dependency flow.
- `tests/test_scan_ssot_schema.py`: cover happy path, each
  referential-integrity failure class, and the ordered-rules invariant.
- CODEOWNERS: add `/.gitapex/ @tvna`.
- Wiring: add the validator to `.pre-commit-config.yaml`,
  `scripts/preflight_steps.py` STEPS, and the verify-pr portable policy
  job, mirroring an existing scan gate's three-plane registration. Note
  `scan_preflight_drift.py` reconciles STEPS with workflow YAML; register
  consistently so it stays green.

Do not add files, hooks, or abstractions beyond what is described here.
No existing gate's behavior may change; the validator gates only the new
`.gitapex/` files.

## Verification

Run after implementing:

    uv run python scripts/scan_ssot_schema.py verify
    uv run pytest tests/test_scan_ssot_schema.py -v
    uv run python scripts/scan_preflight_drift.py verify
    prek run --all-files

Expected: all exit 0. Also run the two text gates on every new/edited
markdown or JSON file per repository policy (em dash, double hyphen).

## PR creation

Read `.github/PULL_REQUEST_TEMPLATE.md` before drafting the body.

Suggested title:

    feat(ssot): add .gitapex/ssot.json registry, schema, and validator gate (phase 0)

Body must cite the phase 0 issue (Closes) and #2246 (Refs), and carry the
required sections per `docs/standards/issue-pr-body-standard.md`.

## Acceptance criteria

- [ ] `.gitapex/ssot.json` and `.gitapex/ssot.schema.json` exist;
  `uv run python scripts/scan_ssot_schema.py verify` exits 0.
- [ ] Validator registered on pre-commit, STEPS, and verify-pr planes;
  `scan_preflight_drift.py verify` exits 0.
- [ ] CODEOWNERS covers `/.gitapex/`.
- [ ] `label_routing` encodes the issue-triage runbook table exactly
  (same order, same actions, one default rule).
- [ ] No behavior change to any existing gate (diff touches no existing
  gate's logic).
- [ ] CI green on the pushed branch.
