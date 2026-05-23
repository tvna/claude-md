# Issue Triage — Label Taxonomy & Routing Runbook

This document is the operator-facing runbook for the labels that triage every issue in this repository. The core axes, severity flag, and automated threat flags are all readable from the GraphQL `labels.nodes[]` header, letting an API/MCP client route an issue without fetching its body.

The taxonomy is introduced incrementally per the phased rollout in [#84](https://github.com/tvna/claude-md/issues/84), which supersedes the `agent:*` design from [#34](https://github.com/tvna/claude-md/issues/34). The JSON SoT lives at `.github/labels.json`; the `Apply labels` workflow described below reconciles GitHub against it. Per [CLAUDE.md §3](../blob/main/CLAUDE.md), agents must be concentrated at one workflow point *after* deterministic gates pass — the labels are the gate. Per §5 it exists to avoid wasting tokens on bodies the agent should not read in full.

## SoT layout

| File | Target | Purpose |
|---|---|---|
| `.github/labels.json` | `/repos/tvna/claude-md/labels` | JSON source of truth for repository labels |
| `docs/issue-triage.md` *(this file)* | — | Runbook |
| `docs/issue-pr-body-standard.md` | — | Sibling runbook for issue/PR body shape (read after labels route an issue) |

## Axes

Every issue receives:

- **≥ 1 `layer:*` label** — which CLAUDE.md layer(s) the issue interferes with (multi-valued; no primary/secondary distinction)
- **Exactly 1 `type:*` label** — purpose of the change
- **0 or 1 `state:*` label** — lifecycle position; absent means active
- **0 or 1 `severity:security` label** — security-sensitive flag
- **0 to 2 `threat:*` labels** — automated threat-intelligence and response routing flags

### `layer:*` (multi-valued, ≥1)

Slug names mirror the Layer identifier in `master.instructions.md` so they survive principle-text edits; the `pN-` prefix keeps natural sort order in the GitHub UI.

| Label | § | Meaning |
|---|---|---|
| `layer:p1-goal-plan` | §1 | Goal & plan structure |
| `layer:p2-precode` | §2 | Pre-code reasoning — fact vs. speculation, assumptions, ambiguity |
| `layer:p3-harness` | §3 | Delivery harness — issues, CI, hooks, deps, PR loop |
| `layer:p4-artifact` | §4 | Artifact code — simplicity bounded by safety |
| `layer:p5-scope-split` | §5 | Change scope & agent split |
| `layer:p6-handoff` | §6 | Handoff & communication |
| `layer:meta` | — | Repo infrastructure governing the meta-document itself (labels, rulesets, workflows). NOT a CLAUDE.md principle. |

Multi-layer issues (e.g. an RFC that moves a rule from §1 to §3) carry every applicable `layer:*` label. Coverage check is cardinality ≥ 1.

### `type:*` (exactly 1)

| Label | Meaning |
|---|---|
| `type:feat` | New behaviour or rule added to the meta-document or repo |
| `type:fix` | Defect: contradiction, broken workflow, wrong doc |
| `type:refactor` | Restructure without behaviour change |
| `type:docs` | Operator runbooks / README (not the meta-document itself) |
| `type:tracking` | Umbrella issue coordinating phased sub-issues |

Maps 1:1 to the Conventional Commit prefixes used in this repo (`docs(...)`, `fix:`, etc.).

### `state:*` (0 or 1; absent = active)

| Label | Meaning |
|---|---|
| `state:rfc` | Open but unactioned per §2 — speculative proposal awaiting evidence |
| `state:parked` | Explicitly deferred; requires evidence to revive |

### `severity:*` (0 or 1)

| Label | Meaning |
|---|---|
| `severity:security` | Security-sensitive. Overrides agent routing toward `investigate` regardless of `type:*`. |

### `threat:*` (0 to 2)

These labels are applied by the `Threat intelligence triage` workflow. They do not replace `severity:security`; they record whether external threat-intelligence collection found repository-relevant vulnerability information.

| Label | Meaning |
|---|---|
| `threat:intel-needed` | Collect threat intelligence before routing or implementation. |
| `threat:response-needed` | Security response is required; do not open an autonomous PR before investigation. |

The deterministic rule lives in `scripts/threat_intel_triage.py`. The workflow extracts locked PyPI dependencies from `uv.lock` (plus exact pins in `pyproject.toml`), queries OSV.dev for vulnerabilities that affect those package versions, fetches CISA KEV, and marks any OSV finding whose ID or aliases appear in KEV as known exploited. Any external finding adds `threat:intel-needed`; any KEV-correlated finding also adds `threat:response-needed`. Fixture inputs (`--osv-file`, `--kev-file`) exist for tests so CI can verify the routing logic without live network access.

## Agent routing

Agents read `(type, state, severity, threat)` from the header alone and apply this table — **no body fetch is required for routing**:

| Condition | Agent action | Body read? |
|---|---|---|
| `state:rfc` OR `state:parked` | no-action | no |
| `type:tracking` | no-action on umbrella; act on sub-issues only | no |
| `threat:response-needed` | investigate + response planning (no autonomous PR) | yes |
| `threat:intel-needed` | collect threat intelligence, then re-route | yes |
| `severity:security` (regardless of other labels) | investigate (no autonomous PR) | yes |
| `type:fix` AND NOT `severity:security` | auto-fix candidate (mechanical PR allowed) | yes |
| `type:docs` | auto-fix candidate | yes |
| `type:feat` OR `type:refactor` | investigate — plan first, implementation awaits approval | yes |
| No `type:*` yet | triage-needed: read title only, set `type:*`, re-route | title only |

Rows are evaluated top-to-bottom; the first match wins. This table is the routing decision — the labels do not encode the decision themselves.

## Apply

The `Apply labels` workflow (`.github/workflows/apply-labels.yml`) is the only supported apply path. It reconciles `.github/labels.json` against the live label set on GitHub via `workflow_dispatch`: POSTs missing labels, PATCHes labels whose color/description differs, and (when `prune=true`) DELETEs labels absent from SoT. Color/description changes propagate through the same dispatch — there is no separate update path.

### Required secret

`LABELS_PAT` — fine-grained PAT scoped to `tvna/claude-md` with `Repository permissions → Issues: Read and write` (the labels endpoints live under Issues in the new PAT scopes). Stored in the `labels-apply` GitHub Environment, not at the repo level.

### Dispatch

```sh
gh workflow run apply-labels.yml --ref main -f dry_run=true -f prune=false
gh run watch
```

Inputs:

- `dry_run` (default `true`) — plan only; emit a markdown summary, no live mutation.
- `prune` (default `false`) — when `true` (and `dry_run=false`), DELETE labels present on GitHub but absent from SoT. Destructive on existing issues: GitHub removes the label from every issue and PR it was applied to.

Reconciliation matrix:

| Live state | SoT state | `dry_run=true` | `dry_run=false, prune=false` | `dry_run=false, prune=true` |
|---|---|---|---|---|
| missing | present | plan-only (POST) | POST | POST |
| present (equal) | present | no-op | no-op | no-op |
| present (differs) | present | plan-only (PATCH) | PATCH | PATCH |
| present | missing | plan-only (report) | report-only row | DELETE |

Typical sequences:

1. **Add or update labels.** Dispatch with `dry_run=true` → review the summary → re-dispatch with `dry_run=false, prune=false`.
2. **Retire old labels** (e.g. #84 Phase 4 `agent:*` retirement). Dispatch with `dry_run=true, prune=true` → confirm only the intended names appear under `plan-only (DELETE)` → re-dispatch with `dry_run=false, prune=true`.

If the workflow itself is broken, the recovery path is `git revert` of the workflow change, not a parallel manual recipe.

## Verify

After every apply or update:

```sh
# 1. Live label set equals SoT byte-for-byte (intersection check; ignores any
#    still-live agent:* labels until Phase 4 of #84 retires them).
diff \
  <(jq -r '.[].name' .github/labels.json | sort) \
  <(gh api /repos/tvna/claude-md/labels --jq '.[].name | select(startswith("agent:") | not)' | sort)

# 2. Per-label color & description match.
for name in $(jq -r '.[].name' .github/labels.json); do
  diff \
    <(jq --arg n "$name" '.[] | select(.name == $n) | {color, description}' .github/labels.json) \
    <(gh api "/repos/tvna/claude-md/labels/$name" --jq '{color, description}')
done

# 3. Coverage on every issue (this is the §1 completion check for #84 Phase 3).
gh api -X GET /repos/tvna/claude-md/issues --paginate -f state=all \
  --jq '.[] | select(.pull_request | not)
        | select((.labels | map(.name) | any(startswith("layer:")) | not) or
                 (.labels | map(.name) | map(select(startswith("type:"))) | length != 1) or
                 (.labels | map(.name) | map(select(startswith("state:"))) | length > 1) or
                 (.labels | map(.name) | map(select(. == "severity:security")) | length > 1) or
                 (.labels | map(.name) | map(select(startswith("threat:"))) | length > 2))
        | .number'
# Must print nothing once Phase 3 is complete.
```

## Rollback

```sh
gh api \
  --method DELETE \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/tvna/claude-md/labels/<name>
```

Deleting a label is **destructive on existing issues** — GitHub removes the label from every issue and PR it was applied to. Re-dispatching the `Apply labels` workflow restores the label definition (if it is still listed in SoT) but does **not** restore per-issue assignments; those must be re-applied manually (Phase 3 of #84 is the operation log for that).

## Drift detection

A scheduled workflow that diffs the live labels returned by `gh api` against `.github/labels.json` **and** verifies issue coverage (every open issue has ≥1 `layer:*`, exactly 1 `type:*`, ≤1 `state:*`, ≤1 `severity:*`, ≤2 `threat:*`) is planned as Phase 5 of [#84](https://github.com/tvna/claude-md/issues/84) (parked). Until it lands, drift is detected only by manual review during retrospectives.

## Migration from the `agent:*` design (#34)

The four `agent:*` labels (`auto-fix` / `investigate` / `no-action` / `triage-needed`) are scheduled for deletion in [#84](https://github.com/tvna/claude-md/issues/84) Phase 4 after every issue has been retroactively labeled with the new axes. Until Phase 4 lands, `agent:*` labels may still exist on live issues but are no longer authoritative — the agent routing table above is. The SoT (`.github/labels.json`) no longer lists `agent:*` entries.
