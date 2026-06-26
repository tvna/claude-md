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

Do not put an undecided evaluation here either. If a document still
carries an open question that blocks a yes/no decision (for example one
awaiting human follow-up or a live API response), it belongs in
[`docs/proposals/`](../proposals/README.md) until the question resolves;
it graduates into this lane once it becomes a settled decision record.

Current compatibility notes:

- `agent-rules-design-philosophy.md` belongs here because it defines the
  repository's documentation and instruction responsibility model.
- `repair-loops-proliferation-analysis.md` belongs here because it is
  read-only analysis that feeds future follow-up issues.
- Existing adopted contracts that still live in this lane are legacy
  placement debt; migrate them to `docs/standards/` in a scoped follow-up
  instead of adding new adopted contracts here.

## Documents

| File | Territory | Tracking issues | Companion |
|---|---|---|---|
| [README.md](README.md) | Compatibility entrypoint for PRD/design placement rules. | #202 | `docs/INDEX.md`; `docs/standards/documentation-quality.md` |
| [TEMPLATE.md](TEMPLATE.md) | Authoring skeleton for prd/ design notes and decision records. | #2000 | `docs/prd/README.md`; `docs/next-session/TEMPLATE.md` |
| [agent-rules-design-philosophy.md](agent-rules-design-philosophy.md) | Meta-runbook for evolving `.apm/instructions/master.instructions.md` and its compiled `CLAUDE.md` / `AGENTS.md`. Six principles plus the four-lane responsibility matrix. | #226, #246 | `.apm/instructions/master.instructions.md` (source); `scripts/scan_design_philosophy_drift.py`; `.github/workflows/verify-pr.yml` (`verify-design-philosophy` job) |
| [codex-permission-request-policy-gate.md](codex-permission-request-policy-gate.md) | Design-stage plan for a future Codex `PermissionRequest` adapter backed by a shared repository policy predicate and Claude parity evidence. | #711, #617, #604 | `.codex/hooks.json`; `.claude/settings.json`; `tests/test_codex_hooks_config.py` |
| [repair-loops-proliferation-analysis.md](repair-loops-proliferation-analysis.md) | Read-only analysis of auto-retro repair-loop signal branches; feeds future follow-up issues rather than defining a gate. | #412 | `scripts/auto_retro.py`; `docs/archive/retrospective-pr-*.md` |
| [offline-prehead-validation-gates.md](offline-prehead-validation-gates.md) | Design pattern for offline PR-head mirror gates that catch breakage a base-checkout `pull_request_target` check cannot see on the PR; five-part checklist and a gate registry. | #1519, #1511 | `scripts/threat_intel_triage.py` (`verify`); `.pre-commit-config.yaml`; `.github/workflows/verify-pr.yml` |
| [security-control-inventory.md](security-control-inventory.md) | MITRE ATT&CK coverage SoT for repository security surfaces. Re-read whenever a workflow, script, ruleset, or runbook lands. | #179, #178 | `scripts/security_drift_report.py`; `.github/workflows/weekly-maintenance.yml` |
| [zero-trust-gap-analysis.md](zero-trust-gap-analysis.md) | Durable Zero Trust (eBook) gap analysis mapping repo controls to seven capability domains and three maturity tiers; the session-memory-independent record of unmet gaps and their tracking issues. | #178, #1387 | `docs/prd/security-control-inventory.md`; `.github/workflows/weekly-maintenance.yml` || [non-ascii-defense.md](non-ascii-defense.md) | Three-layer ASCII discipline at the GitHub-post boundary. | #102 | `scripts/scan_non_ascii.py`; `scripts/preflight_non_ascii.py`; `scripts/sanitize_history.py`; `.github/workflows/issue-pr-triage.yml` |
| [freshness-precondition-gate.md](freshness-precondition-gate.md) | Concrete companion to the universal time-boxed-gate refresh rule: the create_branch freshness preflight, the interim per-operation refresh, and the future auto-refresh skill. | #894, #654, #859 | `scripts/preflight_main_freshness.py`; `.claude/settings.json`; `.apm/instructions/master.instructions.md` (section 3) |
| [doc-dependency-graph.md](doc-dependency-graph.md) | Design rationale for the typed document dependency graph gate: graph schema, edge types, waiver mechanism, advisory-to-required rollout, and the PR#1737-class failure mode this gate prevents. | #1754 | `docs/graph/doc-dependencies.toml`; `scripts/gate_doc_graph_pr.py`; `scripts/doc_graph.py`; `scripts/doc_graph_viz.py`; `.github/workflows/validate-doc-graph.yml` |
| [semantic-versioning-universal-text.md](semantic-versioning-universal-text.md) | Compatibility-based semver for the universal text; drift gate, post-merge `v{version}` auto-tag. | #89 | `apm.yml` |
| [sessionstart-installer-download-retry.md](sessionstart-installer-download-retry.md) | Decision record for retrying curl downloads (initial plus 3 retries, 1s/2s/4s backoff) in the ten SessionStart installers via a shared `scripts/_retry.sh` helper, with fail-loud-but-fail-open surfacing and a bare-curl drift gate. | #2038 | `scripts/_retry.sh`; `scripts/install-*.sh`; `scripts/scan_install_curl_retry_drift.py` |

The last three `prd/` entries are adopted contracts with legacy
placement. They should move to `standards/` in a scoped follow-up rather
than serving as precedent for new PRD files.
