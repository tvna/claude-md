# Issue Triage — Label Taxonomy & Routing Runbook

This document is the operator-facing runbook for the labels that triage every issue in this repository. The core axes, severity flag, and automated threat flags are all readable from the GraphQL `labels.nodes[]` header, letting an API/MCP client route an issue without fetching its body.

The taxonomy is introduced incrementally per the phased rollout in [#84](https://github.com/tvna/claude-md/issues/84), which supersedes the `agent:*` design from [#34](https://github.com/tvna/claude-md/issues/34). The JSON SoT lives at `.github/labels.json`; the `Apply labels` workflow described below reconciles GitHub against it. Per [CLAUDE.md §3](../blob/main/CLAUDE.md), agents must be concentrated at one workflow point *after* deterministic gates pass — the labels are the gate. Per §5 it exists to avoid wasting tokens on bodies the agent should not read in full.

## SoT layout

| File | Target | Purpose |
|---|---|---|
| `.github/labels.json` | `/repos/tvna/claude-md/labels` | JSON source of truth for repository labels |
| `docs/runbooks/issue-triage.md` *(this file)* | — | Runbook |
| `docs/standards/issue-pr-body-standard.md` | — | Sibling runbook for issue/PR body shape (read after labels route an issue) |

## Axes

Every issue receives:

- **≥ 1 `layer:*` label** — which CLAUDE.md layer(s) the issue interferes with (multi-valued; no primary/secondary distinction)
- **Exactly 1 `type:*` label** — purpose of the change
- **0 or 1 `state:*` label** — lifecycle position; absent means active
- **0 or 1 `severity:*` label** — sensitivity flag (security or content)
- **0 to 2 `threat:*` labels** — automated threat-intelligence and response routing flags

### `layer:*` (multi-valued, ≥1)

Slug names are stable historical layer keys; descriptions track the current `master.instructions.md` responsibility. The `pN-` prefix keeps natural sort order in the GitHub UI.

| Label | § | Meaning |
|---|---|---|
| `layer:p1-goal-plan` | §1 | Goal & plan structure |
| `layer:p2-precode` | §2 | Input and pre-code reasoning — untrusted text, facts, assumptions, ambiguity |
| `layer:p3-harness` | §3 | Delivery harness — issues, CI, hooks, deps, PR loop |
| `layer:p4-artifact` | §4 | Safety boundary — simplicity, tool scope, secret exposure |
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
| `severity:non-ascii-content` | Non-ASCII in title/body/comment; advisory for trusted authors, blocks external contributors. |

### `threat:*` (0 to 2)

These labels are applied by the `Threat intelligence triage` workflow. They do not replace `severity:security`; they record whether external threat-intelligence collection found repository-relevant vulnerability information.

| Label | Meaning |
|---|---|
| `threat:intel-needed` | Collect threat intelligence before routing or implementation. |
| `threat:response-needed` | Security response is required; do not open an autonomous PR before investigation. |

The deterministic rule lives in `scripts/threat_intel_triage.py`. The workflow extracts locked PyPI dependencies from `uv.lock` (plus exact pins in `pyproject.toml`) and consults four external sources:

- **OSV.dev** — aggregator queried for vulnerabilities that affect each package version.
- **GitHub Advisory Database** — queried directly via `api.github.com/advisories` (`--ghsa-live`) so reviewed, unreviewed, and malware advisories preserve source attribution alongside OSV. GitHub Actions enumeration is deferred to [#176](https://github.com/tvna/claude-md/issues/176).
- **OSSF malicious-packages** — queried via `api.osv.dev/v1/query` (`--malpkg-live`) per dependency with the version field omitted, keeping only IDs prefixed `MAL-` (the OSSF malicious-packages syndication channel on OSV.dev). This is the documented stable access path for the corpus; matching is **name-only** (case-insensitive within ecosystem) so newly introduced typosquats and maintainer-takeover releases register even when the locked version is not itself flagged.
- **CISA KEV** — fetched to correlate any OSV, GHSA, or OSSF finding whose ID or aliases appear in the known-exploited catalog.

Any external finding adds `threat:intel-needed`. Any KEV-correlated finding, any GHSA advisory whose `type` is `malware`, *or* any finding whose ID starts with `MAL-` (OSSF malicious-packages) also adds `threat:response-needed`. Fixture inputs (`--osv-file`, `--kev-file`, `--ghsa-file`, `--malpkg-file`) exist for tests so CI can verify the routing logic without live network access; the same fixture path is the documented fallback when OSV.dev or GitHub Advisory is unreachable -- an operator can dispatch the workflow with a pre-fetched fixture instead of `--malpkg-live`. The triage summary lists which sources actually surfaced findings and tags each row with its source string (e.g. `OSV.dev, OSSF malicious-packages`).

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

The four `agent:*` labels (`auto-fix` / `investigate` / `no-action` / `triage-needed`) are scheduled for deletion in [#84](https://github.com/tvna/claude-md/issues/84) Phase 4 after every issue has been retroactively labeled with the new axes. The SoT (`.github/labels.json`) no longer lists `agent:*` entries.

### Cleanup pass on 2026-05-26

Sub-issue [#405](https://github.com/tvna/claude-md/issues/405) (Phase 3 operation log) drove a 24-issue back-labeling pass on 2026-05-26 covering three audit findings from #84:

- **A.** Multi-type fix on #18, #34, #87: removed `type:feat`; left `type:tracking` plus `layer:p3-harness`.
- **B.** `agent:*` residue (9 issues: #58, #60, #61, #62, #63, #72, #88, #89, #90): added `layer:*` and `type:*` per the SoT taxonomy. Five issues received `state:rfc` or `type:tracking` where the body declared an open-question umbrella. `agent:investigate` and `agent:no-action` label definitions remain on those issues until the post-merge prune dispatch removes them from the live catalogue.
- **C.** `governance` residue (10 closed issues with no `layer:*`: #51, #53, #55, #73, #75, #106, #109, #112, #113, #115): added `layer:p2-precode`, `layer:p3-harness`, or `layer:meta` and the corresponding `type:*`. `governance` and the legacy `fix` label on #53 / #55 remain until the prune dispatch.

After the pass, the four taxonomy queries below all return zero, which is the operator's readiness signal to run the prune dispatch:

```sh
gh issue list --search 'is:issue label:type:feat label:type:tracking'                                                                   # multi-type
gh issue list --search 'is:issue label:agent:investigate -label:layer:p1-goal-plan -label:layer:p2-precode -label:layer:p3-harness -label:layer:p4-artifact -label:layer:p5-scope-split -label:layer:p6-handoff -label:layer:meta'
gh issue list --search 'is:issue label:agent:no-action  -label:layer:p1-goal-plan -label:layer:p2-precode -label:layer:p3-harness -label:layer:p4-artifact -label:layer:p5-scope-split -label:layer:p6-handoff -label:layer:meta'
gh issue list --search 'is:issue label:governance       -label:layer:p1-goal-plan -label:layer:p2-precode -label:layer:p3-harness -label:layer:p4-artifact -label:layer:p5-scope-split -label:layer:p6-handoff -label:layer:meta'
```

### Phase 4 prune dispatch (post-merge, operator-side)

Once this PR merges, dispatch `apply-labels.yml` with `prune=true` to delete the now-orphan label definitions from the live catalogue. This is destructive on existing assignments per the warning earlier in this runbook, but the back-labeling pass above has already replaced every classification function before the deletion runs.

```sh
# Dry-run first; the step summary should list four labels for DELETE: agent:investigate, agent:no-action, governance, fix
gh workflow run apply-labels.yml --ref main -f dry_run=true -f prune=true

# Apply
gh workflow run apply-labels.yml --ref main -f dry_run=false -f prune=true

# Verify: live label set matches SoT exactly
diff <(gh api /repos/tvna/claude-md/labels --jq '.[].name' | sort) <(jq -r '.[].name' .github/labels.json | sort)
# Expect: no output (the only known divergence after prune is `type:chore` on #338, which is intentionally out of scope per the #84 sub-decision tree)
```

`agent:auto-fix` and `agent:triage-needed` had zero live assignments before the dispatch, so their deletion is purely catalogue cleanup.

The full before/after issue-by-issue record is preserved in [`docs/archive/label-migration-2026-05-26.md`](../archive/label-migration-2026-05-26.md) per the `docs/archive/RETENTION.md` append-only policy.
