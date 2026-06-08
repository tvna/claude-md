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

### Scheduled-detection floor

Every control family that has a scheduled drift detector MUST meet the
`detect-and-file` floor: detection runs on the weekly cron AND an actionable
drift auto-files a per-family issue (not only a rolling comment). The floor is
declared machine-readably in [`.github/security-control-floor.toml`](../../.github/security-control-floor.toml)
and enforced by `scripts/verify_security_control_floor.py` in the
`lint-scripts-static` job of `verify-agents.yml`, so a new family cannot land
below the floor on reviewer memory alone. A family may sit below the floor only
with an explicit `exempt_reason` (advisory-only signals such as
`uv-pin-staleness`, where a weekly issue would be noise). The `rulesets` family
files via its own `ruleset-drift` job; `labels`, `apm-instructions`, and
`uv-pin-literal` file via `security_drift_report.py file-family-issues`.

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
| `weekly-maintenance.yml` / `branch-cleanup` | Impact | Weekly scheduled survey with `contents: read`; survey-only mode (no deletion); rolling summary issue serves as audit log. | `docs/runbooks/branch-cleanup.md`, `scripts/branch_cleanup.py`, `tests/test_branch_cleanup.py` | covered | — |
| `dependabot-automerge.yml` | RD, Persist | `pull_request_target` gated by audit script reading `dependabot-automerge.json` allowlist; severity/threat labels block auto-merge. | `docs/runbooks/dependabot-automerge.md`, `scripts/dependabot_automerge.py`, `tests/test_dependabot_automerge.py`, #185 | covered | — |
| `generate-agents.yml` | Persist, LM | Dispatch + reusable compile; weekly schedule is called by `weekly-maintenance.yml`; drift check via `git diff --exit-code` on `CLAUDE.md` / `AGENTS.md`; opens PR rather than push direct. | `.apm/instructions/master.instructions.md`, `verify-pr.yml`, #112 | partially covered | #183 (downstream review checklist) |
| `weekly-maintenance.yml` / `ruleset-drift` | Persist, IA | Weekly + dispatch drift detection vs `.github/rulesets/`; opens an issue when drift is detected. | `scripts/ruleset_drift.py`, `tests/test_ruleset_drift.py`, `docs/runbooks/rulesets.md` | covered | #120 (required-checks-vs-ruleset sync, separate scope) |
| `issue-pr-triage.yml` / `scan` | DE, Coll, Persist | Write-side scan of issues / PRs / comments; closes / requests-changes / labels; excludes trusted bots. | `docs/prd/non-ascii-defense.md`, `scripts/scan_non_ascii.py`, `tests/test_scan_non_ascii.py`, #102 | covered | — |
| `weekly-maintenance.yml` / `security-control-drift` | Persist, Impact | Weekly + dispatch + event-driven (`push` on `main` over control-family SoT paths, #1390) aggregator: reuses each per-family detector in read-only mode (`ruleset_drift.py detect`, `labels_apply.py plan`, `apm compile` + diff, `uv_pin.py drift` / `stale`) and posts a rolling comment on parent #178. Also auto-files one per-family issue (`security_drift_report.py file-family-issues`) for the `labels`, `apm-instructions`, and `uv-pin-literal` families when they drift, raising them to the `detect-and-file` floor (`rulesets` excluded -- filed by its own job; advisory `uv-pin-staleness` excluded). | `scripts/security_drift_report.py`, `tests/test_security_drift_report.py`, `.github/security-control-floor.toml`, `docs/runbooks/security-control-drift-report.md`, #180 | covered | — |
| `issue-pr-triage.yml` / `triage` | Coll, Recon | Deterministic OSV + GHSA + OSSF malicious-packages + CISA KEV lookup over PyPI and GitHub Actions surfaces (including `uv run --with pkg==ver` transient pins in workflows / `scripts/`), plus FIRST EPSS exploit-prediction enrichment (advisory-only, never escalates `threat:response-needed`); routes labels (`threat:intel-needed`, `threat:response-needed`) before any agent. | `scripts/threat_intel_triage.py`, `tests/test_threat_intel_triage.py`, `docs/runbooks/issue-triage.md`, #170, #173, #175, #176 | partially covered | #170 (sustained ops), #63 (agent-boundary review) |
| `verify-agents.yml` | RD, Persist, Exec | PR gate: repository-specific script lint, type, pytest-shard completeness, uv drift / staleness, workflow-shape, and maintainability checks. | `scripts/uv_pin.py`, `tests/test_uv_pin.py`, `docs/standards/remote-environment.md`, #112 | covered | — |
| `verify-pr.yml` / `portable-pr-policy` | IA, DE, RD, Persist, LM | PR gate: title / body / issue-link checks, README translation parity, APM portability scan, `apm compile` drift, checksum verification, and `prek` in one portable required context (the `Portable PR policy / gate` job, consolidated into `verify-pr.yml` in #1319). | `.apm/instructions/master.instructions.md`, `CLAUDE.md`, `AGENTS.md`, `scripts/scan_apm_portability.py`, `scripts/title_policy.py`, `scripts/body_policy.py`, `scripts/issue_link.py` | partially covered | #183 (downstream review checklist) |
| `verify-pr.yml` / `verify-dependabot-labels` | RD | Static cross-check that `dependabot.yml` labels resolve in `labels.json` (the `Verify dependabot labels / verify` job, consolidated into `verify-pr.yml` in #1319). | `scripts/dependabot_labels.py`, `tests/test_dependabot_labels.py` | covered | — |
| `verify-github-content.yml` | IA, DE, RD | Issue-only gate: title ASCII / format and body section structure for issue events. PR content checks live in `verify-pr.yml`. | `scripts/title_policy.py`, `scripts/body_policy.py`, `docs/standards/issue-pr-body-standard.md`, `docs/prd/non-ascii-defense.md` | covered | — |

Notes:

- No PR verification workflow grants `contents: write`; the PR-time agent compile check now lives in `verify-pr.yml` with read-only repository permissions.
- Every privileged-mutation workflow (`apply-labels.yml`, `apply-rulesets.yml`) is dispatch-only on `main` with an Environment-scoped PAT; no PAT is stored at repo level.

## 2. Branch rulesets (`.github/rulesets/`)

| Surface | ATT&CK | Existing defense | Evidence | Status | Gap |
|---|---|---|---|---|---|
| `main.json` | IA, Persist, Impact | Default-branch ruleset: required status checks including `Verify repository scripts / gate` and `Portable PR policy / gate`; blocks force-push; requires PR + linear history + resolved threads + code-owner review; squash-only merge; blocks deletion; `required_signatures` (satisfied by GitHub's squash-merge signature; keyless -- see `docs/standards/commit-signing.md`). | `docs/runbooks/rulesets.md`, `docs/standards/commit-signing.md`, `weekly-maintenance.yml`, #18, #27, #32, #120 | partially covered | #120 (required-checks-vs-ruleset live sync) |
| `all-branches.json` | IA, Impact | Non-default branch ruleset: blocks force-push on every branch except the default branch and `refs/heads/dependabot/*` (kept excluded so `@dependabot rebase` can force-push in place); deletion intentionally NOT blocked (relies on `delete_branch_on_merge: true`). | `docs/runbooks/rulesets.md`, `docs/runbooks/branch-cleanup.md`, #27, #59, #1014 | covered | — |

Notes:

- The dedicated `dependabot.json` ruleset (`non_fast_forward` on `dependabot/*`, no bypass actors) was **removed in #1014**. After GitHub deprecated the standalone Dependabot App the Rulesets API rejected the bypass actor (#273), so with `bypass_actors: []` the rule blocked `@dependabot rebase` and forced close + reopen. The branch namespace is no longer ruleset-protected — `non_fast_forward` never gated branch creation or actor identity. Auto-merge trust stays anchored on the author login `dependabot[bot]` (`scripts/dependabot_automerge.py`), and the deterministic gate `scripts/verify_dependabot_author.py` (wired into `issue-pr-triage.yml`, tested by `tests/test_verify_dependabot_author.py`) now fails any `dependabot/*` PR whose author is not a trusted bot login. This closes the #273 rebase gap (RD/IA) without re-protecting the branch.
- `bypass_actors` is `[]` on both remaining rulesets — the "Merge without waiting for requirements" UI path is unreachable. Emergency escape requires the [Emergency disable / re-enable procedure](../runbooks/rulesets.md#emergency-disable--re-enable-procedure), which leaves `repository_ruleset.update` audit events and is detected by `weekly-maintenance.yml` if the re-enable step is forgotten.
- The drift gate is the `ruleset-drift` job in `weekly-maintenance.yml`; the cross-family aggregator is the `security-control-drift` job (#180), which wires that drift output into #178 as evidence rather than duplicating the detector.

## 3. Label source of truth (`.github/labels.json`)

| Surface | ATT&CK | Existing defense | Evidence | Status | Gap |
|---|---|---|---|---|---|
| `.github/labels.json` | Persist, IA, Coll | JSON SoT; mutated only via `apply-labels.yml` with `dry_run` default; `verify-pr.yml` ensures Dependabot label references stay resolvable; scheduled drift surfaced by `weekly-maintenance.yml` (#180) and auto-filed as a per-family issue at the `detect-and-file` floor (`security_drift_report.py file-family-issues`, #178). | `docs/runbooks/issue-triage.md`, `apply-labels.yml`, `verify-pr.yml`, `weekly-maintenance.yml`, #84 | partially covered | #84 Phase 5 (label drift + coverage check) |

## 4. APM source and compiled instructions

| Surface | ATT&CK | Existing defense | Evidence | Status | Gap |
|---|---|---|---|---|---|
| `.apm/instructions/master.instructions.md` | LM, Persist, Exec | Single APM source. PR gate `verify-pr.yml` recompiles and diffs the output files; PR review on every change; scheduled compile-then-diff drift auto-filed as a per-family issue at the `detect-and-file` floor (`security_drift_report.py file-family-issues`, #178). | `verify-pr.yml`, `generate-agents.yml`, `CLAUDE.md`, `AGENTS.md` | partially covered | #183 (downstream review checklist) |
| `CLAUDE.md` | LM, Persist | Compiled output; drift-gated by `verify-pr.yml`; not hand-edited (compiled by `apm-cli==0.12.1`). | `verify-pr.yml`, `.apm/instructions/master.instructions.md`, #112 | covered | — |
| `AGENTS.md` | LM, Persist | Compiled output; drift-gated by `verify-pr.yml`; byte-identical compile to `CLAUDE.md` today. | `verify-pr.yml`, `.apm/instructions/master.instructions.md` | covered | — |

## 5. Dependency files and bump policy

| Surface | ATT&CK | Existing defense | Evidence | Status | Gap |
|---|---|---|---|---|---|
| `pyproject.toml` | RD, Exec, C2 | `[tool.uv].required-version` exact pin; `pyyaml` range pin used only by SessionStart hook; `lint-uv-pin` drift gate enforces single source of truth; scheduled `uv-pin-literal` drift auto-filed as a per-family issue at the `detect-and-file` floor (`security_drift_report.py file-family-issues`, #178). | `scripts/uv_pin.py`, `tests/test_uv_pin.py`, `verify-agents.yml`, `docs/standards/remote-environment.md`, #106, #112 | covered | — |
| `uv.lock` | RD, Exec, C2 | Locked transitive snapshot; CI uses `uv sync --locked`; Dependabot weekly bumps; OSV + KEV scanning via `issue-pr-triage.yml` / `triage`. | `verify-agents.yml`, `verify-pr.yml`, `issue-pr-triage.yml`, `.github/dependabot.yml` | covered | — |
| `.github/dependabot.yml` | RD, Persist | Two ecosystems (`github-actions`, `uv`); cooldown (default 7d, major 30d, minor 7d, patch 3d); auto-assigns `dependencies` label; `verify-pr.yml` cross-checks against `labels.json`. | `dependabot-automerge.yml`, `verify-pr.yml`, #185, #221 | covered | — |

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
| `github_api.py` | Cred, Exec, DE | CLI wrapper for GitHub REST API read operations; routes all agent GitHub reads through a single auditable path; `--fields` filter reduces token consumption; rejects non-`api.github.com` URLs; reads token from `GH_TOKEN` (never echoed). | `tests/test_github_api_cli.py`, `scripts/gate_gh_cli.py` (enforces usage), #887 | covered | — |
| `gate_gh_cli.py` | DE, Exec | PreToolUse hook for Bash; denies `gh` CLI invocations and direct `curl api.github.com` calls; redirects to `scripts/github_api.py` (reads) or `mcp__github__*` with hook (writes); fail-open on parse errors (retained per #1389: a `Bash`-matcher hook whose event envelope is harness-generated, not attacker-controllable; a fail-closed default would wedge all Bash for no assume-breach gain). | `tests/test_gate_gh_cli.py`, `.claude/settings.json`, #887 | covered | — |
| `gate_issue_close_comment.py` | DE, Impact | PreToolUse gate on `mcp__github__issue_write`; denies `state: closed` when no session comment has been posted to the same issue number (tracked via `/tmp/claude-issue-comments/`); PostToolUse recorder on `add_issue_comment` / `add_reply_to_pull_request_comment` writes the marker; gate fails **closed** on parse errors (#1389: an unverifiable or unresolved-issue-number close is denied; bound to `issue_write` only, so the deny cannot block unrelated tools). The PostToolUse recorder stays fail-open (it issues no decision). | `tests/test_gate_issue_close_comment.py`, `.claude/settings.json`, `.codex/hooks.json`, #896 | covered | — |
| `gate_mcp_github_uncovered.py` | DE, Exec | Catch-all PreToolUse hook for `mcp__github__*` tools without dedicated hooks; denies uncovered tools and redirects to `scripts/github_api.py` (reads) or instructs adding a hook (writes). | `tests/test_gate_mcp_github_uncovered.py`, `.claude/settings.json`, #870, #887 | covered | — |
| `_trusted_bots.py` | RD, Coll | Static allowlist of trusted bot logins; consumed by `scan_non_ascii.py` and PR-body checks. | `docs/standards/issue-pr-body-standard.md`, `docs/prd/non-ascii-defense.md` | covered | — |
| `body_policy.py` | DE, RD | Validates issue/PR body section structure with cutoff date; pure function, no network. | `tests/test_body_policy.py`, `verify-pr.yml`, `verify-github-content.yml`, #206 | covered | — |
| `branch_cleanup.py` | Impact, Persist | Survey-only; creates/edits rolling issue; `dry_run` default; bounded age threshold; tested age boundaries. | `tests/test_branch_cleanup.py`, `weekly-maintenance.yml`, `docs/runbooks/branch-cleanup.md` | partially covered | #182 (privileged-op runbook for future deletion path) |
| `dependabot_automerge.py` | RD, Persist | Audit-only; no mutation; reads policy from `dependabot-automerge.json`; tested against representative fixtures. | `tests/test_dependabot_automerge.py`, `docs/runbooks/dependabot-automerge.md` | covered | — |
| `dependabot_labels.py` | RD, DE | Static label-resolution check; no network; no mutation. | `tests/test_dependabot_labels.py`, `verify-pr.yml` | covered | — |
| `install-uv.sh` | Exec, C2, Persist | Idempotent SessionStart hook; no-op outside `CLAUDE_CODE_REMOTE`; reads pin from `pyproject.toml`; fetches astral-sh/uv release only. | `docs/standards/remote-environment.md`, `.claude/settings.json` (carve-out), #106, #109, #112 | partially covered | no paired automated test for the shell script (manual verification documented); see `docs/standards/remote-environment.md` *Verification* section. Tracked under #112 follow-up notes. |
| `issue_link.py` | IA, DE | PR gate; validates issue references via same-repo `gh api`; applies advisory labels. | `tests/test_issue_link.py`, `verify-pr.yml`, `docs/standards/issue-pr-body-standard.md` | covered | — |
| `labels_apply.py` | PrivEsc, Impact, Exfil | Plan / dry-run / apply tri-state; PAT scoped to `labels-apply` Environment; prune is opt-in and DELETE-aware; outputs human-readable diff. | `tests/test_labels_apply.py`, `apply-labels.yml`, `docs/runbooks/issue-triage.md` | partially covered | #181, #182 |
| `np_strategy_tracking.py` | PrivEsc, Impact | Plan (default dry-run) / apply tri-state; swaps an issue's `type:*` label to `type:tracking` for an N-PR delivery strategy so sibling PRs can use `Refs` without the body marker the GitHub MCP layer strips; pure decision function (`plan_label_swap`); `apply` records rationale as an issue comment; never echoes the token. | `tests/test_np_strategy_tracking.py`, `docs/standards/issue-pr-body-standard.md`, #1035, #1005 | covered | — |
| `plan_language_context.py` | Coll, LM | SessionStart hook; reads `.github/owners.yaml` and emits language policy; no mutation, no network. | `tests/test_plan_language_context.py`, `docs/standards/repo-scope.md`, #211 | covered | — |
| `pr_body_close_keyword_gate.py` | IA, DE | PreToolUse hook; client-side mirror of the issue-link step inside `verify-pr.yml` (Refs-only / tracking-label / partial-work-marker gate; the opt-out marker is the legacy `<!-- partial -->` comment or the MCP-safe plain-text `partial-pr` line, #1035); blocks `mcp__github__(create_pull_request\|update_pull_request)` with a `permissionDecision: "deny"` JSON; fail-closed when `GH_TOKEN` is unset so the local outcome cannot be looser than the server gate. | `tests/test_pr_body_close_keyword_gate.py`, `docs/standards/issue-pr-body-standard.md`, #219, #222, #1035 | covered | — |
| `preflight_non_ascii.py` | DE, LM, Cred | PreToolUse hook that blocks non-ASCII in `mcp__github__*` write tool inputs; shares scanner with `scan_non_ascii.py`. | `docs/prd/non-ascii-defense.md`, #102, #146 | partially covered | no dedicated test file; coverage rides on `scan_non_ascii.py`. Tracked under #102 follow-up notes. |
| `preflight_github_secrets.py` | Cred, Exfil, DE | PreToolUse hook that scans every string field of `mcp__github__*` write inputs (issue / PR / comment / review bodies) for high-confidence secrets via the shared `_secret_patterns.py` detector and denies before the value crosses into GitHub; the matched value is never echoed (redacted diagnostic names only the field and rule id); fail-open on parse errors (the event envelope is harness-generated, not attacker-controllable, per #1389). Wired into all three agent configs via `agent_hooks_source.json`. | `tests/test_preflight_github_secrets.py`, `scripts/_secret_patterns.py`, `scripts/scan_secrets.py`, `.claude/settings.json`, #1388 | covered | — |
| `_secret_patterns.py` | Cred, Exfil | Shared high-confidence secret-pattern detector (`scan_line` / `scan_text`); pure functions, no I/O; consumed by `scan_secrets.py` (committed-file gate) and `preflight_github_secrets.py` (write-side gate) so the two cannot drift. Never returns the matched value. | `tests/test_scan_secrets.py`, `tests/test_preflight_github_secrets.py`, #1129, #1388 | covered | — |
| `ruleset_drift.py` | Persist, IA | Compares live rulesets to SoT JSON; files an issue when drift is detected; reads `GH_TOKEN_API`. | `tests/test_ruleset_drift.py`, `weekly-maintenance.yml`, `docs/runbooks/rulesets.md` | covered | — |
| `rulesets_apply.py` | PrivEsc, IA, Impact | Plan / dry-run / apply tri-state; PAT scoped to `ruleset-apply` Environment; opt-in `enable_auto_delete`; outputs ruleset-by-ruleset diff. | `tests/test_rulesets_apply.py`, `apply-rulesets.yml`, `docs/runbooks/rulesets.md` | partially covered | #56, #181, #182 |
| `scan_non_ascii.py` | DE, Coll, Persist, Cred | Write-side scanner; closes / requests-changes / labels; trusted-bot allowlist; respects body section boundaries. | `tests/test_scan_non_ascii.py`, `issue-pr-triage.yml`, `docs/prd/non-ascii-defense.md`, #102 | covered | — |
| `security_drift_report.py` | Persist, Impact | Aggregator: parses captured exit codes / outputs of the per-family detectors and emits a single Markdown report; posts / updates a rolling comment on parent #178 via `_github_api.apply_call`. The `file-family-issues` subcommand auto-files one issue per drifting target family (`labels`, `apm-instructions`, `uv-pin-literal`) via the same `apply_call` boundary, meeting the `detect-and-file` floor; never mutates per-family state. | `tests/test_security_drift_report.py`, `weekly-maintenance.yml`, `.github/security-control-floor.toml`, `docs/runbooks/security-control-drift-report.md`, #180 | covered | — |
| `verify_security_control_floor.py` | Persist, Impact | Deterministic gate (`lint-scripts-static`): reads `.github/security-control-floor.toml` and fails CI when a scheduled control family sits below the `detect-and-file` floor without an explicit `exempt_reason`; pure `evaluate`, no network. | `tests/test_verify_security_control_floor.py`, `.github/security-control-floor.toml`, `verify-agents.yml`, #178 | covered | — |
| `threat_intel_triage.py` | Coll, Recon, RD | Deterministic OSV.dev + GHSA + OSSF malicious-packages + CISA KEV lookup with FIRST EPSS advisory-only enrichment (CVE-keyed score / percentile); dependency surfaces cover `uv.lock`, `pyproject.toml`, `.github/workflows/*.yml` `uses:` (`GitHub Actions` ecosystem), and `uv run --with pkg==ver` transient pins in workflows / `scripts/`; fixture inputs for offline tests; applies / removes labels only. EPSS lookups soft-fail so a transient FIRST API outage cannot block the KEV/OSV/GHSA/OSSF routing decision. | `tests/test_threat_intel_triage.py`, `issue-pr-triage.yml`, `docs/runbooks/issue-triage.md`, #170, #173, #175, #176 | partially covered | #170 |
| `title_policy.py` | DE, RD | ASCII / format validator for issue and PR titles; pure function. | `tests/test_title_policy.py`, `verify-pr.yml`, `verify-github-content.yml`, `docs/prd/non-ascii-defense.md` | covered | — |
| `uv_pin.py` | RD, Exec, C2 | Single source of truth for the `uv` pin; drift + upstream-staleness check; emits annotations rather than mutating files. | `tests/test_uv_pin.py`, `verify-agents.yml`, `docs/standards/remote-environment.md`, #112 | covered | — |

## 7. Documentation / runbooks (`docs/`)

| Surface | ATT&CK | Existing defense | Evidence | Status | Gap |
|---|---|---|---|---|---|
| `docs/runbooks/branch-cleanup.md` | Impact, Disc | Documents weekly survey workflow, dispatch inputs, age threshold, dry-run default, rollback path (re-create branch from issue note). | `weekly-maintenance.yml`, `scripts/branch_cleanup.py`, #31 | covered | — |
| `docs/runbooks/dependabot-automerge.md` | RD, Persist | Documents allowlist policy and labels that veto auto-merge; references audit script. | `dependabot-automerge.yml`, `scripts/dependabot_automerge.py`, #185 | covered | — |
| `docs/standards/issue-pr-body-standard.md` | DE, RD, IA | Documents body section requirements; trusted-bot carve-out; advisory hook integration. | `verify-pr.yml`, `verify-github-content.yml`, `scripts/body_policy.py`, `scripts/pr_body_close_keyword_gate.py`, #206 | covered | — |
| `docs/runbooks/issue-triage.md` | Coll, Recon, Persist, PrivEsc | Documents label taxonomy, `LABELS_PAT` Environment scope, apply workflow, prune semantics, manual verification. | `apply-labels.yml`, `.github/labels.json`, #84 | partially covered | #181, #182 |
| `docs/runbooks/agent-provenance.md` | RD, Exec, LM, C2 | Documents minimum provenance metadata, permission review, update cadence, and rollback expectations before adopting or updating skills, subagents, MCP servers, or comparable agent extensions. | #63, #312, `docs/agent-provenance.md` | covered | — |
| `docs/prd/non-ascii-defense.md` | DE, LM, Cred, Coll | Documents three-layer non-ASCII defense (past sanitization, write-side workflow + PreToolUse, read-side PostToolUse); rollback steps. | `issue-pr-triage.yml`, `scripts/scan_non_ascii.py`, `scripts/preflight_non_ascii.py`, #102, #146 | covered | — |
| `docs/standards/performance-metrics.md` | RD | Design-only doc; no operational control today; no privileged data. | #61, #58 | not applicable | — |
| `docs/standards/remote-environment.md` | Exec, C2, Persist | Documents SessionStart hook, uv pin propagation, verification commands, rollback procedure, outbound-network expectations. | `scripts/install-uv.sh`, `.claude/settings.json`, `scripts/uv_pin.py`, #106, #109, #112 | covered | — |
| `docs/standards/repo-scope.md` | LM, Exec | Documents the `.claude/settings.json` carve-out and the prohibition on per-agent tool config (`.codex/`, etc.). | `docs/standards/remote-environment.md`, #109 | covered | — |
| `docs/runbooks/rulesets.md` | PrivEsc, IA, Impact, Disc | Documents `RULESETS_PAT` scope, ruleset apply / verify / rollback orchestration, dispatch authorization, audit-log expectations. | `apply-rulesets.yml`, `weekly-maintenance.yml`, `scripts/rulesets_apply.py`, #18, #27, #56 | partially covered | #56, #182 |
| `docs/runbooks/security-control-drift-report.md` | Persist, Impact | Documents the scheduled aggregator (#180): trigger, families covered, families pending, rolling-comment marker, dry-run preview, per-row investigation steps, rollback. | `weekly-maintenance.yml`, `scripts/security_drift_report.py`, #178, #180 | covered | — |

## Cross-reference: ATT&CK tactic → surface coverage

This table answers, for each row of #178's coverage table: which surfaces in this inventory contribute to the defense, and what is the aggregate status. It is the bridge between this inventory and the #178 coverage table.

| ATT&CK | Contributing surfaces | Aggregate status | Gap |
|---|---|---|---|
| Recon | `docs/runbooks/issue-triage.md`, `docs/runbooks/rulesets.md`, `docs/standards/remote-environment.md`, `threat_intel_triage.py` | partially covered | #170, #181 (no scheduled secret scan beyond GitHub default) |
| RD | `verify-pr.yml`, `verify-github-content.yml`, `issue-pr-triage.yml`, `verify_dependabot_author.py`, `.github/dependabot.yml`, `uv.lock`, `pyproject.toml`, `docs/runbooks/agent-provenance.md` | covered | — |
| IA | `main.json`, `all-branches.json`, `verify_dependabot_author.py`, `verify-pr.yml`, `verify-github-content.yml`, `weekly-maintenance.yml` | partially covered | #120 |
| Exec | `verify-agents.yml`, `verify-pr.yml`, `install-uv.sh`, `pyproject.toml`, `uv.lock`, `.claude/settings.json` carve-out, `docs/runbooks/agent-provenance.md` | partially covered | #181 (workflow `permissions:` audit) |
| Persist | `verify-pr.yml`, `weekly-maintenance.yml`, `apply-labels.yml`, `apply-rulesets.yml`, `verify-github-content.yml` | covered | — |
| PrivEsc | `apply-labels.yml`, `apply-rulesets.yml`, `weekly-maintenance.yml`, `docs/runbooks/issue-triage.md`, `docs/runbooks/rulesets.md` | partially covered | #56, #181 |
| DE | `verify-pr.yml`, `verify-github-content.yml`, `issue-pr-triage.yml`, `preflight_non_ascii.py` | covered | — |
| Cred | `issue-pr-triage.yml`, `preflight_non_ascii.py`, `docs/runbooks/rulesets.md`, `docs/runbooks/issue-triage.md` (Environment-scoped PATs) | partially covered | #181 (log redaction audit) |
| Disc | `docs/runbooks/rulesets.md`, `docs/runbooks/issue-triage.md`, `docs/runbooks/branch-cleanup.md`, `docs/standards/remote-environment.md` | covered | — |
| LM | `.apm/instructions/master.instructions.md`, `CLAUDE.md`, `AGENTS.md`, `verify-pr.yml`, `generate-agents.yml`, `docs/runbooks/agent-provenance.md` | partially covered | #183 |
| Coll | `issue-pr-triage.yml`, `_trusted_bots.py`, `docs/prd/non-ascii-defense.md` | partially covered | #63, #102 |
| C2 | `install-uv.sh`, `threat_intel_triage.py`, `generate-agents.yml`, `uv.lock`, `pyproject.toml`, `docs/runbooks/agent-provenance.md` | covered | — |
| Exfil | `apply-labels.yml`, `apply-rulesets.yml`, `weekly-maintenance.yml`, `docs/runbooks/rulesets.md`, `docs/runbooks/branch-cleanup.md` | partially covered | #181, #182 |
| Impact | `apply-labels.yml`, `apply-rulesets.yml`, `weekly-maintenance.yml`, `main.json`, `all-branches.json` | partially covered | #182 |

## Gap summary

Follow-up issues this inventory references:

| Issue | Scope (per its body) |
|---|---|
| #56 | Ruleset PAT handling and privileged-dispatch hardening |
| #63 | Residual workflow risk, prompt-injection boundary, tool surface, supply chain |
| #102 | Multi-byte / non-ASCII prompt-injection hardening |
| #120 | Required-checks vs live ruleset synchronization |
| #170 | Sustained external threat-intelligence triage operations |
| #180 | Scheduled drift reporting across control families (closed by `weekly-maintenance.yml`) |
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
- `ls .github/rulesets/` matches the 2 rows in section 2.
- `ls scripts/` matches the 22 rows in section 6 (`__pycache__` is excluded; not security-relevant).
- `ls docs/` matches the 11 rows in section 7.

Closes #179.
