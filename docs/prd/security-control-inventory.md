# Security Control Inventory

> Design rationale: see [`docs/prd/agent-rules-design-philosophy.md`](./agent-rules-design-philosophy.md). This inventory supplies the concrete harness-lane evidence that the meta-doc's responsibility matrix references for principle P3.

Baseline inventory of security-relevant repository surfaces, mapped to the MITRE ATT&CK coverage table in [#178](https://github.com/tvna/claude-md/issues/178). For each surface this document records the existing defense, the evidence that proves the defense is operational, a coverage status, and the follow-up issue tracking any gap.

This file is the deliverable for [#179](https://github.com/tvna/claude-md/issues/179). It is intended to be re-read whenever a new workflow, script, ruleset, or runbook lands so the coverage table in #178 stays accurate. Re-verification command is at the bottom of the file.

## How to read this document

- **Surface** — exact path. Every file under the [#179 scope](https://github.com/tvna/claude-md/issues/179) is represented in exactly one section (its primary section); secondary appearances are cross-referenced, not duplicated.
- **ATT&CK tactic(s)** — abbreviated codes from #178's table. See *Tactic abbreviations* below.
- **Existing defense** — the deterministic check, gate, or runbook that defends this surface today.
- **Evidence** — the file, test, workflow, or runbook that proves the defense is in place. Internal repo paths are bare; GitHub issues use `#NNN`.
- **Status**
  - `covered` — defense is operational, evidence is current, and no follow-up gap is needed.
  - `partially covered` — defense exists but at least one dimension (least-privilege audit, scheduled drift detection, documented rollback, dry-run, log redaction, downstream review) is incomplete. A follow-up issue tracks the gap.
  - `not covered` — no defense beyond default GitHub controls. A follow-up issue is mandatory.
  - `not applicable` — surface is not security-relevant; included only because the #179 verification rg keyword matched incidentally.
- **Gap** — issue number(s) for tracked follow-up. Existing issues are reused per #178's "Existing related issues reused instead of duplicated" rule. No new issues are opened by this inventory; novel gaps would be added here by a follow-up PR.

### Tactic abbreviations

| Code | ATT&CK tactic |
|---|---|
| `Recon` | Reconnaissance |
| `RD` | Resource Development |
| `IA` | Initial Access |
| `Exec` | Execution |
| `Persist` | Persistence |
| `PrivEsc` | Privilege Escalation |
| `DE` | Defense Evasion |
| `Cred` | Credential Access |
| `Disc` | Discovery |
| `LM` | Lateral Movement |
| `Coll` | Collection |
| `C2` | Command and Control |
| `Exfil` | Exfiltration |
| `Impact` | Impact |

## 1. GitHub Actions workflows (`.github/workflows/`)

| Surface | ATT&CK | Existing defense | Evidence | Status | Gap |
|---|---|---|---|---|---|
| `apply-labels.yml` | PrivEsc, Impact | Manual `workflow_dispatch` only; `main` ref guard; `labels-apply` Environment scopes `LABELS_PAT`; mandatory `dry_run` input default, `prune` opt-in. | `docs/runbooks/issue-triage.md`, `scripts/labels_apply.py`, `tests/test_labels_apply.py` | partially covered | #181 (perms audit), #182 (privileged-op runbook) |
| `apply-rulesets.yml` | PrivEsc, IA, Impact | Manual dispatch on `main` only; `ruleset-apply` Environment scopes `RULESETS_PAT`; per-file JSON validation; ruleset selector + `dry_run` + opt-in `enable_auto_delete`. | `docs/runbooks/rulesets.md`, `scripts/rulesets_apply.py`, `tests/test_rulesets_apply.py` | partially covered | #56 (PAT handling), #181, #182 |
| `branch-cleanup.yml` | Impact | Weekly scheduled survey with `contents: read` at top level; survey-only mode (no deletion); rolling summary issue serves as audit log. | `docs/runbooks/branch-cleanup.md`, `scripts/branch_cleanup.py`, `tests/test_branch_cleanup.py` | covered | — |
| `dependabot-automerge.yml` | RD, Persist | `pull_request_target` gated by audit script reading `dependabot-automerge.json` allowlist; severity/threat labels block auto-merge. | `docs/runbooks/dependabot-automerge.md`, `scripts/dependabot_automerge.py`, `tests/test_dependabot_automerge.py`, #185 | covered | — |
| `generate-agents.yml` | Persist, LM | Scheduled + dispatch compile; drift check via `git diff --exit-code` on `CLAUDE.md` / `AGENTS.md`; opens PR rather than push direct. | `.apm/instructions/master.instructions.md`, `verify-apm.yml`, #112 | partially covered | #183 (downstream review checklist) |
| `ruleset-drift.yml` | Persist, IA | Weekly + dispatch drift detection vs `.github/rulesets/`; opens an issue when drift is detected. | `scripts/ruleset_drift.py`, `tests/test_ruleset_drift.py`, `docs/runbooks/rulesets.md` | covered | #120 (required-checks-vs-ruleset sync, separate scope) |
| `scan-non-ascii.yml` | DE, Coll, Persist | Write-side scan of issues / PRs / comments; closes / requests-changes / labels; excludes trusted bots. | `docs/prd/non-ascii-defense.md`, `scripts/scan_non_ascii.py`, `tests/test_scan_non_ascii.py`, #102 | covered | — |
| `security-control-drift-report.yml` | Persist, Impact | Weekly + dispatch aggregator: reuses each per-family detector in read-only mode (`ruleset_drift.py detect`, `labels_apply.py plan`, `apm compile` + diff, `uv_pin.py drift` / `stale`) and posts a rolling comment on parent #178. Never opens new issues. | `scripts/security_drift_report.py`, `tests/test_security_drift_report.py`, `docs/runbooks/security-control-drift-report.md`, #180 | covered | — |
| `threat-intel-triage.yml` | Coll, Recon | Deterministic OSV + GHSA + OSSF malicious-packages + CISA KEV lookup over PyPI and GitHub Actions surfaces (including `uv run --with pkg==ver` transient pins in workflows / `scripts/`), plus FIRST EPSS exploit-prediction enrichment (advisory-only, never escalates `threat:response-needed`); routes labels (`threat:intel-needed`, `threat:response-needed`) before any agent. | `scripts/threat_intel_triage.py`, `tests/test_threat_intel_triage.py`, `docs/runbooks/issue-triage.md`, #170, #173, #175, #176 | partially covered | #170 (sustained ops), #63 (agent-boundary review) |
| `verify-agents.yml` | RD, Persist, Exec | PR gate: APM compile drift, `lint-uv-pin` (drift + upstream staleness), aggregated required check for ruleset. | `scripts/uv_pin.py`, `tests/test_uv_pin.py`, `docs/standards/remote-environment.md`, #112 | covered | — |
| `verify-apm.yml` | Persist, LM | PR gate: portability scan then `apm compile` + byte-for-byte diff of `CLAUDE.md` / `AGENTS.md`; `--exclude-newer "14 days"` prevents transient package noise. Replaces deleted `verify-apm-drift.yml` and `verify-apm-portability.yml` per #468 (one checkout + one uv install shared). | `.apm/instructions/master.instructions.md`, `CLAUDE.md`, `AGENTS.md`, `scripts/scan_apm_portability.py` | partially covered | #183 (downstream review checklist) |
| `verify-dependabot-labels.yml` | RD | Static cross-check that `dependabot.yml` labels resolve in `labels.json`. | `scripts/dependabot_labels.py`, `tests/test_dependabot_labels.py` | covered | — |
| `verify-github-content.yml` | IA, DE, RD | PR + issue gate: title ASCII / format, body section structure, body issue-link (PR only). Replaces deleted `verify-title-policy.yml`, `verify-body-policy.yml`, and `verify-issue-link.yml` per #468 (one checkout shared). Body-policy gained a stable required-check context under this gate. | `scripts/title_policy.py`, `scripts/body_policy.py`, `scripts/issue_link.py`, `docs/standards/issue-pr-body-standard.md`, `docs/prd/non-ascii-defense.md` | covered | — |

Notes:

- No workflow has a per-job widening that grants `contents: write` beyond what its job needs except `verify-agents.yml` (verify job: `contents: write`, `pull-requests: write`). That widening is the surface #181 will audit explicitly.
- Every privileged-mutation workflow (`apply-labels.yml`, `apply-rulesets.yml`) is dispatch-only on `main` with an Environment-scoped PAT; no PAT is stored at repo level.

## 2. Branch rulesets (`.github/rulesets/`)

| Surface | ATT&CK | Existing defense | Evidence | Status | Gap |
|---|---|---|---|---|---|
| `main.json` | IA, Persist, Impact | Default-branch ruleset: 3 required status checks (`Verify agent instructions / gate`, `Verify issue link / gate`, `Verify title policy / gate`); blocks force-push; requires PR + linear history + resolved threads + code-owner review; squash-only merge; blocks deletion. | `docs/runbooks/rulesets.md`, `ruleset-drift.yml`, #18, #27, #120 | partially covered | #120 (required-checks-vs-ruleset live sync) |
| `all-branches.json` | IA, Impact | Non-default branch ruleset: blocks force-push on every branch except the default branch; deletion intentionally NOT blocked (relies on `delete_branch_on_merge: true`). | `docs/runbooks/rulesets.md`, `docs/runbooks/branch-cleanup.md`, #27, #59 | covered | — |
| `dependabot.json` | IA, RD | `dependabot/*` ruleset: blocks force-push; no bypass actors. (Originally granted Dependabot Integration `actor_id: 49699333` a bypass per #140, but GitHub deprecated the standalone Dependabot GitHub App and the Rulesets API rejects that bypass actor — see #273. The admin `RepositoryRole` bypass was also removed across all three rulesets.) | `docs/runbooks/rulesets.md`, #18, #273 | partially covered | #273 (no automation can rebase `dependabot/*` branches; Dependabot falls back to close + reopen) |

Notes:

- `bypass_actors` is `[]` on all three rulesets — the "Merge without waiting for requirements" UI path is unreachable. Emergency escape requires the [Emergency disable / re-enable procedure](../runbooks/rulesets.md#emergency-disable--re-enable-procedure), which leaves `repository_ruleset.update` audit events and is detected by `ruleset-drift.yml` if the re-enable step is forgotten.
- The drift gate is `ruleset-drift.yml`; the cross-family aggregator `security-control-drift-report.yml` (#180) wires that drift output into #178 as evidence rather than duplicating the detector.

## 3. Label source of truth (`.github/labels.json`)

| Surface | ATT&CK | Existing defense | Evidence | Status | Gap |
|---|---|---|---|---|---|
| `.github/labels.json` | Persist, IA, Coll | JSON SoT; mutated only via `apply-labels.yml` with `dry_run` default; `verify-dependabot-labels.yml` ensures Dependabot label references stay resolvable; scheduled drift surfaced by `security-control-drift-report.yml` (#180). | `docs/runbooks/issue-triage.md`, `apply-labels.yml`, `verify-dependabot-labels.yml`, `security-control-drift-report.yml`, #84 | partially covered | #84 Phase 5 (label drift + coverage check) |

## 4. APM source and compiled instructions

| Surface | ATT&CK | Existing defense | Evidence | Status | Gap |
|---|---|---|---|---|---|
| `.apm/instructions/master.instructions.md` | LM, Persist, Exec | Single APM source. PR gate `verify-apm.yml` recompiles and diffs the output files; PR review on every change. | `verify-apm.yml`, `generate-agents.yml`, `CLAUDE.md`, `AGENTS.md` | partially covered | #183 (downstream review checklist) |
| `CLAUDE.md` | LM, Persist | Compiled output; drift-gated by `verify-apm.yml`; not hand-edited (compiled by `apm-cli==0.12.1`). | `verify-apm.yml`, `.apm/instructions/master.instructions.md`, #112 | covered | — |
| `AGENTS.md` | LM, Persist | Compiled output; drift-gated by `verify-apm.yml`; byte-identical compile to `CLAUDE.md` today. | `verify-apm.yml`, `.apm/instructions/master.instructions.md` | covered | — |

## 5. Dependency files and bump policy

| Surface | ATT&CK | Existing defense | Evidence | Status | Gap |
|---|---|---|---|---|---|
| `pyproject.toml` | RD, Exec, C2 | `[tool.uv].required-version` exact pin; `pyyaml` range pin used only by SessionStart hook; `lint-uv-pin` drift gate enforces single source of truth. | `scripts/uv_pin.py`, `tests/test_uv_pin.py`, `verify-agents.yml`, `docs/standards/remote-environment.md`, #106, #112 | covered | — |
| `uv.lock` | RD, Exec, C2 | Locked transitive snapshot; CI uses `uv sync --locked`; Dependabot weekly bumps; OSV + KEV scanning via `threat-intel-triage.yml`. | `verify-agents.yml`, `verify-apm.yml`, `threat-intel-triage.yml`, `.github/dependabot.yml` | covered | — |
| `.github/dependabot.yml` | RD, Persist | Two ecosystems (`github-actions`, `uv`); cooldown (default 7d, major 30d, minor 7d, patch 3d); auto-assigns `dependencies` label; `verify-dependabot-labels.yml` cross-checks against `labels.json`. | `dependabot-automerge.yml`, `verify-dependabot-labels.yml`, #185, #221 | covered | — |

## 6. Scripts (`scripts/`)

**Cross-cutting static security gate (#190).** Every script in this section
is covered by the `S` (flake8-bandit) rule family in `[tool.ruff.lint]`,
run by the `lint-scripts` job in `.github/workflows/verify-agents.yml`
as part of the existing `ruff check scripts tests` step. The gate
flags `subprocess` shell injection, hardcoded `/tmp` paths, `urllib`
opens against attacker-controllable schemes, and assertions used as
production guards. Suppressions are inline (`# noqa: S<NNN>`) with a
one-line justification on the preceding comment; test-suite-wide
patterns (`assert`, dummy tokens) are scoped via
`[tool.ruff.lint.per-file-ignores]`. Pinned by
`tests/test_ruff_security_gate.py`, which also verifies the gate
rejects a deliberately unsafe sample.

| Surface | ATT&CK | Existing defense | Evidence | Status | Gap |
|---|---|---|---|---|---|
| `_github_api.py` | Cred, Exec | Shared HTTP wrapper; token passed as parameter (never logged); retry with jitter. | `tests/test_github_api.py` | covered | — |
| `_trusted_bots.py` | RD, Coll | Static allowlist of trusted bot logins; consumed by `scan_non_ascii.py` and PR-body checks. | `docs/standards/issue-pr-body-standard.md`, `docs/prd/non-ascii-defense.md` | covered | — |
| `body_policy.py` | DE, RD | Validates issue/PR body section structure with cutoff date; pure function, no network. | `tests/test_body_policy.py`, `verify-github-content.yml`, #206 | covered | — |
| `branch_cleanup.py` | Impact, Persist | Survey-only; creates/edits rolling issue; `dry_run` default; bounded age threshold; tested age boundaries. | `tests/test_branch_cleanup.py`, `branch-cleanup.yml`, `docs/runbooks/branch-cleanup.md` | partially covered | #182 (privileged-op runbook for future deletion path) |
| `dependabot_automerge.py` | RD, Persist | Audit-only; no mutation; reads policy from `dependabot-automerge.json`; tested against representative fixtures. | `tests/test_dependabot_automerge.py`, `docs/runbooks/dependabot-automerge.md` | covered | — |
| `dependabot_labels.py` | RD, DE | Static label-resolution check; no network; no mutation. | `tests/test_dependabot_labels.py`, `verify-dependabot-labels.yml` | covered | — |
| `install-uv.sh` | Exec, C2, Persist | Idempotent SessionStart hook; no-op outside `CLAUDE_CODE_REMOTE`; reads pin from `pyproject.toml`; fetches astral-sh/uv release only. | `docs/standards/remote-environment.md`, `.claude/settings.json` (carve-out), #106, #109, #112 | partially covered | no paired automated test for the shell script (manual verification documented); see `docs/standards/remote-environment.md` *Verification* section. Tracked under #112 follow-up notes. |
| `issue_link.py` | IA, DE | PR gate; validates issue references via same-repo `gh api`; applies advisory labels. | `tests/test_issue_link.py`, `verify-github-content.yml`, `docs/standards/issue-pr-body-standard.md` | covered | — |
| `labels_apply.py` | PrivEsc, Impact, Exfil | Plan / dry-run / apply tri-state; PAT scoped to `labels-apply` Environment; prune is opt-in and DELETE-aware; outputs human-readable diff. | `tests/test_labels_apply.py`, `apply-labels.yml`, `docs/runbooks/issue-triage.md` | partially covered | #181, #182 |
| `plan_language_context.py` | Coll, LM | SessionStart hook; reads `.github/owners.yaml` and emits language policy; no mutation, no network. | `tests/test_plan_language_context.py`, `docs/standards/repo-scope.md`, #211 | covered | — |
| `pr_body_close_keyword_gate.py` | IA, DE | PreToolUse hook; client-side mirror of the issue-link step inside `verify-github-content.yml` (Refs-only / tracking-label / `<!-- partial -->` gate); blocks `mcp__github__(create_pull_request\|update_pull_request)` with a `permissionDecision: "deny"` JSON; fail-closed when `GH_TOKEN` is unset so the local outcome cannot be looser than the server gate. | `tests/test_pr_body_close_keyword_gate.py`, `docs/standards/issue-pr-body-standard.md`, #219, #222 | covered | — |
| `preflight_non_ascii.py` | DE, LM, Cred | PreToolUse hook that blocks non-ASCII in `mcp__github__*` write tool inputs; shares scanner with `scan_non_ascii.py`. | `docs/prd/non-ascii-defense.md`, #102, #146 | partially covered | no dedicated test file; coverage rides on `scan_non_ascii.py`. Tracked under #102 follow-up notes. |
| `ruleset_drift.py` | Persist, IA | Compares live rulesets to SoT JSON; files an issue when drift is detected; reads `GH_TOKEN_API`. | `tests/test_ruleset_drift.py`, `ruleset-drift.yml`, `docs/runbooks/rulesets.md` | covered | — |
| `rulesets_apply.py` | PrivEsc, IA, Impact | Plan / dry-run / apply tri-state; PAT scoped to `ruleset-apply` Environment; opt-in `enable_auto_delete`; outputs ruleset-by-ruleset diff. | `tests/test_rulesets_apply.py`, `apply-rulesets.yml`, `docs/runbooks/rulesets.md` | partially covered | #56, #181, #182 |
| `scan_non_ascii.py` | DE, Coll, Persist, Cred | Write-side scanner; closes / requests-changes / labels; trusted-bot allowlist; respects body section boundaries. | `tests/test_scan_non_ascii.py`, `scan-non-ascii.yml`, `docs/prd/non-ascii-defense.md`, #102 | covered | — |
| `security_drift_report.py` | Persist, Impact | Aggregator: parses captured exit codes / outputs of the per-family detectors and emits a single Markdown report; posts / updates a rolling comment on parent #178 via `_github_api.apply_call`. Never opens new issues; never mutates per-family state. | `tests/test_security_drift_report.py`, `security-control-drift-report.yml`, `docs/runbooks/security-control-drift-report.md`, #180 | covered | — |
| `threat_intel_triage.py` | Coll, Recon, RD | Deterministic OSV.dev + GHSA + OSSF malicious-packages + CISA KEV lookup with FIRST EPSS advisory-only enrichment (CVE-keyed score / percentile); dependency surfaces cover `uv.lock`, `pyproject.toml`, `.github/workflows/*.yml` `uses:` (`GitHub Actions` ecosystem), and `uv run --with pkg==ver` transient pins in workflows / `scripts/`; fixture inputs for offline tests; applies / removes labels only. EPSS lookups soft-fail so a transient FIRST API outage cannot block the KEV/OSV/GHSA/OSSF routing decision. | `tests/test_threat_intel_triage.py`, `threat-intel-triage.yml`, `docs/runbooks/issue-triage.md`, #170, #173, #175, #176 | partially covered | #170 |
| `title_policy.py` | DE, RD | ASCII / format validator for issue and PR titles; pure function. | `tests/test_title_policy.py`, `verify-github-content.yml`, `docs/prd/non-ascii-defense.md` | covered | — |
| `uv_pin.py` | RD, Exec, C2 | Single source of truth for the `uv` pin; drift + upstream-staleness check; emits annotations rather than mutating files. | `tests/test_uv_pin.py`, `verify-agents.yml`, `docs/standards/remote-environment.md`, #112 | covered | — |

## 7. Documentation / runbooks (`docs/`)

| Surface | ATT&CK | Existing defense | Evidence | Status | Gap |
|---|---|---|---|---|---|
| `docs/runbooks/branch-cleanup.md` | Impact, Disc | Documents weekly survey workflow, dispatch inputs, age threshold, dry-run default, rollback path (re-create branch from issue note). | `branch-cleanup.yml`, `scripts/branch_cleanup.py`, #31 | covered | — |
| `docs/runbooks/dependabot-automerge.md` | RD, Persist | Documents allowlist policy and labels that veto auto-merge; references audit script. | `dependabot-automerge.yml`, `scripts/dependabot_automerge.py`, #185 | covered | — |
| `docs/standards/issue-pr-body-standard.md` | DE, RD, IA | Documents body section requirements; trusted-bot carve-out; advisory hook integration. | `verify-github-content.yml`, `scripts/body_policy.py`, `scripts/pr_body_close_keyword_gate.py`, #206 | covered | — |
| `docs/runbooks/issue-triage.md` | Coll, Recon, Persist, PrivEsc | Documents label taxonomy, `LABELS_PAT` Environment scope, apply workflow, prune semantics, manual verification. | `apply-labels.yml`, `.github/labels.json`, #84 | partially covered | #181, #182 |
| `docs/runbooks/agent-provenance.md` | RD, Exec, LM, C2 | Documents minimum provenance metadata, permission review, update cadence, and rollback expectations before adopting or updating skills, subagents, MCP servers, or comparable agent extensions. | #63, #312, `docs/agent-provenance.md` | covered | — |
| `docs/prd/non-ascii-defense.md` | DE, LM, Cred, Coll | Documents three-layer non-ASCII defense (past sanitization, write-side workflow + PreToolUse, read-side PostToolUse); rollback steps. | `scan-non-ascii.yml`, `scripts/scan_non_ascii.py`, `scripts/preflight_non_ascii.py`, #102, #146 | covered | — |
| `docs/standards/performance-metrics.md` | RD | Design-only doc; no operational control today; no privileged data. | #61, #58 | not applicable | — |
| `docs/standards/remote-environment.md` | Exec, C2, Persist | Documents SessionStart hook, uv pin propagation, verification commands, rollback procedure, outbound-network expectations. | `scripts/install-uv.sh`, `.claude/settings.json`, `scripts/uv_pin.py`, #106, #109, #112 | covered | — |
| `docs/standards/repo-scope.md` | LM, Exec | Documents the `.claude/settings.json` carve-out and the prohibition on per-agent tool config (`.codex/`, etc.). | `docs/standards/remote-environment.md`, #109 | covered | — |
| `docs/runbooks/rulesets.md` | PrivEsc, IA, Impact, Disc | Documents `RULESETS_PAT` scope, ruleset apply / verify / rollback orchestration, dispatch authorization, audit-log expectations. | `apply-rulesets.yml`, `ruleset-drift.yml`, `scripts/rulesets_apply.py`, #18, #27, #56 | partially covered | #56, #182 |
| `docs/runbooks/security-control-drift-report.md` | Persist, Impact | Documents the scheduled aggregator (#180): trigger, families covered, families pending, rolling-comment marker, dry-run preview, per-row investigation steps, rollback. | `security-control-drift-report.yml`, `scripts/security_drift_report.py`, #178, #180 | covered | — |

## Cross-reference: ATT&CK tactic → surface coverage

This table answers, for each row of #178's coverage table: which surfaces in this inventory contribute to the defense, and what is the aggregate status. It is the bridge between this inventory and the #178 coverage table.

| ATT&CK | Contributing surfaces | Aggregate status | Gap |
|---|---|---|---|
| Recon | `docs/runbooks/issue-triage.md`, `docs/runbooks/rulesets.md`, `docs/standards/remote-environment.md`, `threat_intel_triage.py` | partially covered | #170, #181 (no scheduled secret scan beyond GitHub default) |
| RD | `verify-github-content.yml`, `scan-non-ascii.yml`, `.github/dependabot.yml`, `uv.lock`, `pyproject.toml`, `dependabot.json` ruleset, `docs/runbooks/agent-provenance.md` | covered | — |
| IA | `main.json`, `all-branches.json`, `dependabot.json`, `verify-github-content.yml`, `ruleset-drift.yml` | partially covered | #120 |
| Exec | `verify-agents.yml`, `verify-apm.yml`, `install-uv.sh`, `pyproject.toml`, `uv.lock`, `.claude/settings.json` carve-out, `docs/runbooks/agent-provenance.md` | partially covered | #181 (workflow `permissions:` audit) |
| Persist | `verify-apm.yml`, `ruleset-drift.yml`, `apply-labels.yml`, `apply-rulesets.yml`, `verify-github-content.yml`, `security-control-drift-report.yml` | covered | — |
| PrivEsc | `apply-labels.yml`, `apply-rulesets.yml`, `ruleset-drift.yml`, `docs/runbooks/issue-triage.md`, `docs/runbooks/rulesets.md` | partially covered | #56, #181 |
| DE | `verify-github-content.yml`, `scan-non-ascii.yml`, `verify-apm.yml`, `preflight_non_ascii.py` | covered | — |
| Cred | `scan-non-ascii.yml`, `preflight_non_ascii.py`, `docs/runbooks/rulesets.md`, `docs/runbooks/issue-triage.md` (Environment-scoped PATs) | partially covered | #181 (log redaction audit) |
| Disc | `docs/runbooks/rulesets.md`, `docs/runbooks/issue-triage.md`, `docs/runbooks/branch-cleanup.md`, `docs/standards/remote-environment.md` | covered | — |
| LM | `.apm/instructions/master.instructions.md`, `CLAUDE.md`, `AGENTS.md`, `verify-apm.yml`, `generate-agents.yml`, `docs/runbooks/agent-provenance.md` | partially covered | #183 |
| Coll | `scan-non-ascii.yml`, `threat-intel-triage.yml`, `_trusted_bots.py`, `docs/prd/non-ascii-defense.md` | partially covered | #63, #102 |
| C2 | `install-uv.sh`, `threat_intel_triage.py`, `generate-agents.yml`, `uv.lock`, `pyproject.toml`, `docs/runbooks/agent-provenance.md` | covered | — |
| Exfil | `apply-labels.yml`, `apply-rulesets.yml`, `ruleset-drift.yml`, `docs/runbooks/rulesets.md`, `docs/runbooks/branch-cleanup.md` | partially covered | #181, #182 |
| Impact | `apply-labels.yml`, `apply-rulesets.yml`, `branch-cleanup.yml`, `ruleset-drift.yml`, `main.json`, `all-branches.json` | partially covered | #182 |

## Gap summary

Follow-up issues this inventory references:

| Issue | Scope (per its body) |
|---|---|
| #56 | Ruleset PAT handling and privileged-dispatch hardening |
| #63 | Residual workflow risk, prompt-injection boundary, tool surface, supply chain |
| #102 | Multi-byte / non-ASCII prompt-injection hardening |
| #120 | Required-checks vs live ruleset synchronization |
| #170 | Sustained external threat-intelligence triage operations |
| #180 | Scheduled drift reporting across control families (closed by `security-control-drift-report.yml`) |
| #181 | Workflow permissions and PAT audit (least privilege matrix) |
| #182 | Privileged-operation runbook checklist (dry-run / authorization / rollback / audit) |
| #183 | Downstream instruction review checklist |
| #184 | ATT&CK review cadence on #178 |
| #312 | Agent extension provenance runbook for skills, subagents, MCP servers, and comparable extensions |

No new follow-up issues are opened by this inventory: every gap identified above maps to one of the issues in the table. If a future review surfaces a gap that does not fit any of these, append it to this file and open a new issue then.

Surfaces explicitly marked `not applicable`:

- `docs/standards/performance-metrics.md` — design-only doc, no operational control.

## Re-verification

The exact command from #179's *Verification* section:

```bash
rg -n "PAT|secret|token|bypass|permissions|workflow_dispatch|audit log|rollback|hook|uv|ruleset|label|APM|AGENTS|CLAUDE" docs .github scripts .apm pyproject.toml uv.lock
```

Expected behavior:

- Every distinct file that matches the keywords and is part of #179's scope is represented in exactly one of sections 1-7 above. Matches inside `uv.lock` (locked package metadata) and inside ASCII translation fixtures count as one surface — `uv.lock` — and are covered under section 5.
- A match in a file already represented in this inventory under its primary section is acceptable and does not require a new entry.
- A match in a file NOT represented here is a defect in this inventory and should be added by a PR that closes #179 follow-up.

Reviewers should also confirm:

- `ls .github/workflows/` matches the 15 rows in section 1.
- `ls .github/rulesets/` matches the 3 rows in section 2.
- `ls scripts/` matches the 19 rows in section 6 (`__pycache__` is excluded; not security-relevant).
- `ls docs/` matches the 11 rows in section 7.

Closes #179.
