# Zero Trust gap analysis

> Status: analysis (read-only decision record). Companion source of truth for
> security surface coverage is [`security-control-inventory.md`](security-control-inventory.md);
> the umbrella that coordinates the gaps is #178.

This document is the durable record of the Zero Trust gap analysis run against
this repository's agentic-AI security controls. It exists so the analysis and
its open gaps are not session-memory dependent: every gap is mapped to a
tracking issue or explicitly recorded as parked here.

## Source and method

- Framework source: Anthropic, "Zero Trust for AI Agents" (eBook, 2026),
  grounded from an operator-provided copy. Reproducible fetch is tracked in
  #1383. The eBook framing is captured in #178.
- Method: the full control set (50+ scripts under `scripts/`, the workflows
  under `.github/workflows/`, and the runbooks under `docs/`) was swept and
  mapped against the eBook framework -- three principles, the "impossible, not
  tedious" design test, Least Agency and blast radius, three maturity tiers
  (Foundation, Enterprise, Advanced), and seven capability domains.
- Evidence tags: `[fact]` is observed in-tree or in issue state; `[analysis]`
  is a gap judgement.

## Top meta-gap: the control inventory had drifted

- `[fact]` `security-control-inventory.md` listed `scripts/` as 22 rows and
  named #181 / #182 / #184 / #312 as open gaps.
- `[fact]` `scripts/` now holds 50+ files (for example `scan_secrets.py`,
  `block_sensitive_reads.py`, `scan_workflow_action_pins.py`) plus runbooks
  added since (`workflow-permissions-audit.md`, `privileged-operation-runbooks.md`,
  `attack-coverage-review-cadence.md`, `agent-provenance.md`). #181 / #182 /
  #184 / #312 are all closed (completed).
- `[analysis]` The inventory marked closed work as open and omitted landed
  controls. Re-verification relied on "re-read whenever a workflow, script,
  ruleset, or runbook lands" (reviewer memory), with no deterministic gate.
  This is the "impossible, not tedious" failure and a deterministic-gate gap
  (CLAUDE.md section 3). Tracked by #1387.

## Capability-domain gaps

| Domain | Unmet gap `[analysis]` | Tier | Tracking |
|---|---|---|---|
| Identity / auth | Long-lived standing PATs; rotation is only a reminder, not short-lived / OIDC tokens. No gate fails a PAT past its rotation window. | Advanced | #1381 |
| Access / privilege | Mixed fail posture: `gate_gh_cli.py` and `gate_issue_close_comment.py` fail-open on parse errors while preflight gates fail-closed. Residual non-Environment PAT read use. | Enterprise | #1389, #56 |
| Observability / audit | Drift detection is weekly-cron only (up to a 7-day window). Plus the inventory-currency gap above. | Enterprise | #1390, #1387 |
| Behavioral monitoring | No agent-action anomaly detection or per-session mutation blast-radius cap; OWASP ASI08 / ASI10 runtime anomaly unmapped. | Advanced | #1380, #1378 |
| Input / output controls | No PreToolUse gate scans `mcp__github__*` write bodies for secret patterns; a token pasted into an issue/PR/comment would post uncaught. | Foundation | #1388 |
| Integrity / recovery | Rollback is documented but not rehearsed/verified (no recovery-validation gate). | Enterprise (mostly met) | parked (see below) |
| AI governance | Agent-extension provenance is a manual checklist, with no deterministic gate enforcing provenance metadata on adoption. | Advanced | parked (see below) |

## Tier scorecard `[analysis]`

- Foundation: mostly met (deny-by-default MCP gates, protected and signed
  `main`, pinned dependencies, secret scanning of files). Hole: output-side
  secret-exfil gate (#1388).
- Enterprise: partial (audit trail and a permissions audit exist). Holes:
  residual PAT scope (#56), detection latency (#1390), mixed fail posture
  (#1389).
- Advanced: largely unmet -- agent identity / short-lived credentials (#1381),
  runtime behavioral anomaly detection and blast-radius caps (#1380), active
  defense, and recovery validation.

## "Impossible, not tedious" violations `[analysis]`

1. PAT rotation = reminder (friction) -> short-lived / OIDC tokens (misuse made
   impossible). Tracked: #1381.
2. Inventory currency = manual re-read -> CI fails when a new surface is absent
   from the source of truth. Tracked: #1387.
3. Fail-open gates = trust default -> unify on fail-closed. Tracked: #1389.
4. Weekly detection = shrink-the-window operation -> event-driven detection.
   Tracked: #1390.

## Three lenses

- MITRE ATT&CK: controls are thick but the inventory was stale (resynced by
  #1387); review cadence is established (#184, with
  `runbooks/attack-coverage-review-cadence.md`).
- OWASP Agentic Top 10: completion tracked in #1378. The genuinely unmet items
  are ASI03 (agent identity) and ASI08 / ASI10 (runtime anomaly), matching the
  Identity and Behavioral domains above.
- Threat intelligence: strong and largely met (#170 closed, SHA-pinned actions,
  KEV / OSV / GHSA / OSSF / EPSS via `threat_intel_triage.py`).

## Prioritized unmet work

| Priority | Work | Tracking |
|---|---|---|
| 1 | Resync the inventory and add a currency gate | #1387 |
| 2 | Output-side secret-exfil PreToolUse gate on `mcp__github__*` writes | #1388 |
| 3 | Unify GitHub MCP gate fail posture to fail-closed | #1389 |
| 4 | PAT short-lived / OIDC and per-session blast-radius cap | #1381, #1380 |
| 5 | Event-driven drift detection for the key families | #1390 |

## Parked items (recorded, not yet issue-backed)

These are captured here so they are not lost to session memory. They were left
un-issued to avoid tracker proliferation; promote to an issue when prioritized.

- Integrity / recovery: rollback procedures are documented per runbook but not
  rehearsed. A recovery-validation drill (or a gate that exercises a documented
  rollback against a fixture) would prove recovery works rather than assuming
  it. Lower priority because the rollback paths are simple `git revert` or
  SoT-re-apply flows.
- AI governance: agent-extension (skill / subagent / MCP server) adoption is
  governed by the `agent-provenance.md` checklist (manual). A deterministic
  manifest-validation gate that fails when a newly added extension lacks
  provenance metadata would remove the reviewer-memory dependency. Deferred
  until a second agent extension is actually adopted.

## Re-verification

- Confirm each tracking issue above is open or closed-with-rationale.
- After #1387 lands, `security-control-inventory.md` and this file should agree
  on the gap set; a disagreement is a drift signal to reconcile.
