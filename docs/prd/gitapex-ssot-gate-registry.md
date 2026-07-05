# .gitapex/ssot.json: Gate-Function Registry with Label Routing

Date: 2026-07-03
Refs: [#2246](https://github.com/tvna/claude-md/issues/2246)

Related: [#1984](https://github.com/tvna/claude-md/issues/1984) (config SSoT
inventory), [#1041](https://github.com/tvna/claude-md/issues/1041) (hardcoded
label literals), [#1043](https://github.com/tvna/claude-md/issues/1043)
(shared type vocabulary), [#970](https://github.com/tvna/claude-md/issues/970)
(label taxonomy design), [#972](https://github.com/tvna/claude-md/issues/972)
(label live migration).

## Purpose

Define a single machine-readable registry, `.gitapex/ssot.json`, that makes
the repository's gate functions a governed single source of truth (SSoT):
which deterministic gates exist, on which enforcement planes they fire, which
policy definition files they read, and how agent reasoning is routed by
GitHub labels. The registry holds references and routing, never policy
values; each policy file stays authoritative for its own content. The design
includes a phased migration plan whose steps are individually small,
reversible by `git revert`, and behavior-neutral until explicitly promoted.

## Background

The repository enforces its rules on four planes:

1. Agent hooks (`.claude/settings.json` PreToolUse / PostToolUse / Stop /
   SessionStart), generated from `scripts/agent_hooks_source.json` by
   `scripts/gen_agent_hooks.py` (with `.codex/hooks.json` and
   `.devin/hooks.v1.json` as parallel generated outputs).
2. Local git hooks: prek pre-commit stage (`.pre-commit-config.yaml`) and
   the pre-push preflight (`.githooks/pre-push` running
   `scripts/preflight_all.py` over `scripts/preflight_steps.py` `STEPS`).
3. CI: `verify-pr.yml`, `verify-agents.yml`, and sibling workflows, with
   the required-check set declared in `.github/rulesets/main.json`.
4. Server-side automation (`issue-pr-triage.yml`, `apply-labels.yml`,
   `post-merge.yml`).

Each plane carries its own partial gate manifest, and the same rule is often
enforced on two or three planes (non-ASCII, coverage floor, commit signing,
gh CLI ban, generated-tree edit protection). `scripts/scan_preflight_drift.py`
exists solely to reconcile `STEPS` with the workflow YAML; no manifest spans
all planes. Separately, the adopted label taxonomy
(`.github/label-policy.toml` design, `.github/labels.json` live catalog)
drives agent routing through a prose decision table in
`docs/runbooks/issue-triage.md`, while label-consuming scripts hardcode label
literals; #1041 records the latent breakage this causes across renames.

The prior SSoT investigation
(`docs/proposals/config-ssot-duplicate-fact-inventory.md`, #1984) concluded
that physically consolidating owner-distinct policy files degrades SSoT
posture: it collapses CODEOWNERS boundaries, mixes lifecycles, and turns
independent drift gates into a single point of failure. This design accepts
that conclusion as a constraint.

## Facts

- Fact: gate declarations live today in at least five partial manifests:
  `scripts/agent_hooks_source.json`, `scripts/preflight_steps.py` `STEPS`,
  `.pre-commit-config.yaml`, `.github/rulesets/main.json`, and the
  enforcement registries `docs/standards/*.enforcement.toml`.
- Fact: `.claude/settings.json` carries a full second copy of the
  GitHub-write PreToolUse hook list for the `mcp__codex_apps__github._*`
  namespace; the duplication is structural, not accidental, and is managed
  by the `gen_agent_hooks.py` generation chain.
- Fact: the agent routing decision table (`docs/runbooks/issue-triage.md`,
  section "Agent routing") is first-match-wins over `(type, state,
  severity)` labels and states that no body fetch is required for routing;
  it exists only as Markdown prose.
- Fact: `scripts/auto_retro.py`, `scripts/scan_retro_followup_drift.py`,
  `scripts/branch_cleanup.py`, `scripts/ruleset_drift.py`, and
  `.github/dependabot.yml` hardcode label names; #1041 documents which of
  those literals break at the #972 catalog migration.
- Fact: the dominant governance pattern in this repository is a declarative
  SoT file paired with a deterministic drift gate, mandated by CLAUDE.md
  section 3 ("ship its drift gate in the same change").
- Fact: no `.gitapex/` path exists anywhere in the repository or its git
  history; the namespace is new and unclaimed.
- Fact: #1984 found no Class A duplicated-value gaps in config files; the
  unsolved problem is registry-level (no cross-plane gate inventory, no
  machine-readable routing), not value-level.
- Speculation: once every gate is enumerated in one registry with its
  planes and policy references, the cross-plane duplication clusters become
  mechanically checkable, and `scan_preflight_drift.py` generalizes from a
  two-plane reconciler into a consumer of the registry.
- Speculation: a machine-readable routing table lets both agents and gates
  (for example `scripts/gate_issue_classification_labels.py`) resolve label
  policy through one indirection, which makes future renames a one-file
  change plus a lockstep-verified consumer sweep.

## Assumptions

- Assumption: the owner accepts a new top-level dot-directory `.gitapex/`
  (named by the operator in the session goal). The name is a deliberate
  choice, not derived from an existing tool; nothing in the toolchain
  claims it.
- Assumption: JSON (not TOML) is acceptable for a hand-maintained governed
  file when paired with a JSON Schema and a validator gate; the operator
  named `ssot.json` explicitly. See Considered Alternatives for the TOML
  trade-off.
- Assumption: CODEOWNERS coverage of `.gitapex/` by `@tvna` is the intended
  governance gate, in the same class as the (since-retired; #2342 folded it
  into `.gitapex/**`) former `docs/graph/**` entry.
- Assumption: implementation happens in follow-up sessions; this document
  plus the handoff prompt is the complete input those sessions need.

## Target Users

- Agents routing an issue or PR from labels alone (reasoning routing).
- Gate scripts resolving label names, routing rules, or gate metadata.
- Reviewers auditing which gates guard which operation and where the
  authoritative policy for each gate lives.
- The owner (`@tvna`) governing changes to gate topology through
  code-owner review.

## Use Cases

1. An agent picks up an issue, reads its labels, and resolves the routing
   action (`no-action`, `investigate`, `auto-fix-candidate`,
   `triage-needed`) and the permitted reasoning depth (body read allowed or
   not, autonomous PR allowed or not) from `.gitapex/ssot.json` instead of
   parsing a runbook table.
2. A label rename lands in `.github/label-policy.toml`; the registry's
   referential-integrity gate fails every stale reference in one CI run,
   producing the lockstep update list that #1041 currently reconstructs by
   hand.
3. A new gate script is added on one plane; the registry forces a
   declaration of its planes and policy sources, and the drift gate flags
   any plane where the declaration and reality disagree.
4. A reviewer asks "what blocks a force-push?" and answers it by reading
   one registry entry instead of grepping four manifests.

## Goals

- One file enumerates every deterministic gate with its planes, trigger,
  one-line rule, and policy source references.
- The agent routing table is machine-readable, first-match-wins, and
  consumed by both agents and gates.
- Label references used by scripts are resolvable through the registry so
  renames are lockstep-verifiable.
- Every phase of the migration is independently revertible and the first
  phase changes no runtime behavior.

## Success Metrics

- Phase 0 merged: `python3 scripts/scan_ssot_schema.py verify` exits 0 in
  CI and the registry file exists; zero behavior change elsewhere
  (verifiable: no other gate's inputs or outputs differ).
- Phase 1 merged: drift between the registry and the four existing
  manifests is reported deterministically (advisory first, then blocking).
- Phase 2 complete: the #1041 verification command
  (`grep -rnE "layer:meta|harness:retro-opened|..." scripts/*.py`) trends
  to zero hits as consumers migrate to registry-resolved labels.
- Phase 3 complete: a new hardcoded label literal in `scripts/*.py` fails
  CI; the runbook routing table and the registry cannot drift silently.

## Non-Goals

- No physical consolidation of policy values. `.github/label-policy.toml`,
  `.github/title-policy.toml`, `.github/labels.json`,
  `.github/rulesets/main.json`, `.github/tracking-issues.toml`, and the
  security TOMLs keep their content, owners, and paired gates (#1984).
- No replacement of the `gen_agent_hooks.py` generation chain.
  `scripts/agent_hooks_source.json` remains the generation source for the
  agent hook surfaces; the registry references it and cross-checks it, and
  any future inversion (generating it from the registry) is explicitly
  deferred.
- No change to GitHub-side enforcement (rulesets, required checks,
  CODEOWNERS semantics).
- No new gate behavior in phases 0 and 1 beyond validating and observing
  the registry itself.
- No YAML/TOML rewrite of existing manifests.

## Requirements / Content

### Design principles

1. References, not values. The registry stores pointers (paths, ids, label
   names) and topology (which gate, which plane, which policy source). A
   value that already has an owning file is never restated. This is the
   #1984 constraint applied as a schema rule: the only literals allowed in
   the registry are identifiers.
2. Registry plus paired gate, in the same change. Phase 0 ships the
   registry, its JSON Schema, and its validator gate in one PR (CLAUDE.md
   section 3).
3. Observe before enforce. Every reconciliation starts advisory and is
   promoted to blocking in a separate, revertible PR.
4. Governance-gated provenance. `.gitapex/ssot.json` becomes trusted
   instruction state only through the code-owner-reviewed merge gate
   (CLAUDE.md section 2); CODEOWNERS covers `.gitapex/` from phase 0.
5. Smallest blast radius per step. One consumer migrates per PR in phase
   2; each PR names its revert set.

### File layout

    .gitapex/
      ssot.json          the registry (hand-maintained, governed)
      ssot.schema.json   JSON Schema (draft 2020-12) for ssot.json

CODEOWNERS gains:

    /.gitapex/ @tvna

### Schema draft

Top-level shape of `.gitapex/ssot.json` (illustrative excerpt, not the
normative schema; the normative schema is `ssot.schema.json`):

    {
      "meta": {
        "schema_version": 1,
        "tracking_issue": 2246,
        "status": "adopted-design",
        "phase": "phase-0"
      },
      "policy_sources": [
        {
          "id": "label-policy",
          "path": ".github/label-policy.toml",
          "format": "toml",
          "authority": "label taxonomy design; families, renames, area paths",
          "paired_gates": ["labels-apply-validate", "scan-area-path-coverage"]
        },
        {
          "id": "labels-live",
          "path": ".github/labels.json",
          "format": "json",
          "authority": "live label catalog applied to GitHub"
        },
        {
          "id": "agent-hooks-source",
          "path": "scripts/agent_hooks_source.json",
          "format": "json",
          "authority": "generation source for agent hook surfaces"
        },
        {
          "id": "rulesets-main",
          "path": ".github/rulesets/main.json",
          "format": "json",
          "authority": "GitHub ruleset: required checks and native branch rules"
        }
      ],
      "gates": [
        {
          "id": "preflight-non-ascii",
          "kind": "script",
          "script": "scripts/preflight_non_ascii.py",
          "rule": "GitHub-bound bodies are ASCII",
          "planes": ["pretooluse"],
          "trigger": "mcp github write tools",
          "policy_refs": [],
          "cluster": "non-ascii",
          "tracking_issue": 1889
        },
        {
          "id": "gate-issue-classification-labels",
          "kind": "script",
          "script": "scripts/gate_issue_classification_labels.py",
          "rule": "agent-created issues carry layer:* and type:* labels",
          "planes": ["pretooluse"],
          "trigger": "mcp__github__issue_write create",
          "policy_refs": ["labels-live", "label-policy"],
          "cluster": null,
          "tracking_issue": null
        },
        {
          "id": "ruleset-no-force-push",
          "kind": "native",
          "native_rule": "non_fast_forward",
          "rule": "branch history cannot be rewritten",
          "planes": ["server"],
          "trigger": "git push (non-fast-forward)",
          "policy_refs": ["rulesets-main"],
          "cluster": null,
          "tracking_issue": null
        }
      ],
      "clusters": [
        {
          "id": "non-ascii",
          "rule": "ASCII-only outward text",
          "expected_planes": ["pretooluse", "pre-push", "ci", "server"]
        }
      ],
      "label_routing": {
        "source_note": "machine form of docs/runbooks/issue-triage.md Agent routing",
        "rules": [
          { "if_any": ["state:rfc", "state:parked"],
            "action": "no-action", "body_read": "no" },
          { "if_any": ["type:tracking"],
            "action": "no-action-umbrella", "body_read": "no" },
          { "if_any": ["severity:security"],
            "action": "investigate", "body_read": "yes",
            "autonomous_pr": false },
          { "if_all": ["type:fix"], "if_none": ["severity:security"],
            "action": "auto-fix-candidate", "body_read": "yes",
            "autonomous_pr": true },
          { "if_any": ["type:docs"],
            "action": "auto-fix-candidate", "body_read": "yes",
            "autonomous_pr": true },
          { "if_any": ["type:feat", "type:refactor"],
            "action": "investigate", "body_read": "yes",
            "autonomous_pr": false },
          { "default": true,
            "action": "triage-needed", "body_read": "title-only" }
        ]
      },
      "label_consumers": [
        {
          "script": "scripts/auto_retro.py",
          "labels": ["type:docs", "ops:retro-opened"],
          "note": "retro identity and terminal labels; see #1041"
        }
      ]
    }

Schema rules the validator enforces (referential integrity, all
deterministic):

- Every `policy_sources[].path`, `gates[].script`, and every path-like
  field resolves to a tracked file.
- Every `gates[].policy_refs[]` entry names an existing
  `policy_sources[].id`.
- Every label string in `label_routing` resolves against the live
  catalog `.github/labels.json` ONLY. Routing is executable against the
  labels GitHub applies today; a renamed-away or retired name would
  validate but never match, silently falling through to the default
  route, so legacy names are rejected in this block. When the catalog
  flips a rename, the validator fails the stale routing rule in the same
  PR, forcing the lockstep edit.
- Every label string in `label_consumers` resolves against
  `.github/labels.json` unioned with the `rename_from` and `retired`
  tables of `.github/label-policy.toml`. The inventory may legitimately
  record a legacy name mid-migration, and the union is what makes stale
  consumer references detectable (the deterministic guard #1041 asks
  for, applied first to the registry and, in phase 3, to the scripts
  themselves).
- `gates[].kind` is `script` or `native`. A `script` entry carries
  `gates[].script` (a tracked path); a `native` entry carries
  `gates[].native_rule` naming the enforcing platform rule (for example
  the `non_fast_forward`, `deletion`, `required_signatures`, or
  pull-request review rule types in `.github/rulesets/main.json`), so
  GitHub-side enforcement is inventoried first-class instead of being
  omitted or faked as a script.
- `label_routing.rules` is an ordered array; exactly one `default` rule,
  and it is last.
- `gates[].planes[]` values come from the closed enum `pretooluse`,
  `posttooluse`, `stop`, `sessionstart`, `userpromptsubmit`,
  `pre-commit`, `pre-push`, `ci`, `server`.
- No free-form value duplication: the schema deliberately has no field for
  thresholds, colors, version pins, or other values owned elsewhere.

### Label-based reasoning routing

The `label_routing` table is the executable form of the runbook's
first-match-wins decision table. Consumers:

- Agents: at issue pickup, resolve labels to `action`, `body_read`, and
  `autonomous_pr` before deciding whether to fetch the body. This encodes
  the token-economy rule (route from the header, never the body) and the
  safety rule (`severity:security` never yields an autonomous PR) as data.
- Gates: `gate_issue_classification_labels.py` (axes present),
  `gate_merge_safety.py` and future routing-aware gates can read the same
  table instead of embedding routing fragments.
- The runbook keeps the human-readable rationale and gains one line
  declaring `.gitapex/ssot.json` as the executable table; a phase 3 drift
  gate parses the runbook's Markdown table and fails when the two
  disagree, so prose and data cannot diverge silently.

Routing changes therefore become: edit `label_routing` in one governed
file, pass code-owner review, and every consumer follows.

### Governance model

| Layer | Mechanism | Phase |
|---|---|---|
| Ownership | CODEOWNERS `/.gitapex/ @tvna`; merge requires owner review | 0 |
| Shape | `ssot.schema.json` validated by `scripts/scan_ssot_schema.py` | 0 |
| Referential integrity | same validator: paths exist, ids resolve, labels resolve per the split rules (routing: live catalog only; consumers: catalog plus rename/retired tables) | 0 |
| Reality reconciliation | `scripts/scan_ssot_drift.py`: registry vs `agent_hooks_source.json`, `preflight_steps.py` `STEPS`, `.pre-commit-config.yaml`, `.github/rulesets/main.json` | 1 (advisory), then blocking |
| Consumption | `scripts/_ssot.py` shared reader; consumers import it | 2 |
| Anti-regression | literal-label scan over `scripts/*.py`; runbook-table-vs-registry drift gate | 3 |

The validator registers on the same planes the repository already uses for
registry gates: pre-commit (prek), `preflight_steps.py` `STEPS`, and
`verify-pr.yml`, mirroring how `scan_doc_graph_registration.py` is wired.

Trust boundary note (CLAUDE.md section 2): the registry is read by agents at
runtime, so its provenance gate is what makes it a trusted instruction
source. Edits are a normal session task; they become trusted state only
after the code-owner-reviewed merge. The validator refusing unresolvable
references also blocks a class of smuggling (a routing rule pointing at a
label or script that does not exist cannot merge).

### Migration plan (blast-radius-ordered)

Each phase is one or more small PRs; every PR names its revert set; a
revert of any phase leaves earlier phases intact.

Phase 0: introduce, validate, own (behavior-neutral)

- Add `.gitapex/ssot.json` (meta, policy_sources, the gate entries for the
  agent-hook plane first, label_routing, label_consumers seeded from the
  #1041 list), `ssot.schema.json`, `scripts/scan_ssot_schema.py`, tests,
  CODEOWNERS line, pre-commit / STEPS / verify-pr wiring for the validator.
- Blast radius: additive only; the validator gates only the new files.
  Nothing reads the registry yet. Revert set: the single phase 0 PR.

Phase 1: observe drift (advisory), then promote

- Add `scripts/scan_ssot_drift.py` comparing the registry's `gates` and
  `clusters` against the four manifests; advisory (`::warning::`) in CI.
- Promote to blocking in a separate PR once the report is clean.
- Blast radius: CI annotations only, then one new failure mode whose fix
  is always "update the registry or the manifest"; no runtime surface.
  Revert set: the promotion PR (drops back to advisory) or both PRs.

Phase 2: consume (one consumer per PR)

- Add `scripts/_ssot.py` (load, validate lazily, resolve labels and
  routing; stdlib json only, same style as `scripts/_retro_labels.py`).
- Migrate consumers in this order (risk-ascending, from the #1041 list and
  the routing consumers):
  1. `scripts/branch_cleanup.py` (lowest risk, maintenance-only)
  2. `scripts/ruleset_drift.py`
  3. `scripts/scan_retro_followup_drift.py`
  4. `scripts/auto_retro.py` (retro identity, terminal label, search keys)
  5. `scripts/gate_issue_classification_labels.py` (axes via registry
     pointer to `label-policy` families)
- Each PR: one consumer, its tests, zero registry shape changes. Revert
  set: that PR alone; the consumer falls back to its previous literals.
- Coordination with #972: consumers migrated to registry resolution become
  immune to the catalog flip, which shrinks the lockstep set #1041 tracks.

Phase 3: enforce SSoT (anti-regression)

- Extend the drift gate: hardcoded label literals in `scripts/*.py`
  outside `_ssot.py` fail CI (allowlist for tests and for `_retro_labels.py`
  until it folds in).
- Add the runbook-table-vs-registry drift check.
- Fold `scan_preflight_drift.py`'s reconciliation into
  `scan_ssot_drift.py` (or re-point it at the registry) so the two-plane
  reconciler does not persist as a duplicate of the registry gate.
- Blast radius: new CI failure modes only; behavior of gates unchanged.

Phase 4 (deferred, explicitly out of scope now)

- Optional inversion: generate `scripts/agent_hooks_source.json` (or parts
  of `STEPS`) from the registry. Deferred because the generation chain is
  healthy, the payoff is consolidation rather than correctness, and #1984
  warns against collapsing working layers. Re-open condition: a real drift
  incident that phases 1 to 3 fail to catch, or a third hook surface that
  makes hand-maintaining both files measurably costly.

## Why

- A registry/index layer is the only SSoT shape compatible with the #1984
  conclusion: the gap is not duplicated values but the absence of a
  cross-plane inventory and machine-readable routing. This design closes
  exactly that gap and nothing else.
- Data-not-prose routing turns the most safety-relevant agent decision
  (how much to read, whether an autonomous PR is allowed) into a governed,
  diffable, first-match-wins table with a paired drift gate.
- Blast-radius ordering (validate, observe, consume, enforce) means every
  merge before phase 2 is provably inert at runtime, and phase 2 changes
  one consumer at a time with per-PR revert sets.
- The pattern (declarative SoT plus paired drift gate, advisory before
  blocking, CODEOWNERS on the governed path) is the repository's existing
  idiom; no new governance concept is introduced.

## Why not

Alternatives fail on ownership collapse (B), on leaving the cross-plane gap
open (A), or on contradicting the operator's explicit interface choice with
no compensating benefit (C, D). Details below.

## Considered Alternatives

- A. Extend existing files instead of adding a registry (put routing into
  `.github/label-policy.toml`, keep `STEPS` as the gate manifest).
  Rejected: each existing file is single-plane and single-concern by
  design; no file may own the cross-plane view without breaking its scope,
  and `STEPS` is Python data invisible to non-Python consumers. Fact: the
  cross-plane reconciliation today is a bespoke script with an allowlist
  (`scan_preflight_drift.py`), which is the symptom of the missing layer.
- B. Physically merge policy files into `.gitapex/ssot.json`. Rejected:
  #1984 already analyzed and rejected value consolidation (ownership,
  lifecycle, gate-independence). This design keeps that verdict.
- C. TOML (`.gitapex/ssot.toml`) instead of JSON. Fact: hand-maintained
  policy in this repository is mostly TOML with inline comments; JSON has
  no comments. Fact: the operator named `ssot.json` in the session goal,
  and machine-first catalogs in this repository are already JSON
  (`labels.json`, `rulesets/main.json`, `agent_hooks_source.json`).
  Chosen: JSON, with commentary carried by `ssot.schema.json`
  `description` fields and this document. The choice is reversible until
  phase 2 (only the validator would change); revisit at phase 0 review if
  the owner prefers TOML.
- D. Generated registry (scan the manifests and emit the registry).
  Rejected as the primary mechanism: a generated file cannot be the
  governance surface (nothing to review; drift gates would compare
  generated output to its own inputs). Generation stays available as a
  phase 1 helper to seed and cross-check entries.
- E. Do nothing (keep per-plane manifests plus `scan_preflight_drift.py`).
  Rejected: leaves routing as prose, label literals hardcoded (#1041
  stays open-ended), and every new cross-plane rule needing a bespoke
  reconciler.

## Acceptance Criteria

Design-stage (this issue, #2246):

- [ ] This document exists under `docs/prd/`, is registered in
  `docs/prd/README.md` and `.gitapex/doc-dependencies.toml`, and passes
  the repository text gates.
- [ ] A handoff prompt for the phase 0 implementation session exists under
  `docs/next-session/`.

Implementation-stage (follow-up issues, one per phase):

- [ ] Phase 0: `.gitapex/ssot.json` validates against `ssot.schema.json`;
  `scripts/scan_ssot_schema.py verify` exits 0 locally and in CI;
  CODEOWNERS covers `.gitapex/`; no other gate's behavior changes.
- [ ] Phase 1: `scripts/scan_ssot_drift.py verify` reports registry vs
  manifest drift; promotion to blocking is a separate revertible PR.
- [ ] Phase 2: each listed consumer resolves labels/routing via
  `scripts/_ssot.py`; the #1041 grep trends to zero.
- [ ] Phase 3: a synthetic hardcoded label literal and a synthetic
  runbook-table edit each fail CI deterministically.

## Verification

Re-runnable checks for this document's claims:

- command: `python3 scripts/scan_repo_em_dash.py verify --path docs/prd/gitapex-ssot-gate-registry.md`
  result: exit 0
- command: `python3 scripts/scan_repo_double_hyphen.py verify --path docs/prd/gitapex-ssot-gate-registry.md`
  result: exit 0
- command: `uv run python scripts/scan_docs_inventory.py verify`
  result: exit 0 (document registered in the prd lane README)
- command: `uv run python scripts/scan_doc_graph_registration.py verify`
  result: exit 0 (document registered as a graph node)
- After phase 0 lands: `uv run python scripts/scan_ssot_schema.py verify`
  result: exit 0

## Scope

In scope: the registry file and schema, its validator and drift gates, the
machine-readable routing table, the shared reader, and the consumer
migrations enumerated in phase 2. Out of scope: everything listed under
Non-Goals, and the phase 4 inversion.

## Priority

Phase 0 unblocks everything and is small; it should precede the #972 label
catalog flip so phase 2 consumers can migrate onto rename-immune resolution
while #1041's lockstep list is still short.

## Release Plan

The migration plan above is the release plan; phases map one-to-one to
follow-up issues, each opened with the body standard and closed by its
phase's acceptance criteria.

## Maintenance and Rollback

- The registry changes through normal PRs gated by CODEOWNERS review plus
  the validator; there is no out-of-band update path.
- Rollback of any phase is `git revert` of that phase's PR(s); phases are
  ordered so no later phase is load-bearing for an earlier one. The
  smallest revert sets are named per phase in the migration plan.
- This document updates by PR when the schema or phases change; the
  `meta.phase` field in the registry records rollout state so the document
  never has to.

## Open Questions / Future Work

- Phase 4 inversion (generating `agent_hooks_source.json` from the
  registry): deferred; re-open condition recorded in the migration plan.
- Folding `scripts/_retro_labels.py` into `_ssot.py`: deferred to phase 3;
  the retro TP/FP loop is stable and should not move while #972 is in
  flight.
- Whether `label_routing` should also carry per-action token budgets
  (deferred: no consumer needs them yet; adding fields later is a
  backward-compatible schema change).

## References

- Tracking: https://github.com/tvna/claude-md/issues/2246
- Related issues: https://github.com/tvna/claude-md/issues/1984,
  https://github.com/tvna/claude-md/issues/1041,
  https://github.com/tvna/claude-md/issues/1043,
  https://github.com/tvna/claude-md/issues/970,
  https://github.com/tvna/claude-md/issues/972
- Companions: `docs/proposals/config-ssot-duplicate-fact-inventory.md`;
  `docs/runbooks/issue-triage.md`; `docs/standards/label-taxonomy.md`;
  `.github/label-policy.toml`; `.github/labels.json`;
  `scripts/agent_hooks_source.json`; `scripts/preflight_steps.py`;
  `scripts/scan_preflight_drift.py`; `.github/rulesets/main.json`;
  `docs/next-session/gitapex-ssot-phase0.md`

## Graduation Path

When phase 0 is adopted, the schema contract (field meanings, validator
rules, closed enums) graduates to `docs/standards/` as the normative
registry standard; this document remains the decision record for the
design and its alternatives.
