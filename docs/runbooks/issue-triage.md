# Issue Triage — Label Taxonomy & Routing Runbook

This document is the operator-facing runbook for the labels that triage every issue in this repository. The core axes, severity flag, and automated threat flags are all readable from the GraphQL `labels.nodes[]` header, letting an API/MCP client route an issue without fetching its body.

The taxonomy is introduced incrementally per the phased rollout in [#84](https://github.com/tvna/claude-md/issues/84), which supersedes the `agent:*` design from [#34](https://github.com/tvna/claude-md/issues/34). The JSON SoT lives at `.github/labels.json`; the `Apply labels` workflow described below reconciles GitHub against it. Per [CLAUDE.md §3](../../CLAUDE.md), agents must be concentrated at one workflow point *after* deterministic gates pass -- the labels are the gate. Per §5 it exists to avoid wasting tokens on bodies the agent should not read in full.

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

These labels are applied by the `triage` job in the `Issue and PR triage` workflow. They do not replace `severity:security`; they record whether external threat-intelligence collection found repository-relevant vulnerability information.

| Label | Meaning |
|---|---|
| `threat:intel-needed` | Collect threat intelligence before routing or implementation. |
| `threat:response-needed` | Security response is required; do not open an autonomous PR before investigation. |

The deterministic rule lives in `scripts/threat_intel_triage.py`. The workflow extracts every repository-local dependency surface and consults five external sources plus one supplemental enrichment layer.

### Repository-local dependency surfaces

`discover_dependencies` in `scripts/threat_intel_triage.py` walks the following inputs. Non-executable prose (Markdown under `docs/`, `README*.md`, `AGENTS.md`) is intentionally excluded so a runbook example cannot create noisy findings.

| Surface | Source | Records |
|---|---|---|
| Locked PyPI graph | `uv.lock` | every transitive `[[package]]` entry |
| Direct PyPI pins | `pyproject.toml` (`project.dependencies`, `dependency-groups.*`) | exact `name==version` entries only; ranges are ignored |
| GitHub Actions | `.github/workflows/**/*.{yml,yaml}` `uses:` lines | `owner/repo@<ref>`; for SHA-pinned references the trailing `# <tag>` comment supplies the version so OSV correlates against the released tag |
| Transient PyPI pins | `.github/workflows/**/*.{yml,yaml}` and `scripts/**/*.{sh,py}` `uv run --with <pkg>==<ver>` | only literal `name==version` invocations; shell-variable expansions, placeholders, and range specifiers are silently skipped |

Local in-repo workflow references (`./...`) and `docker://...` OCI images are out of scope: the former carry no upstream version surface, the latter are gated by digest pinning under `scripts/scan_workflow_action_pins.py`.

### External sources

- **OSV.dev** — aggregator queried for vulnerabilities that affect each package version. Covers PyPI (`uv.lock`, `pyproject.toml`, `uv run --with` transient pins) **and** the `GitHub Actions` ecosystem (workflow `uses:` references).
- **GitHub Advisory Database** — queried directly via `api.github.com/advisories` (`--ghsa-live`) so reviewed, unreviewed, and malware advisories preserve source attribution alongside OSV. Ecosystems without a GHSA mapping (currently anything other than PyPI) are silently skipped at the GHSA stage; correlation for the GitHub Actions surface relies on OSV.
- **OSSF malicious-packages** — queried via `api.osv.dev/v1/query` (`--malpkg-live`) per dependency with the version field omitted, keeping only IDs prefixed `MAL-` (the OSSF malicious-packages syndication channel on OSV.dev). This is the documented stable access path for the corpus; matching is **name-only** (case-insensitive within ecosystem) so newly introduced typosquats and maintainer-takeover releases register even when the locked version is not itself flagged.
- **CISA KEV** — fetched to correlate any OSV, GHSA, or OSSF finding whose ID or aliases appear in the known-exploited catalog.
- **FIRST EPSS** — queried via `api.first.org/data/v1/epss` (`--epss-live`) for CVE-aliased findings. Provides an exploit-prediction score (0.0-1.0) and percentile rank so reviewers can prioritize CVEs that KEV has not (yet) confirmed as exploited. Per [#173](https://github.com/tvna/claude-md/issues/173) EPSS is **advisory-only**: scores enrich the summary table but never escalate `threat:response-needed` on their own. CISA KEV remains the authoritative known-exploitation signal; the rationale for not adding an EPSS threshold here is recorded below.
- **NVD (supplemental enrichment, [#174](https://github.com/tvna/claude-md/issues/174))** — `--nvd-file` for fixture-driven tests, `--nvd-live` to query `services.nvd.nist.gov/rest/json/cves/2.0`. NVD is consulted **only for CVEs already surfaced by OSV or GHSA**; it never widens the finding set, never reclassifies severity, and never affects the `threat:response-needed` decision. When NVD enrichment is available it attaches CVSS (v3.1 → v3.0 → v2.0 fallback), CWE identifiers, and reference URLs to the triage summary row and to a follow-up `### NVD references (supplemental)` block. **Limitations:** NVD has strict unauthenticated rate limits (5 requests per 30 seconds) and visible analyst-publish latency on newly assigned CVEs, so transport failure, 404, or empty payloads are silently skipped. **Missing NVD enrichment is not evidence that the underlying OSV/GHSA finding is irrelevant** — response decisions remain driven by KEV correlation, OSSF `MAL-` findings, and GHSA `malware` advisories, never by NVD presence.

### Source-selection policy

Threat-intelligence sources are admitted only when they preserve deterministic,
attributable routing. A proposed source must meet all of these properties before
it can influence labels:

- **Public availability.** The source is public, queryable by maintainers, and
  does not require private credentials, paid access, or sharing repository
  context with an unapproved service.
- **License and terms compatibility.** The source permits automated lookup,
  citation in GitHub Actions summaries, and fixture snapshots for tests.
- **Stable machine-readable format.** The source exposes JSON, CSV, or another
  documented structured format with stable identifiers that can be joined to a
  repository dependency surface.
- **Source attribution.** Every surfaced finding can name the source that
  produced it. Aggregated data must preserve whether a result came from OSV.dev,
  GHSA, OSSF malicious-packages, CISA KEV, FIRST EPSS, NVD, or a future source.
- **Fixture-testability.** The workflow must support a checked-in or
  test-generated fixture path so CI verifies the routing rule without live
  network access.

Current finding sources are OSV.dev, GitHub Advisory Database, OSSF
malicious-packages, and CISA KEV. FIRST EPSS is a prediction enrichment source,
not an escalation source. NVD is metadata enrichment only and cannot widen the
finding set. Candidate sources named for later review include ecosystem-specific
advisory feeds, Dependabot/security-alert exports, and other public malware or
known-exploitation catalogs, but none should be added until the properties above
are satisfied and fixtures cover the new branch.

Precedence is ordered by evidence strength:

1. **Confirmed exploitation or malware** takes priority. CISA KEV correlation,
   GHSA `malware` advisories, and OSSF `MAL-` findings can add
   `threat:response-needed`.
2. **Prediction enriches but does not escalate.** FIRST EPSS scores help humans
   prioritize CVE-aliased findings, but do not add `threat:response-needed`.
3. **Vulnerability metadata informs context.** OSV.dev, GHSA vulnerability
   advisories, and NVD metadata establish or enrich the finding set, but absent
   exploitation or malware evidence they route to `threat:intel-needed` only.

Missing source data is never evidence of safety. Empty, rate-limited, failed, or
unsupported responses mean "no usable data from this source in this run"; they do
not clear another source's finding and do not remove an existing need for human
review. Operators should use fixture inputs when a live source is unreachable and
should state any live-source outage in the workflow summary or follow-up comment
when it affects confidence.

Source quality is reviewed during the retrospective for every PR that changes
`scripts/threat_intel_triage.py`, `.github/workflows/issue-pr-triage.yml`, or
this runbook, and at least quarterly while #170 remains open. The review records
false positives, false negatives, stale-label removals, rate-limit failures, and
terms or schema changes. A source that repeatedly produces unactionable findings
or cannot be fixture-tested is parked until a narrower query, better
normalization, or removal plan is documented.

Any external finding adds `threat:intel-needed`. Any KEV-correlated finding, any GHSA advisory whose `type` is `malware`, *or* any finding whose ID starts with `MAL-` (OSSF malicious-packages) also adds `threat:response-needed`. Fixture inputs (`--osv-file`, `--kev-file`, `--ghsa-file`, `--malpkg-file`, `--epss-file`, `--nvd-file`) exist for tests so CI can verify the routing logic without live network access; the same fixture path is the documented fallback when OSV.dev or GitHub Advisory is unreachable -- an operator can dispatch the workflow with a pre-fetched fixture instead of the corresponding `--*-live` flag. The triage summary lists which sources actually surfaced findings and tags each row with its source string (e.g. `OSV.dev, OSSF malicious-packages`); when EPSS scores are attached, an `EPSS` column shows `<score> (p<percentile>%)` per finding and `FIRST EPSS` appears in the `Sources:` line. NVD never appears in the source string because it is enrichment, not a finding source; when NVD data is attached the row gains `NVD CVSS` and `NVD CWE` columns and a `### NVD references (supplemental)` block lists per-CVE detail.

### Why EPSS is advisory-only (no auto-escalation threshold)

KEV records vulnerabilities **observed** in active exploitation. EPSS is a probabilistic forecast of exploitation likelihood. The two signals are complementary, not interchangeable:

- KEV correlation is rare and unambiguous: when it fires, response action is warranted.
- EPSS distributes across the entire CVE population; even a 0.95 score still admits false positives, and choosing a threshold without observed false-positive data would lock automation into a guess.
- The auto-escalation surface (`threat:response-needed`) blocks autonomous PRs and requires investigation. A probabilistic signal raising that flag would generate review load that does not match a confirmed-exploitation incident.

A future sub-issue may revisit this once distribution data has been observed on real findings; until then the score is surfaced for human prioritization only.

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

One-time setup for `LABELS_PAT`:

1. Open GitHub user settings, then **Developer settings**.
2. Open **Personal access tokens** -> **Fine-grained tokens**.
3. Select **Generate new token**.
4. Set the token name to `LABELS_PAT`.
5. Set an expiration date of 90 days or less, then record the rotation
   date in the operator calendar.
6. Under **Resource owner**, select `tvna`.
7. Under **Repository access**, select **Only select repositories** and
   choose `tvna/claude-md`.
8. Under **Repository permissions**, set:
   - **Issues**: Read and write.
   - **Metadata**: Read-only.
9. Generate the token and copy it once. Do not paste it into an issue,
   PR, commit, terminal transcript, or runbook.
10. Open `tvna/claude-md` -> **Settings** -> **Environments**.
11. Create or open the `labels-apply` Environment.
12. Keep required reviewers enabled for live apply review if repository
    policy requires manual approval before label mutation.
13. Add an Environment secret named `LABELS_PAT` with the copied token
    value.
14. Run `apply-labels.yml` with `dry_run=true` and confirm the guard
    step passes and the job emits a plan without mutating labels.

Rotation uses the same secret name: generate the replacement token
first, update the `labels-apply` Environment secret, confirm a
`dry_run=true` dispatch passes the guard step, then revoke the old token.

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
