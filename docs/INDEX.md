# docs/ index

This file enumerates every document under `docs/` by the lane that owns
it. Lanes are the buckets that `ls docs/` already shows:
`proposals/` (pre-decision evaluations with open questions), `prd/`
(design-stage rationale and decision records), `standards/`
(adopted rules, schemas, and contracts), `runbooks/` (operator
procedures), `uml/` (UML diagram artifacts), `generated/` (checked-in
generated views), `archive/` (frozen historical evidence).

If you only want one entry per lane, read the first row of each table
below -- that is the highest-traffic document in the lane. Otherwise
scan the `Territory` column for the domain you care about and follow
the `Companion` column to the workflow or script that implements it.

Lane README files define the detailed placement rules:
[`proposals/README.md`](proposals/README.md), [`prd/README.md`](prd/README.md),
[`standards/README.md`](standards/README.md),
and [`runbooks/README.md`](runbooks/README.md). The append-only policy
for `archive/` is documented separately in
[`archive/RETENTION.md`](archive/RETENTION.md).

## proposals/ -- pre-decision evaluations with open questions

| File | Territory | Tracking issues | Companion |
|---|---|---|---|
| [README.md](proposals/README.md) | Placement rules for pre-decision evaluations whose requirements are not yet decidable, and their graduation path into `prd/` / `standards/` / `runbooks/`. | #1001 | `docs/INDEX.md`; `docs/prd/README.md` |
| [instruction-distribution-mechanism.md](proposals/instruction-distribution-mechanism.md) | Decision (A+C: shipped sync template plus tagged release artifacts pinned by tag+sha256) for how downstream projects import the compiled instructions as committed real files; retraction of the submodule+symlink method; deferred reusable-workflow option B and its re-open condition. | #1678 | `.github/workflows/publish-instructions-release.yml`; `scripts/publish_instruction_release.py`; `docs/runbooks/consumer-instruction-sync.md` |

## prd/ -- design-stage rationale and decision records

| File | Territory | Tracking issues | Companion |
|---|---|---|---|
| [README.md](prd/README.md) | Compatibility entrypoint for PRD/design placement rules. | #202 | `docs/INDEX.md`; `docs/standards/documentation-quality.md` |
| [agent-rules-design-philosophy.md](prd/agent-rules-design-philosophy.md) | Meta-runbook for evolving `.apm/instructions/master.instructions.md` and its compiled `CLAUDE.md` / `AGENTS.md`. Six principles plus the four-lane responsibility matrix. | #226, #246 | `.apm/instructions/master.instructions.md` (source); `scripts/scan_design_philosophy_drift.py`; `.github/workflows/verify-pr.yml` (`verify-design-philosophy` job) |
| [codex-permission-request-policy-gate.md](prd/codex-permission-request-policy-gate.md) | Design-stage plan for a future Codex `PermissionRequest` adapter backed by a shared repository policy predicate and Claude parity evidence. | #711, #617, #604 | `.codex/hooks.json`; `.claude/settings.json`; `tests/test_codex_hooks_config.py` |
| [repair-loops-proliferation-analysis.md](prd/repair-loops-proliferation-analysis.md) | Read-only analysis of auto-retro repair-loop signal branches; feeds future follow-up issues rather than defining a gate. | #412 | `scripts/auto_retro.py`; `docs/archive/retrospective-pr-*.md` |
| [offline-prehead-validation-gates.md](prd/offline-prehead-validation-gates.md) | Design pattern for offline PR-head mirror gates that catch breakage a base-checkout `pull_request_target` check cannot see on the PR; five-part checklist and a gate registry. | #1519, #1511 | `scripts/threat_intel_triage.py` (`verify`); `.pre-commit-config.yaml`; `.github/workflows/verify-pr.yml` |
| [security-control-inventory.md](prd/security-control-inventory.md) | MITRE ATT&CK coverage SoT for repository security surfaces. Re-read whenever a workflow, script, ruleset, or runbook lands. | #179, #178 | `scripts/security_drift_report.py`; `.github/workflows/weekly-maintenance.yml` |
| [zero-trust-gap-analysis.md](prd/zero-trust-gap-analysis.md) | Durable Zero Trust (eBook) gap analysis mapping repo controls to seven capability domains and three maturity tiers; the session-memory-independent record of unmet gaps and their tracking issues. | #178, #1387 | `docs/prd/security-control-inventory.md`; `.github/workflows/weekly-maintenance.yml` |
| [privileged-operation-runbooks.md](prd/privileged-operation-runbooks.md) | Six-control contract (authorizing issue, dry-run, live apply, rollback, audit, secret-leak evidence) for every privileged operation. | #182, #178 | `.github/workflows/apply-rulesets.yml`; `.github/workflows/apply-labels.yml`; `.github/workflows/weekly-maintenance.yml` |
| [non-ascii-defense.md](prd/non-ascii-defense.md) | Three-layer ASCII discipline at the GitHub-post boundary. | #102 | `scripts/scan_non_ascii.py`; `scripts/preflight_non_ascii.py`; `scripts/sanitize_history.py`; `.github/workflows/issue-pr-triage.yml` |
| [freshness-precondition-gate.md](prd/freshness-precondition-gate.md) | Concrete companion to the universal time-boxed-gate refresh rule: the create_branch freshness preflight, the interim per-operation refresh, and the future auto-refresh skill. | #894, #654, #859 | `scripts/preflight_main_freshness.py`; `.claude/settings.json`; `.apm/instructions/master.instructions.md` (section 3) |

The last three `prd/` entries are adopted contracts with legacy
placement. They should move to `standards/` in a scoped follow-up rather
than serving as precedent for new PRD files.

## uml/ -- UML diagram artifacts

| File | Territory | Tracking issues | Companion |
|---|---|---|---|
| [survey-followup-timing.sequence.md](uml/survey-followup-timing.sequence.md) | Sequence diagram of the agent/CI/human handoff collaboration around the pre-merge retro survey and new-session follow-up prompt, with a grounded gap analysis (survey re-fires once per PR; follow-up timing is a cue-word heuristic). Selected over an activity-diagram candidate as the better lens for this timing/ordering defect. | #1594, #1581 | `scripts/gate_handoff_retro_survey_askuserquestion.py`; `scripts/stop_new_session_handoff_prompt.py`; `.github/workflows/post-merge.yml` |
| [survey-followup-timing.sequence.ja.md](uml/survey-followup-timing.sequence.ja.md) | Japanese translation of `survey-followup-timing.sequence.md` (owner-language reading copy of the sequence diagram and gap analysis). | #1594, #1581 | `docs/uml/survey-followup-timing.sequence.md` |
| [branch-local-remote.state.md](uml/branch-local-remote.state.md) | Two state diagrams (local working branch in the ephemeral container; remote branch on GitHub) of the branch lifecycle the agent drives in one session, with a grounded gap analysis of state divergence across the container boundary (unrecorded-session fail-open; no HEAD-vs-remote-tip gate; ephemeral unpushed loss; no remote merged-branch delete path). | #1627, #785, #1513, #31 | `scripts/preflight_push_session_branch.py`; `scripts/preflight_branch_base.py`; `scripts/branch_cleanup.py`; `scripts/gate_update_pr_branch.py` |
| [branch-local-remote.state.ja.md](uml/branch-local-remote.state.ja.md) | Japanese translation of `branch-local-remote.state.md` (owner-language reading copy of the local/remote branch state diagrams and gap analysis). | #1627, #785, #1513, #31 | `docs/uml/branch-local-remote.state.md` |

## standards/ -- adopted rules, schemas, and contracts

| File | Territory | Tracking issues | Companion |
|---|---|---|---|
| [README.md](standards/README.md) | Placement rules for adopted repository standards. | #202 | `docs/INDEX.md`; `docs/standards/documentation-quality.md` |
| [commit-signing.md](standards/commit-signing.md) | Adopted `required_signatures` rule on `main`, satisfied keylessly by GitHub's squash-merge signature; the squash-only invariant reviewers must enforce. | #32, #18 | `.github/rulesets/main.json`; `docs/runbooks/rulesets.md`; `docs/prd/security-control-inventory.md` |
| [label-taxonomy.md](standards/label-taxonomy.md) | Adopted post-#970 label taxonomy, TOML policy contract, area-to-path mapping, and operational-label rules. | #970, #972 | `.github/label-policy.toml`; `.github/labels.json`; `docs/runbooks/issue-triage.md`; `.github/workflows/apply-labels.yml` |
| [issue-pr-body-standard.md](standards/issue-pr-body-standard.md) | Required H2 sections, ordering, and Facts / Assumptions discipline for issue and PR bodies. | #226 section 7 | `scripts/body_policy.py`; `scripts/preflight_pr_body_required_sections.py`; `scripts/preflight_pr_template_shape.py`; `.github/workflows/verify-pr.yml` (`portable-pr-policy` job); `.github/workflows/verify-github-content.yml`; `.github/PULL_REQUEST_TEMPLATE.md` |
| [workflow-script-quality.md](standards/workflow-script-quality.md) | Quality gates M1 through M9 for Python scripts under `scripts/` invoked from `.github/workflows/`. | #226 principle P4 | `.github/workflows/verify-agents.yml` (`lint-scripts` job: ruff, mypy, pytest with coverage floor) |
| [pre-push-gate-performance.md](standards/pre-push-gate-performance.md) | Why the pre-push gate was slow and the coverage-preserving test-suite speed redesign: call-time sleeper seam plus autouse no-op, xdist, content-addressed skip cache, fail-fast cheap tier. | #985 | `.githooks/pre-push`; `scripts/preflight_all.py`; `scripts/preflight_cache.py`; `tests/conftest.py`; `pyproject.toml` (`[dependency-groups] local`) |
| [ci-caching-evaluation.md](standards/ci-caching-evaluation.md) | Measurement-based decision not to add CI dependency caching (uv setup is ~3s; an actions/cache round-trip would be net-negative), the per-candidate evaluation, and the revisit criteria. | #1173 | `scripts/analyze_ci_timings.py`; `scripts/ci_budget_issue.py`; `.github/actions/setup-uv/action.yml`; `.github/workflows/verify-agents.yml`; `.github/workflows/verify-flake.yml` |
| [documentation-quality.md](standards/documentation-quality.md) | Deterministic documentation quality checks for contributor-facing standards and runbooks. | #202, #918 | `scripts/scan_markdown_links.py`; `scripts/scan_docs_inventory.py`; `.github/workflows/verify-agents.yml` (`lint-scripts-static` job) |
| [readme-authoring-standard.md](standards/readme-authoring-standard.md) | Adopted structure rules for the top-level READMEs: canonical section order, numbered-step vs tool-specific-note placement, multi-language sync, and link discipline. | #1094 | `README.md`; `README.ja.md`; `README.zh.md`; `docs/runbooks/readme-translation-drift.md`; `docs/standards/documentation-quality.md` |
| [devin-apm-compatibility.md](standards/devin-apm-compatibility.md) | Adopted APM-first Devin compatibility contract: shared `.agents/skills` surface plus the `.devin/hooks.v1.json` hook adapter, with hook parity fixed by tests. | #982 | `.agents/skills`; `.devin/hooks.v1.json`; `tests/test_devin_hooks_config.py` |
| [github-mcp-app-auth.md](standards/github-mcp-app-auth.md) | Automated GitHub App token auth for the local GitHub MCP server: launch-wrapper token minting, App issuance path, env secrets, rotation, and non-exposing verification. | #1063, #1067 | `apm.yml`; `scripts/mcp_github_launch.sh`; `scripts/mint_github_app_token.py`; `tests/test_mint_github_app_token.py` |
| [agent-hooks-generation.md](standards/agent-hooks-generation.md) | Per-agent hook configs are generated from `scripts/agent_hooks_source.json` with a `git rev-parse --show-toplevel` CWD-independence wrapper injected into every repo-script command, so hooks run regardless of the session's working directory; a `--check` drift gate prevents hand-edits. | #1317, #783 | `scripts/gen_agent_hooks.py`; `scripts/agent_hooks_source.json`; `.claude/settings.json`; `.codex/hooks.json`; `.devin/hooks.v1.json`; `.pre-commit-config.yaml`; `tests/test_gen_agent_hooks.py` |
| [documented-prohibition-enforcement.md](standards/documented-prohibition-enforcement.md) | Audit mapping every documented `CLAUDE.md` / `AGENTS.md` prohibition to its enforcing deterministic gate (enforced / enforceable-gap / not-deterministically-enforceable), and the fail-closed merge-safety gate that closes the merge gap. | #1563 | `scripts/gate_merge_safety.py`; `scripts/agent_hooks_source.json`; `tests/test_gate_merge_safety.py`; `docs/runbooks/merge-readiness-loop.md` |
| [pr-subscription-lifecycle.md](standards/pr-subscription-lifecycle.md) | Terminal-state signal contract for merged PRs after the auto-retro pipeline opens or reuses the retrospective issue. | #387 | `scripts/auto_retro.py`; `.github/workflows/post-merge.yml`; `.github/labels.json` |
| [reserved-retro-scope-exception.md](standards/reserved-retro-scope-exception.md) | Why the reserved `auto-retro` scope deny gate and the in-session retro-create path (design D1) collide, and the one narrow allow-exception (the canonical handoff title) that lets them coexist, with what it covers and excludes. | #1675, #1593, #1581, #1395 | `scripts/gate_reserved_retro_scope.py`; `scripts/auto_retro.py`; `docs/runbooks/pre-merge-retro-survey.md` |
| [maintainability-metrics.md](standards/maintainability-metrics.md) | Lightweight maintainability metric inventory and the module-size pilot gate for scripts under `scripts/`. | #200 | `scripts/scan_maintainability_metrics.py`; `.github/workflows/verify-agents.yml` (`lint-scripts-static` job) |
| [dependency-freshness.md](standards/dependency-freshness.md) | Recurring dependency freshness, lockfile drift, and toolchain reproducibility track. | #201 | `.github/workflows/weekly-maintenance.yml`; `scripts/uv_pin.py`; `scripts/scan_workflow_action_pins.py`; `scripts/scan_workflow_pip.py`; `.github/dependabot.yml` |
| [repo-scope.md](standards/repo-scope.md) | Repo purpose statement and the content-based prohibition on agent-tool-specific configuration files (the Q1 disqualifier). | #58 | `.gitignore`; `.claudeignore` (current enforcement; Phase 4 CI gate parked) |
| [remote-environment.md](standards/remote-environment.md) | Keeping the remote execution environment's `uv` aligned with what CI uses. | #106, #109 | `scripts/install-uv.sh`; `scripts/uv_pin.py`; `pyproject.toml` (`[tool.uv].required-version`) |
| [devcontainer-tooling.md](standards/devcontainer-tooling.md) | Provisioning gate-required CLIs (waza, uv, ...) declaratively in the devcontainer flake, with a drift gate that fails when a gate needs a tool the container lacks, plus the egress-destination triage rule and its rationale gate. | #1100, #1103, #1170 | `flake.nix`; `scripts/scan_devcontainer_tool_drift.py`; `scripts/scan_allowlist_rationale.py`; `scripts/preflight_all.py`; `docs/runbooks/devcontainer-tool-network-triage.md`; `.github/workflows/verify-agents.yml` (`lint-scripts-static` job) |
| [performance-metrics.md](standards/performance-metrics.md) | Phase 2 design-only measurement schema for the performance impact of master-source edits. No harness lands with this document. | #58, #61 | (none; Phase 3 harness tracked in #62) |
| [sast-tooling.md](standards/sast-tooling.md) | Adopted CodeQL dataflow (taint) scan over `scripts/` (advanced setup, security-extended, informational-first) and the recorded rejection of Pyre (mypy overlap) and Pysa (pyre engine plus bespoke taint models). | #1237 | `.github/workflows/codeql.yml`; `.github/codeql/codeql-config.yml`; `pyproject.toml` (ruff `S`, mypy) |
| [host-unit-duckdb-metrics.md](standards/host-unit-duckdb-metrics.md) | OTel-compatible per-host DuckDB store for the quality-vs-scope proportionality signal. Supersedes the orphan-branch JSON approach; collect early in DuckDB, export to OTLP later. | #815, #814, #226 | `metrics/duckdb/schema/v1/schema.sql`; `docs/standards/performance-metrics.md` |
| [tool-overlap-measurement.md](standards/tool-overlap-measurement.md) | Effectiveness-measurement contract for running each new tool (zizmor / lychee / betterleaks) alongside its overlapping gate on the same scope: what is recorded, the redaction rule, the measurement window, and the keep / replace / drop decision rule. | #1618, #1610 | `scripts/measure_tool_overlap.py`; `metrics/duckdb/schema/v3/schema.sql`; `.github/workflows/measure-tool-overlap.yml`; `tests/test_measure_tool_overlap.py` |

## runbooks/ -- operator procedures

| File | Territory | Tracking issues | Companion |
|---|---|---|---|
| [README.md](runbooks/README.md) | Placement rules for operator procedures. | #202 | `docs/INDEX.md`; `docs/standards/documentation-quality.md` |
| [consumer-instruction-sync.md](runbooks/consumer-instruction-sync.md) | Downstream consumer procedure for importing the compiled `CLAUDE.md` / `AGENTS.md` as committed real files via a copyable sync workflow that fetches a tag-pinned release asset, verifies sha256, and opens a PR (no auto-merge). | #1678 | `.github/workflows/publish-instructions-release.yml`; `scripts/publish_instruction_release.py`; `docs/proposals/instruction-distribution-mechanism.md` |
| [rulesets.md](runbooks/rulesets.md) | Apply / verify / rollback runbook for `.github/rulesets/*.json` SoT. | #18 | `.github/workflows/apply-rulesets.yml`; `.github/workflows/verify-pr.yml` (`verify-ruleset-sync` job); `.github/workflows/weekly-maintenance.yml`; `scripts/rulesets_apply.py`; `scripts/ruleset_drift.py`; `scripts/verify_ruleset_sync.py` |
| [issue-triage.md](runbooks/issue-triage.md) | Label taxonomy and routing runbook readable from `labels.nodes[]` headers without fetching issue bodies. | #84, #34 | `.github/labels.json`; `.github/workflows/apply-labels.yml`; `scripts/labels_apply.py` |
| [branch-cleanup.md](runbooks/branch-cleanup.md) | Weekly survey of abandoned branches; currently dry-run only. | #31, #18 Phase 4-B | `.github/workflows/weekly-maintenance.yml`; `scripts/branch_cleanup.py` |
| [dependabot-automerge.md](runbooks/dependabot-automerge.md) | Audit-first Dependabot auto-merge policy gates. | #185 | `.github/dependabot-automerge.json`; `.github/workflows/dependabot-automerge.yml`; `.github/workflows/verify-pr.yml` (`verify-dependabot-labels` job); `scripts/dependabot_automerge.py`; `scripts/dependabot_labels.py` |
| [devcontainers.md](runbooks/devcontainers.md) | VS Code devcontainer entrypoints for Claude and Codex, with Nix-managed tool versions and egress allowlists. | #643 | `.devcontainer/**`; `flake.nix`; `flake.lock`; `scripts/nixpkgs_cooldown.py` |
| [devcontainer-tool-network-triage.md](runbooks/devcontainer-tool-network-triage.md) | Observe / evaluate / decide / verify procedure for a new tool's DNS and HTTP destinations before they are admitted to the egress allowlist, enforced by the inline-rationale gate. | #1170, #696 | `.devcontainer/network/*.allowlist`; `scripts/scan_allowlist_rationale.py`; `docs/standards/devcontainer-tooling.md`; `docs/runbooks/agent-provenance.md` |
| [rtk-hook-verification.md](runbooks/rtk-hook-verification.md) | Verify-first go/no-go procedure for the rtk auto-rewrite PreToolUse hook: mechanism, the Claude Code #15897 no-op risk against this repo's existing Bash gates at the pinned 2.1.154, push-gate safety analysis, live-session verification, and the post-PASS enablement checklist. | #1199, #1193 | `.devcontainer/config/claude/settings.json`; `.devcontainer/scripts/configure-agent-runtime.sh`; `flake.nix`; `scripts/preflight_push_base.py`; `scripts/preflight_hook_event_keys.py` |
| [workflow-permissions-audit.md](runbooks/workflow-permissions-audit.md) | Least-privilege matrix for every workflow (trigger, token / secret used, minimum permissions vs declared, mismatch follow-up). | #181, #178 | `.github/workflows/*.yml` (audit target); `scripts/scan_workflow_pip.py`; `scripts/scan_workflow_action_pins.py` |
| [workflow-permissions.md](runbooks/workflow-permissions.md) | Apply / verify / rollback runbook for the repo-level default workflow permissions setting (`GET/PUT /actions/permissions/workflow`), SoT in `.github/actions-permissions/workflow.json`, drift at the `detect-and-file` floor. | #1488, #178 | `.github/actions-permissions/workflow.json`; `.github/workflows/apply-rulesets.yml`; `.github/workflows/weekly-maintenance.yml`; `scripts/rulesets_apply.py`; `scripts/security_drift_report.py`; `.github/security-control-floor.toml` |
| [compromised-action-response.md](runbooks/compromised-action-response.md) | Emergency response for a compromised third-party action (Trivy included) or leaked workflow token: containment, image quarantine, revoke-then-reissue, revert-first recovery, post-incident retrospective. | #1264 | `.github/workflows/publish-devcontainer-images.yml`; `.github/workflows/dependabot-automerge.yml`; `scripts/dependabot_automerge.py`; `docs/runbooks/revert-first-rollback.md`; `docs/runbooks/devcontainers.md` |
| [security-control-drift-report.md](runbooks/security-control-drift-report.md) | Aggregator runbook for per-family drift detectors posting a single rolling comment on the MITRE ATT&CK tracker. | #180, #178 | `.github/workflows/weekly-maintenance.yml`; `scripts/security_drift_report.py` |
| [downstream-instruction-review-checklist.md](runbooks/downstream-instruction-review-checklist.md) | Security-focused review checklist for PRs that change instructions this repository ships to downstream consumers. | #183, #178 | `.github/workflows/verify-pr.yml` (`portable-pr-policy` job); `.github/PULL_REQUEST_TEMPLATE.md` (Bootstrap items) |
| [agent-provenance.md](runbooks/agent-provenance.md) | Provenance metadata and review criteria for skills, subagents, MCP servers, and comparable agent extensions. | #312, #63 | `docs/prd/security-control-inventory.md`; `docs/runbooks/downstream-instruction-review-checklist.md`; `docs/standards/repo-scope.md` |
| [attack-coverage-review-cadence.md](runbooks/attack-coverage-review-cadence.md) | Quarterly review cadence and comment template for the MITRE ATT&CK coverage tracker (#178). | #184, #178 | `.github/workflows/monthly-maintenance.yml` (`remind` job) |
| [ci-monitoring-polling-vs-webhook.md](runbooks/ci-monitoring-polling-vs-webhook.md) | Operator choice guide for polling and webhook-backed PR CI monitoring paths. | #781 | `scripts/post_pr_create_ci_monitor.py`; GitHub PR activity subscription |
| [issue-closure-fast-path.md](runbooks/issue-closure-fast-path.md) | Fast evidence loop for closing GitHub issues from direct merged-PR evidence. | #187 | `scripts/issue_closure_fast_path.py`; GitHub issue close tool calls |
| [measure-lint-pytest-timings.md](runbooks/measure-lint-pytest-timings.md) | Operator procedure for collecting and publishing verify-agents timing reports. | #545 | `.github/workflows/weekly-maintenance.yml`; `scripts/analyze_ci_timings.py` |
| [preflight.md](runbooks/preflight.md) | Local pre-push and manual preflight entrypoint mirroring PR-gating CI scripts. | #493 | `scripts/preflight_all.py`; `scripts/scan_preflight_drift.py`; `.githooks/pre-push` |
| [context7-mcp.md](runbooks/context7-mcp.md) | Operator procedure for the context7 MCP server declared in `apm.yml`: keyless default, optional API-key issuance and storage, and downstream `apm install` wiring. | #1188, #1190 | `apm.yml`; `README.md`; `docs/runbooks/agent-provenance.md` |
| [host-uv-pin.md](runbooks/host-uv-pin.md) | macOS rescue procedure for aligning uv across the VS Code workspace, Claude Desktop, and Codex Desktop entrypoints, including pinned execution of APM compile. | #1205, #1745 | `claude-md.code-workspace`; `.claude/settings.json`; `.codex/hooks.json`; `scripts/setup_pinned_uv.sh`; `scripts/session_uv_local_pin.sh`; `scripts/uv_pin.py` |
| [adding-a-workflow.md](runbooks/adding-a-workflow.md) | Pre-push two-step for landing a new GitHub Actions workflow (generate the if-branch diagram + register it in `docs/INDEX.md`, add a CLI contract test per workflow-invoked script) plus the token-cost-disclosure habit for multi-step or LLM-backed verification. | #1101, #1100, #1099 | `scripts/workflow_diagram.py`; `tests/test_workflow_cli_contracts.py`; `scripts/scan_docs_inventory.py`; `docs/runbooks/preflight.md` |
| [replacement-pr-preflight.md](runbooks/replacement-pr-preflight.md) | Guardrail for closing a PR and opening a replacement for the same issue or session. | #632 | `scripts/preflight_replacement_pr.py` |
| [retro-labels.md](runbooks/retro-labels.md) | Operator runbook for `retro:*` labels that classify retrospective true/false positives and feed the auto-retro prior. | #558, #582 | `scripts/_retro_labels.py`; `scripts/scan_retro_followup_drift.py`; `.github/workflows/daily-maintenance.yml` (`scan` job) |
| [retrospective-noise-flooding-procedure.md](runbooks/retrospective-noise-flooding-procedure.md) | Operator procedure for reviewing retrospective and auto-retro flooding signal vs noise. | #315, #63 Phase 8(D-3) | `.github/workflows/post-merge.yml`; `scripts/auto_retro.py`; `docs/archive/retrospective-pr-*.md` (subject) |
| [auto-retrospective-automation.md](runbooks/auto-retrospective-automation.md) | Operator entry point for the auto-retro pipeline: trigger surface, issue-body template, skip/idempotency rules, run verification, and the relocated pause/resume + revert procedure. | #1454, #149 | `.github/workflows/post-merge.yml`; `scripts/auto_retro.py`; `scripts/_trusted_bots.py`; `docs/prd/privileged-operation-runbooks.md` (section 9 contract) |
| [prek.md](runbooks/prek.md) | `j178/prek` install steps, configured hooks, and the CI gate that runs `prek run --all-files` on every PR. | #408 | `.pre-commit-config.yaml`; `.github/workflows/verify-agents.yml` (`prek` job); `scripts/uv_pin.py`; `scripts/scan_workflow_pip.py` |
| [readme-translation-drift.md](runbooks/readme-translation-drift.md) | Deterministic gate that fails a PR when `README.md` changes without matching `README.ja.md` / `README.zh.md` updates, plus the opt-out marker procedure. | #476 | `scripts/verify_readme_translation.py`; `.github/workflows/verify-pr.yml` (`portable-pr-policy` job); `README.md`; `README.ja.md`; `README.zh.md` |
| [update-pr-branch-recovery.md](runbooks/update-pr-branch-recovery.md) | Recovery procedure for when a PR branch falls behind `main`; replaces the blocked `mcp__github__update_pull_request_branch` with a new-branch-from-main approach. | #893 | `scripts/gate_update_pr_branch.py` |
| [revert-first-rollback.md](runbooks/revert-first-rollback.md) | Default-to-`git revert` procedure for rollback / undo intents: identifying the commit/PR set, revert ordering, tree-parity verification, and the conditions that justify a manual fallback. Knowledge source for the planned rollback skill. | #1020 | `.apm/instructions/master.instructions.md` (section 3) |
| [pre-merge-retro-survey.md](runbooks/pre-merge-retro-survey.md) | Claude-only `Stop` (handoff) gate that blocks end-of-turn until a satisfaction-first, scenario-branched retro survey runs via `AskUserQuestion` for each PR the session created, with a Mermaid diagram of the branching flow and a non-interactive `--satisfaction`/`--problem` fallback for when the `AskUserQuestion` confirm cannot be submitted. | #1073, #1081 | `scripts/gate_handoff_retro_survey_askuserquestion.py`; `.claude/settings.json`; `scripts/gate_decision_handoff_askuserquestion.py` |
| [refresh-behind-pr.md](runbooks/refresh-behind-pr.md) | Deterministic, agent-agnostic path for the behind and conflict-free case: local `git merge origin/<base>` plus a plain push (fast-forward, flattened by the squash-merge), no force-push and no `update_pull_request_branch`. | #1361, #893 | `scripts/refresh_pr_branch.py`; `scripts/check_pr_mergeability.py`; `docs/runbooks/update-pr-branch-recovery.md` |
| [merge-readiness-loop.md](runbooks/merge-readiness-loop.md) | The agent-agnostic open-PR to just-before-merge loop (CI monitor, mergeability, behind-refresh) and the deterministic harness pieces that keep each step identical across Claude, Codex, and Devin. | #1361, #1359 | `scripts/agent_hooks_source.json`; `scripts/post_pr_create_ci_monitor.py`; `scripts/check_pr_mergeability.py`; `scripts/refresh_pr_branch.py`; `docs/runbooks/refresh-behind-pr.md` |
| [pr-body-policy-recovery.md](runbooks/pr-body-policy-recovery.md) | Approved recovery for a PR body that fails a body-policy gate after open: edit the body for a fresh `edited` event instead of re-running the stale run, never add an empty retrigger commit, and a decision tree mapping symptom to repair. | #675 | `scripts/preflight_pr_body.py`; `scripts/preflight_push_nonempty.py`; `.github/workflows/verify-pr.yml`; `docs/runbooks/replacement-pr-preflight.md` |
| [parallel-agent-dispatch.md](runbooks/parallel-agent-dispatch.md) | Operating procedure for dispatching parallel agents when the work is clear-responsibility, individually simple, high-volume, and independent (not when one change is complex): the two-mode decision (independent domains -> concurrent; same workspace -> sequential or worktree-isolated), the worktree path that recovers concurrency, and the integration step. | #1709, #226 | `.agents/skills/dispatching-parallel-agents/SKILL.md`; `.agents/skills/subagent-driven-development/SKILL.md`; `.agents/skills/using-git-worktrees/SKILL.md`; `CLAUDE.md` (section 3) |

## generated/ -- checked-in generated views

### generated/scripts/ -- per-script AST graphs

`generated/scripts/ast/<stem>.md` holds one Mermaid AST control-flow doc per
`scripts/*.py` file, `generated/scripts/dependency-graph.md` holds the
sibling-import dependency graph across those scripts,
`generated/scripts/trigger-map.md` reverse-maps where each script is launched
from (workflow `run:` steps, pre-commit, `preflight_all.py` Step argv, agent
hooks) and lists dead-script candidates, plus
`generated/scripts/auto-retro-triage-report.md`, the live retro-issue snapshot.
This folder is owned by the post-merge automation
(the `decision-tree` job in `.github/workflows/post-merge.yml`); it is not
hand-editable and is exempt from per-file INDEX linking (a non-bot edit fails
`scripts/gate_generated_scripts_manual_edit.py`). Sources:
`python3 scripts/script_ast_graph.py all-doc` (per-script AST),
`python3 scripts/script_dependency_graph.py all-doc` (dependency graph),
`python3 scripts/script_trigger_map.py all-doc` (trigger reverse-map), and
`python3 scripts/auto_retro.py triage-report` (triage snapshot).
Tracking issues: #598, #605, #960, #1540, #1543, #1546.

### generated/workflows/ -- workflow if-branch diagrams

`generated/workflows/<name>-if-branches.md` holds one Mermaid if-branch diagram
per `.github/workflows/<name>.yml`. Each diagram shows job-level `if:`
conditions, `needs:` dependency edges, and step-level `if:` branches.
This folder is owned by the post-merge automation
(the `decision-tree` job in `.github/workflows/post-merge.yml`); it is not
hand-editable and is exempt from per-file INDEX linking (a non-bot edit fails
`scripts/gate_generated_scripts_manual_edit.py`). Listing each file here would
drift as workflows are added or removed, so the directory is described once and
skipped by `scripts/scan_docs_inventory.py`.
Source: `python3 scripts/workflow_diagram.py diagram-doc`.
Tracking issues: #960, #1613.

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
| [renovate-evaluation.md](archive/renovate-evaluation.md) | DECLINED (#1014) evaluation of switching Dependabot to Mend Renovate, with the one-shot cutover migration sketch and phased sub-issue chain (#280-#284, superseded). Retained as the record of the evaluation; references the pre-consolidation workflow names in its migration sketch as historical state. |
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
