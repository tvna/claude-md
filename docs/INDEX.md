# docs/ index

This file enumerates every document under `docs/` by the lane that owns
it. Lanes are the buckets that `ls docs/` already shows:
`prd/` (design-stage rationale and decision records), `standards/`
(adopted rules, schemas, and contracts), `runbooks/` (operator
procedures), `generated/` (checked-in generated views), `archive/`
(frozen historical evidence).

If you only want one entry per lane, read the first row of each table
below -- that is the highest-traffic document in the lane. Otherwise
scan the `Territory` column for the domain you care about and follow
the `Companion` column to the workflow or script that implements it.

Lane README files define the detailed placement rules:
[`prd/README.md`](prd/README.md), [`standards/README.md`](standards/README.md),
and [`runbooks/README.md`](runbooks/README.md). The append-only policy
for `archive/` is documented separately in
[`archive/RETENTION.md`](archive/RETENTION.md).

## prd/ -- design-stage rationale and decision records

| File | Territory | Tracking issues | Companion |
|---|---|---|---|
| [README.md](prd/README.md) | Compatibility entrypoint for PRD/design placement rules. | #202 | `docs/INDEX.md`; `docs/standards/documentation-quality.md` |
| [agent-rules-design-philosophy.md](prd/agent-rules-design-philosophy.md) | Meta-runbook for evolving `.apm/instructions/master.instructions.md` and its compiled `CLAUDE.md` / `AGENTS.md`. Six principles plus the four-lane responsibility matrix. | #226, #246 | `.apm/instructions/master.instructions.md` (source); `scripts/scan_design_philosophy_drift.py`; `.github/workflows/verify-design-philosophy.yml` |
| [codex-permission-request-policy-gate.md](prd/codex-permission-request-policy-gate.md) | Design-stage plan for a future Codex `PermissionRequest` adapter backed by a shared repository policy predicate and Claude parity evidence. | #711, #617, #604 | `.codex/hooks.json`; `.claude/settings.json`; `tests/test_codex_hooks_config.py` |
| [repair-loops-proliferation-analysis.md](prd/repair-loops-proliferation-analysis.md) | Read-only analysis of auto-retro repair-loop signal branches; feeds future follow-up issues rather than defining a gate. | #412 | `scripts/auto_retro.py`; `docs/archive/retrospective-pr-*.md` |
| [security-control-inventory.md](prd/security-control-inventory.md) | MITRE ATT&CK coverage SoT for repository security surfaces. Re-read whenever a workflow, script, ruleset, or runbook lands. | #179, #178 | `scripts/security_drift_report.py`; `.github/workflows/weekly-maintenance.yml` |
| [privileged-operation-runbooks.md](prd/privileged-operation-runbooks.md) | Six-control contract (authorizing issue, dry-run, live apply, rollback, audit, secret-leak evidence) for every privileged operation. | #182, #178 | `.github/workflows/apply-rulesets.yml`; `.github/workflows/apply-labels.yml`; `.github/workflows/weekly-maintenance.yml` |
| [non-ascii-defense.md](prd/non-ascii-defense.md) | Three-layer ASCII discipline at the GitHub-post boundary. | #102 | `scripts/scan_non_ascii.py`; `scripts/preflight_non_ascii.py`; `scripts/sanitize_history.py`; `.github/workflows/issue-pr-triage.yml` |

The last three `prd/` entries are adopted contracts with legacy
placement. They should move to `standards/` in a scoped follow-up rather
than serving as precedent for new PRD files.

## standards/ -- adopted rules, schemas, and contracts

| File | Territory | Tracking issues | Companion |
|---|---|---|---|
| [README.md](standards/README.md) | Placement rules for adopted repository standards. | #202 | `docs/INDEX.md`; `docs/standards/documentation-quality.md` |
| [issue-pr-body-standard.md](standards/issue-pr-body-standard.md) | Required H2 sections, ordering, and Facts / Assumptions discipline for issue and PR bodies. | #226 section 7 | `scripts/body_policy.py`; `scripts/preflight_pr_body_required_sections.py`; `scripts/preflight_pr_template_shape.py`; `.github/workflows/portable-pr-policy.yml`; `.github/workflows/verify-github-content.yml`; `.github/PULL_REQUEST_TEMPLATE.md` |
| [workflow-script-quality.md](standards/workflow-script-quality.md) | Quality gates M1 through M9 for Python scripts under `scripts/` invoked from `.github/workflows/`. | #226 principle P4 | `.github/workflows/verify-agents.yml` (`lint-scripts` job: ruff, mypy, pytest with coverage floor) |
| [documentation-quality.md](standards/documentation-quality.md) | Deterministic documentation quality checks for contributor-facing standards and runbooks. | #202, #918 | `scripts/scan_markdown_links.py`; `scripts/scan_docs_inventory.py`; `.github/workflows/verify-agents.yml` (`lint-scripts-static` job) |
| [pr-subscription-lifecycle.md](standards/pr-subscription-lifecycle.md) | Terminal-state signal contract for merged PRs after the auto-retro pipeline opens or reuses the retrospective issue. | #387 | `scripts/auto_retro.py`; `.github/workflows/post-merge.yml`; `.github/labels.json` |
| [maintainability-metrics.md](standards/maintainability-metrics.md) | Lightweight maintainability metric inventory and the module-size pilot gate for scripts under `scripts/`. | #200 | `scripts/scan_maintainability_metrics.py`; `.github/workflows/verify-agents.yml` (`lint-scripts-static` job) |
| [dependency-freshness.md](standards/dependency-freshness.md) | Recurring dependency freshness, lockfile drift, and toolchain reproducibility track. | #201 | `.github/workflows/weekly-maintenance.yml`; `scripts/uv_pin.py`; `scripts/scan_workflow_action_pins.py`; `scripts/scan_workflow_pip.py`; `.github/dependabot.yml` |
| [repo-scope.md](standards/repo-scope.md) | Repo purpose statement and the content-based prohibition on agent-tool-specific configuration files (the Q1 disqualifier). | #58 | `.gitignore`; `.claudeignore` (current enforcement; Phase 4 CI gate parked) |
| [remote-environment.md](standards/remote-environment.md) | Keeping the remote execution environment's `uv` aligned with what CI uses. | #106, #109 | `scripts/install-uv.sh`; `scripts/uv_pin.py`; `pyproject.toml` (`[tool.uv].required-version`) |
| [performance-metrics.md](standards/performance-metrics.md) | Phase 2 design-only measurement schema for the performance impact of master-source edits. No harness lands with this document. | #58, #61 | (none; Phase 3 harness tracked in #62) |
| [host-unit-duckdb-metrics.md](standards/host-unit-duckdb-metrics.md) | OTel-compatible per-host DuckDB store for the quality-vs-scope proportionality signal. Supersedes the orphan-branch JSON approach; collect early in DuckDB, export to OTLP later. | #815, #814, #226 | `metrics/duckdb/schema/v1/schema.sql`; `docs/standards/performance-metrics.md` |

## runbooks/ -- operator procedures

| File | Territory | Tracking issues | Companion |
|---|---|---|---|
| [README.md](runbooks/README.md) | Placement rules for operator procedures. | #202 | `docs/INDEX.md`; `docs/standards/documentation-quality.md` |
| [rulesets.md](runbooks/rulesets.md) | Apply / verify / rollback runbook for `.github/rulesets/*.json` SoT. | #18 | `.github/workflows/apply-rulesets.yml`; `.github/workflows/verify-ruleset-sync.yml`; `.github/workflows/weekly-maintenance.yml`; `scripts/rulesets_apply.py`; `scripts/ruleset_drift.py`; `scripts/verify_ruleset_sync.py` |
| [issue-triage.md](runbooks/issue-triage.md) | Label taxonomy and routing runbook readable from `labels.nodes[]` headers without fetching issue bodies. | #84, #34 | `.github/labels.json`; `.github/workflows/apply-labels.yml`; `scripts/labels_apply.py` |
| [branch-cleanup.md](runbooks/branch-cleanup.md) | Weekly survey of abandoned branches; currently dry-run only. | #31, #18 Phase 4-B | `.github/workflows/weekly-maintenance.yml`; `scripts/branch_cleanup.py` |
| [dependabot-automerge.md](runbooks/dependabot-automerge.md) | Audit-first Dependabot auto-merge policy gates. | #185 | `.github/dependabot-automerge.json`; `.github/workflows/dependabot-automerge.yml`; `.github/workflows/verify-dependabot-labels.yml`; `scripts/dependabot_automerge.py`; `scripts/dependabot_labels.py` |
| [devcontainers.md](runbooks/devcontainers.md) | VS Code devcontainer entrypoints for Claude and Codex, with Nix-managed tool versions and egress allowlists. | #643 | `.devcontainer/**`; `flake.nix`; `flake.lock`; `scripts/nixpkgs_cooldown.py` |
| [workflow-permissions-audit.md](runbooks/workflow-permissions-audit.md) | Least-privilege matrix for every workflow (trigger, token / secret used, minimum permissions vs declared, mismatch follow-up). | #181, #178 | `.github/workflows/*.yml` (audit target); `scripts/scan_workflow_pip.py`; `scripts/scan_workflow_action_pins.py` |
| [security-control-drift-report.md](runbooks/security-control-drift-report.md) | Aggregator runbook for per-family drift detectors posting a single rolling comment on the MITRE ATT&CK tracker. | #180, #178 | `.github/workflows/weekly-maintenance.yml`; `scripts/security_drift_report.py` |
| [downstream-instruction-review-checklist.md](runbooks/downstream-instruction-review-checklist.md) | Security-focused review checklist for PRs that change instructions this repository ships to downstream consumers. | #183, #178 | `.github/workflows/portable-pr-policy.yml`; `.github/PULL_REQUEST_TEMPLATE.md` (Bootstrap items) |
| [agent-provenance.md](runbooks/agent-provenance.md) | Provenance metadata and review criteria for skills, subagents, MCP servers, and comparable agent extensions. | #312, #63 | `docs/prd/security-control-inventory.md`; `docs/runbooks/downstream-instruction-review-checklist.md`; `docs/standards/repo-scope.md` |
| [attack-coverage-review-cadence.md](runbooks/attack-coverage-review-cadence.md) | Quarterly review cadence and comment template for the MITRE ATT&CK coverage tracker (#178). | #184, #178 | `.github/workflows/attack-coverage-review-reminder.yml` |
| [ci-monitoring-polling-vs-webhook.md](runbooks/ci-monitoring-polling-vs-webhook.md) | Operator choice guide for polling and webhook-backed PR CI monitoring paths. | #781 | `scripts/post_pr_create_ci_monitor.py`; GitHub PR activity subscription |
| [issue-closure-fast-path.md](runbooks/issue-closure-fast-path.md) | Fast evidence loop for closing GitHub issues from direct merged-PR evidence. | #187 | `scripts/issue_closure_fast_path.py`; GitHub issue close tool calls |
| [measure-lint-pytest-timings.md](runbooks/measure-lint-pytest-timings.md) | Operator procedure for collecting and publishing verify-agents timing reports. | #545 | `.github/workflows/weekly-maintenance.yml`; `scripts/analyze_ci_timings.py` |
| [preflight.md](runbooks/preflight.md) | Local pre-push and manual preflight entrypoint mirroring PR-gating CI scripts. | #493 | `scripts/preflight_all.py`; `scripts/scan_preflight_drift.py`; `.githooks/pre-push` |
| [replacement-pr-preflight.md](runbooks/replacement-pr-preflight.md) | Guardrail for closing a PR and opening a replacement for the same issue or session. | #632 | `scripts/preflight_replacement_pr.py` |
| [retro-labels.md](runbooks/retro-labels.md) | Operator runbook for `retro:*` labels that classify retrospective true/false positives and feed the auto-retro prior. | #558, #582 | `scripts/_retro_labels.py`; `scripts/scan_retro_followup_drift.py`; `.github/workflows/retro-followup-drift.yml` |
| [retrospective-noise-flooding-procedure.md](runbooks/retrospective-noise-flooding-procedure.md) | Operator procedure for reviewing retrospective and auto-retro flooding signal vs noise. | #315, #63 Phase 8(D-3) | `.github/workflows/post-merge.yml`; `scripts/auto_retro.py`; `docs/archive/retrospective-pr-*.md` (subject) |
| [prek.md](runbooks/prek.md) | `j178/prek` install steps, configured hooks, and the CI gate that runs `prek run --all-files` on every PR. | #408 | `.pre-commit-config.yaml`; `.github/workflows/verify-agents.yml` (`prek` job); `scripts/uv_pin.py`; `scripts/scan_workflow_pip.py` |
| [readme-translation-drift.md](runbooks/readme-translation-drift.md) | Deterministic gate that fails a PR when `README.md` changes without matching `README.ja.md` / `README.zh.md` updates, plus the opt-out marker procedure. | #476 | `scripts/verify_readme_translation.py`; `.github/workflows/portable-pr-policy.yml` (`gate` job); `README.md`; `README.ja.md`; `README.zh.md` |

## generated/ -- checked-in generated views

| File | Subject | Source | Tracking issues |
|---|---|---|---|
| [auto-retro-decision-tree.md](generated/auto-retro-decision-tree.md) | Mermaid decision tree for the current `auto_retro.run()` control flow. | `python3 scripts/auto_retro.py decision-tree-doc` | #598, #605 |

## archive/ -- frozen historical evidence

These files are append-only. Their narrative references to pre-restructure
paths reflect the state at PR-merge time and are preserved as historical
fidelity. See [`archive/RETENTION.md`](archive/RETENTION.md) for the
naming convention and the per-30-entries year-folder cutover.

| File | Subject |
|---|---|
| [decision-tree-replay.md](archive/decision-tree-replay.md) | Calibration evidence that the decision tree in `prd/agent-rules-design-philosophy.md` section 4 reproduces historical lane assignments. Append-only; not normative. |
| [issue-pr-body-examples.md](archive/issue-pr-body-examples.md) | Worked example bodies, one per `type:*` label plus one PR. Calibration material for `standards/issue-pr-body-standard.md`. |
| [label-migration-2026-05-26.md](archive/label-migration-2026-05-26.md) | Append-only operation log for the 2026-05-26 label backfill and prune preparation. |
| [renovate-poc-279.md](archive/renovate-poc-279.md) | Renovate migration PoC primary-source evidence for issue #279 (Q2/Q3/Q4 answered from Renovate docs; Q1 pending human Mend Renovate App install). Two documentary candidate ruleset shapes captured against the post-PR-#454 SoT. |
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
- [agent-provenance.md](agent-provenance.md) -- compatibility pointer to `runbooks/agent-provenance.md` for the original #312 target path.
- This INDEX is reviewed whenever a file is added, removed, or moved across lanes. Treat it as a self-describing supplement to `ls docs/`, not a replacement for the folder layout: the lane is visible at the filesystem level; this index just names what each file owns.
