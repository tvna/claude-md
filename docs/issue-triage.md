# Issue Triage — Three-Axis Label Taxonomy & Routing Runbook

This document is the operator-facing runbook for the labels that triage every issue in this repository. Three axes plus one severity flag — all readable from the GraphQL `labels.nodes[]` header — let an API/MCP client classify an issue without fetching its body.

The taxonomy is introduced incrementally per the phased rollout in [#84](https://github.com/tvna/claude-md/issues/84), which supersedes the `agent:*` design from [#34](https://github.com/tvna/claude-md/issues/34). The JSON SoT lives at `.github/labels.json`; the values in the Apply section below MUST match it byte-for-byte. Per [CLAUDE.md §3](../blob/main/CLAUDE.md), agents must be concentrated at one workflow point *after* deterministic gates pass — the labels are the gate. Per §5 it exists to avoid wasting tokens on bodies the agent should not read in full.

## SoT layout

| File | Target | Purpose |
|---|---|---|
| `.github/labels.json` | `/repos/tvna/claude-md/labels` | JSON source of truth for the 15 labels |
| `docs/issue-triage.md` *(this file)* | — | Runbook |

## Axes

Every issue receives:

- **≥ 1 `layer:*` label** — which CLAUDE.md layer(s) the issue interferes with (multi-valued; no primary/secondary distinction)
- **Exactly 1 `type:*` label** — purpose of the change
- **0 or 1 `state:*` label** — lifecycle position; absent means active
- **0 or 1 `severity:security` label** — security-sensitive flag

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

## Agent routing

Agents read `(type, state, severity)` from the header alone and apply this table — **no body fetch is required for routing**:

| Condition | Agent action | Body read? |
|---|---|---|
| `state:rfc` OR `state:parked` | no-action | no |
| `type:tracking` | no-action on umbrella; act on sub-issues only | no |
| `severity:security` (regardless of other labels) | investigate (no autonomous PR) | yes |
| `type:fix` AND NOT `severity:security` | auto-fix candidate (mechanical PR allowed) | yes |
| `type:docs` | auto-fix candidate | yes |
| `type:feat` OR `type:refactor` | investigate — plan first, implementation awaits approval | yes |
| No `type:*` yet | triage-needed: read title only, set `type:*`, re-route | title only |

Rows are evaluated top-to-bottom; the first match wins. This table is the routing decision — the labels do not encode the decision themselves.

## Apply (first-time `POST`)

Apply one label at a time. Each call returns the created label object. The `-f color=` / `-f description=` values are byte-for-byte mirrors of `.github/labels.json` — if either side changes, update both in the same PR.

```sh
gh api \
  --method POST \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/tvna/claude-md/labels \
  -f name='layer:p1-goal-plan' \
  -f color='1d76db' \
  -f description='CLAUDE.md §1 — Goal & plan structure (what the work is and how it will be verified).'

# Repeat the same shape for each of the other 14 names. The full byte-for-byte
# payload list is `jq -c '.[]' .github/labels.json`:
jq -c '.[]' .github/labels.json | while read -r row; do
  name=$(jq -r '.name'        <<< "$row")
  color=$(jq -r '.color'      <<< "$row")
  desc=$(jq -r '.description' <<< "$row")
  gh api \
    --method POST \
    -H "Accept: application/vnd.github+json" \
    -H "X-GitHub-Api-Version: 2022-11-28" \
    /repos/tvna/claude-md/labels \
    -f name="$name" \
    -f color="$color" \
    -f description="$desc"
done
```

## Update (re-apply with `PATCH`)

Use the update path when fixing drift or when adjusting colour / description. Labels are addressed by their current name; pass `-f new_name=` to rename.

```sh
gh api \
  --method PATCH \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/tvna/claude-md/labels/layer:p1-goal-plan \
  -f color='1d76db' \
  -f description='CLAUDE.md §1 — Goal & plan structure (what the work is and how it will be verified).'
```

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
                 (.labels | map(.name) | map(select(. == "severity:security")) | length > 1))
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

Deleting a label is **destructive on existing issues** — GitHub removes the label from every issue and PR it was applied to. Re-`POST`ing the same label restores its definition but does **not** restore per-issue assignments; those must be re-applied manually (Phase 3 of #84 is the operation log for that).

## Drift detection

A scheduled workflow that diffs the live labels returned by `gh api` against `.github/labels.json` **and** verifies issue coverage (every open issue has ≥1 `layer:*`, exactly 1 `type:*`, ≤1 `state:*`, ≤1 `severity:*`) is planned as Phase 5 of [#84](https://github.com/tvna/claude-md/issues/84) (parked). Until it lands, drift is detected only by manual review during retrospectives.

## Migration from the `agent:*` design (#34)

The four `agent:*` labels (`auto-fix` / `investigate` / `no-action` / `triage-needed`) are scheduled for deletion in [#84](https://github.com/tvna/claude-md/issues/84) Phase 4 after every issue has been retroactively labeled with the new axes. Until Phase 4 lands, `agent:*` labels may still exist on live issues but are no longer authoritative — the agent routing table above is. The SoT (`.github/labels.json`) no longer lists `agent:*` entries.
