# docs/ index

This file enumerates every document under `docs/` by the lane that owns
it. Lanes are the same four buckets that `ls docs/` already shows:
`prd/` (design contracts), `standards/` (shapes, schemas, and contracts),
`runbooks/` (operator procedures), `archive/` (frozen historical evidence).

If you only want one entry per lane, read the first row of each table
below -- that is the highest-traffic document in the lane. Otherwise
scan the `Territory` column for the domain you care about and follow
the `Companion` column to the workflow or script that implements it.

The append-only policy for `archive/` is documented separately in
[`archive/RETENTION.md`](archive/RETENTION.md).

## prd/ -- design contracts

| File | Territory | Tracking issues | Companion |
|---|---|---|---|
| [agent-rules-design-philosophy.md](prd/agent-rules-design-philosophy.md) | Meta-runbook for evolving `.apm/instructions/master.instructions.md` and its compiled `CLAUDE.md` / `AGENTS.md`. Six principles plus the four-lane responsibility matrix. | #226, #246 | `.apm/instructions/master.instructions.md` (source); `scripts/scan_design_philosophy_drift.py`; `.github/workflows/verify-design-philosophy.yml` |
| [security-control-inventory.md](prd/security-control-inventory.md) | MITRE ATT&CK coverage SoT for repository security surfaces. Re-read whenever a workflow, script, ruleset, or runbook lands. | #179, #178 | `scripts/security_drift_report.py`; `.github/workflows/security-control-drift-report.yml` |
| [privileged-operation-runbooks.md](prd/privileged-operation-runbooks.md) | Six-control contract (authorizing issue, dry-run, live apply, rollback, audit, secret-leak evidence) for every privileged operation. | #182, #178 | `.github/workflows/apply-rulesets.yml`; `.github/workflows/apply-labels.yml`; `.github/workflows/branch-cleanup.yml` |
| [non-ascii-defense.md](prd/non-ascii-defense.md) | Three-layer ASCII discipline at the GitHub-post boundary. | #102 | `scripts/scan_non_ascii.py`; `scripts/preflight_non_ascii.py`; `scripts/sanitize_history.py`; `.github/workflows/scan-non-ascii.yml` |

## standards/ -- shapes, schemas, contracts

| File | Territory | Tracking issues | Companion |
|---|---|---|---|
| [issue-pr-body-standard.md](standards/issue-pr-body-standard.md) | Required H2 sections, ordering, and Facts / Assumptions discipline for issue and PR bodies. | #226 section 7 | `scripts/body_policy.py`; `scripts/preflight_pr_body_required_sections.py`; `scripts/preflight_pr_template_shape.py`; `.github/workflows/verify-body-policy.yml`; `.github/PULL_REQUEST_TEMPLATE.md` |
| [workflow-script-quality.md](standards/workflow-script-quality.md) | Quality gates M1 through M9 for Python scripts under `scripts/` invoked from `.github/workflows/`. | #226 principle P4 | `.github/workflows/verify-agents.yml` (`lint-scripts` job: ruff, mypy, pytest with coverage floor) |
| [repo-scope.md](standards/repo-scope.md) | Repo purpose statement and the content-based prohibition on agent-tool-specific configuration files (the Q1 disqualifier). | #58 | `.gitignore`; `.claudeignore` (current enforcement; Phase 4 CI gate parked) |
| [remote-environment.md](standards/remote-environment.md) | Keeping the remote execution environment's `uv` aligned with what CI uses. | #106, #109 | `scripts/install-uv.sh`; `scripts/uv_pin.py`; `pyproject.toml` (`[tool.uv].required-version`) |
| [performance-metrics.md](standards/performance-metrics.md) | Phase 2 design-only measurement schema for the performance impact of master-source edits. No harness lands with this document. | #58, #61 | (none; Phase 3 harness tracked in #62) |

## runbooks/ -- operator procedures

| File | Territory | Tracking issues | Companion |
|---|---|---|---|
| [rulesets.md](runbooks/rulesets.md) | Apply / verify / rollback runbook for `.github/rulesets/*.json` SoT. | #18 | `.github/workflows/apply-rulesets.yml`; `.github/workflows/verify-ruleset-sync.yml`; `.github/workflows/ruleset-drift.yml`; `scripts/rulesets_apply.py`; `scripts/ruleset_drift.py`; `scripts/verify_ruleset_sync.py` |
| [issue-triage.md](runbooks/issue-triage.md) | Label taxonomy and routing runbook readable from `labels.nodes[]` headers without fetching issue bodies. | #84, #34 | `.github/labels.json`; `.github/workflows/apply-labels.yml`; `scripts/labels_apply.py` |
| [branch-cleanup.md](runbooks/branch-cleanup.md) | Weekly survey of abandoned branches; currently dry-run only. | #31, #18 Phase 4-B | `.github/workflows/branch-cleanup.yml`; `scripts/branch_cleanup.py` |
| [dependabot-automerge.md](runbooks/dependabot-automerge.md) | Audit-first Dependabot auto-merge policy gates. | #185 | `.github/dependabot-automerge.json`; `.github/workflows/dependabot-automerge.yml`; `.github/workflows/verify-dependabot-labels.yml`; `scripts/dependabot_automerge.py`; `scripts/dependabot_labels.py` |
| [workflow-permissions-audit.md](runbooks/workflow-permissions-audit.md) | Least-privilege matrix for every workflow (trigger, token / secret used, minimum permissions vs declared, mismatch follow-up). | #181, #178 | `.github/workflows/*.yml` (audit target); `scripts/scan_workflow_pip.py`; `scripts/scan_workflow_action_pins.py` |
| [security-control-drift-report.md](runbooks/security-control-drift-report.md) | Aggregator runbook for per-family drift detectors posting a single rolling comment on the MITRE ATT&CK tracker. | #180, #178 | `.github/workflows/security-control-drift-report.yml`; `scripts/security_drift_report.py` |
| [downstream-instruction-review-checklist.md](runbooks/downstream-instruction-review-checklist.md) | Security-focused review checklist for PRs that change instructions this repository ships to downstream consumers. | #183, #178 | `.github/workflows/verify-apm-portability.yml`; `.github/workflows/verify-apm-drift.yml`; `.github/PULL_REQUEST_TEMPLATE.md` (Bootstrap items) |
| [retrospective-noise-flooding-procedure.md](runbooks/retrospective-noise-flooding-procedure.md) | Operator procedure for reviewing retrospective and auto-retro flooding signal vs noise. | #315, #63 Phase 8(D-3) | `.github/workflows/auto-retro.yml`; `scripts/auto_retro.py`; `docs/archive/retrospective-pr-*.md` (subject) |

## archive/ -- frozen historical evidence

These files are append-only. Their narrative references to pre-restructure
paths reflect the state at PR-merge time and are preserved as historical
fidelity. See [`archive/RETENTION.md`](archive/RETENTION.md) for the
naming convention and the per-30-entries year-folder cutover.

| File | Subject |
|---|---|
| [decision-tree-replay.md](archive/decision-tree-replay.md) | Calibration evidence that the decision tree in `prd/agent-rules-design-philosophy.md` section 4 reproduces historical lane assignments. Append-only; not normative. |
| [issue-pr-body-examples.md](archive/issue-pr-body-examples.md) | Worked example bodies, one per `type:*` label plus one PR. Calibration material for `standards/issue-pr-body-standard.md`. |
| [retrospective-pr-229.md](archive/retrospective-pr-229.md) | Retrospective for PR #229 (layer responsibility boundary repair loops). |
| [retrospective-pr-235.md](archive/retrospective-pr-235.md) | Retrospective for PR #235 (security control inventory, repair-free). |
| [retrospective-pr-237.md](archive/retrospective-pr-237.md) | Retrospective for PR #237 (auto-retro workflow, repair-free). |
| [retrospective-pr-248.md](archive/retrospective-pr-248.md) | Retrospective for PR #248 (agent-rules design philosophy, repair-free). |
| [retrospective-pr-249.md](archive/retrospective-pr-249.md) | Retrospective for PR #249 (security-drift aggregator, repair-free). |
| [retrospective-pr-256.md](archive/retrospective-pr-256.md) | Retrospective for PR #256 (agent-rules checklist follow-up, repair-free). |
| [retrospective-pr-257.md](archive/retrospective-pr-257.md) | Retrospective for PR #257 (workflow permissions audit, repair-free). |
| [retrospective-pr-337.md](archive/retrospective-pr-337.md) | Retrospective for PR #337 (no-override rule, repair-free). |
| [retrospective-pr-349.md](archive/retrospective-pr-349.md) | Retrospective for PR #349 (GitHub Advisory Database direct query, repair-free). |

## Navigation aids

- [archive/RETENTION.md](archive/RETENTION.md) -- append-only policy and auto-retro placement convention for `archive/`.
- This INDEX is reviewed whenever a file is added, removed, or moved across lanes. Treat it as a self-describing supplement to `ls docs/`, not a replacement for the folder layout: the lane is visible at the filesystem level; this index just names what each file owns.
