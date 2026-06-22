# Issue Triage -- Label Taxonomy & Routing Runbook

This document is the operator-facing runbook for the labels that triage every issue in this repository. The core axes and the severity flag are all readable from the GraphQL `labels.nodes[]` header, letting an API/MCP client route an issue without fetching its body. (The `threat:*` overlay axis was retired in #1647; see `threat:*` below.)

The adopted post-#970 label design lives in
[`docs/standards/label-taxonomy.md`](../standards/label-taxonomy.md) and the
machine-readable policy file
[`../../.github/label-policy.toml`](../../.github/label-policy.toml). The live
GitHub catalog remains [`../../.github/labels.json`](../../.github/labels.json)
until the migration issue #972 updates writers, backfills assignments, and runs
the apply/prune workflow.

The taxonomy is introduced incrementally per the phased rollout in [#84](https://github.com/tvna/claude-md/issues/84), which supersedes the `agent:*` design from [#34](https://github.com/tvna/claude-md/issues/34). The JSON SoT lives at `.github/labels.json`; the `Apply labels` workflow described below reconciles GitHub against it. Per [CLAUDE.md §3](../../CLAUDE.md), agents must be concentrated at one workflow point *after* deterministic gates pass -- the labels are the gate. Per §5 it exists to avoid wasting tokens on bodies the agent should not read in full.

## SoT layout

| File | Target | Purpose |
|---|---|---|
| `.github/label-policy.toml` | Final target policy after #970 | Adopted design contract; not applied until #972 |
| `.github/labels.json` | `/repos/tvna/claude-md/labels` | JSON source of truth for repository labels |
| `docs/runbooks/issue-triage.md` *(this file)* | -- | Runbook |
| `docs/standards/label-taxonomy.md` | -- | Adopted taxonomy, area mapping, and operational-label rules |
| `docs/standards/issue-pr-body-standard.md` | -- | Sibling runbook for issue/PR body shape (read after labels route an issue) |

## Axes

Every issue receives:

- **≥ 1 `layer:*` label** -- which CLAUDE.md layer(s) the issue interferes with (multi-valued; no primary/secondary distinction)
- **Exactly 1 `type:*` label** -- purpose of the change
- **0 or 1 `state:*` label** -- lifecycle position; absent means active
- **0 or 1 `severity:*` label** -- sensitivity flag (security or content)
- ~~**0 to 2 `threat:*` labels**~~ -- **retired** in #1647; the per-item labels are removed and threat-intelligence findings aggregate onto the #178 umbrella (see `threat:*` below)

### `layer:*` (multi-valued, ≥1)

Slug names are stable historical layer keys; descriptions track the current `master.instructions.md` responsibility. The `pN-` prefix keeps natural sort order in the GitHub UI.

| Label | § | Meaning |
|---|---|---|
| `layer:p1-goal-plan` | §1 | Goal & plan structure |
| `layer:p2-precode` | §2 | Input and pre-code reasoning -- untrusted text, facts, assumptions, ambiguity |
| `layer:p3-harness` | §3 | Delivery harness -- issues, CI, hooks, deps, PR loop |
| `layer:p4-artifact` | §4 | Safety boundary -- simplicity, tool scope, secret exposure |
| `layer:p5-scope-split` | §5 | Change scope & agent split |
| `layer:p6-handoff` | §6 | Handoff & communication |
| `layer:meta` | -- | Repo infrastructure governing the meta-document itself (labels, rulesets, workflows). NOT a CLAUDE.md principle. |

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

Apply `type:tracking` only when the issue is a sub-issue umbrella (coordinates
children, takes no direct implementation commit) AND is referenced by multiple
PRs via non-closing `Refs #N` (1-issue/N-PR). The label is what lets those
Refs-only PRs pass `verify-issue-link.yml`. Do not apply it to an issue a
single PR closes via `Closes #N`, including a one-off retrospective. There is
no `tracking` title type; pick the conventional type that fits the work and
mark the umbrella with the label.

### `state:*` (0 or 1; absent = active)

| Label | Meaning |
|---|---|
| `state:rfc` | Open but unactioned per §2 -- speculative proposal awaiting evidence |
| `state:parked` | Explicitly deferred; requires evidence to revive |

### `severity:*` (0 or 1)

| Label | Meaning |
|---|---|
| `severity:security` | Security-sensitive. Overrides agent routing toward `investigate` regardless of `type:*`. |
| `severity:non-ascii-content` | Non-ASCII in title/body/comment; advisory for trusted authors, blocks external contributors. |

### `threat:*` (retired)

**The `threat:*` labels were retired.** Auto-application was removed in [#1645](https://github.com/tvna/claude-md/issues/1645), and the label definitions were removed from `.github/labels.json` and `.github/label-policy.toml` in [#1647](https://github.com/tvna/claude-md/issues/1647). Threat-intelligence findings are repository-global -- they come from the locked-dependency corpus, not from any one issue/PR -- so stamping them onto whatever item happened to trigger a run produced pure noise (a single known-exploited, no-fix advisory flipped `threat:response-needed` on every new item). Findings are now **aggregated** into one idempotent comment on the #178 security umbrella; see [Aggregated findings on the security umbrella](#aggregated-findings-on-the-security-umbrella) below. The `intel-needed` / `response-needed` *classifications* survive only as finding descriptors in that aggregated comment, not as live labels:

| Finding class | Meaning (on the #178 umbrella) |
|---|---|
| `intel-needed` | A repository-relevant external finding was surfaced; collect threat intelligence. |
| `response-needed` | A KEV-correlated, OSSF `MAL-`, or GHSA `malware` finding fired; security response is required (no autonomous remediation). |

The live per-item label assignments left by the retired regime are swept by the owner-driven prune dispatch; see *Stale-label handling* below.

The deterministic rule lives in `scripts/threat_intel_triage.py`. The `scan` subcommand extracts every repository-local dependency surface and consults five external sources plus one supplemental enrichment layer.

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

- **OSV.dev** -- aggregator queried for vulnerabilities that affect each package version. Covers PyPI (`uv.lock`, `pyproject.toml`, `uv run --with` transient pins) **and** the `GitHub Actions` ecosystem (workflow `uses:` references).
- **GitHub Advisory Database** -- queried directly via `api.github.com/advisories` (`--ghsa-live`) so reviewed, unreviewed, and malware advisories preserve source attribution alongside OSV. Ecosystems without a GHSA mapping (currently anything other than PyPI) are silently skipped at the GHSA stage; correlation for the GitHub Actions surface relies on OSV.
- **OSSF malicious-packages** -- queried via `api.osv.dev/v1/query` (`--malpkg-live`) per dependency with the version field omitted, keeping only IDs prefixed `MAL-` (the OSSF malicious-packages syndication channel on OSV.dev). This is the documented stable access path for the corpus; matching is **name-only** (case-insensitive within ecosystem) so newly introduced typosquats and maintainer-takeover releases register even when the locked version is not itself flagged.
- **CISA KEV** -- fetched to correlate any OSV, GHSA, or OSSF finding whose ID or aliases appear in the known-exploited catalog.
- **FIRST EPSS** -- queried via `api.first.org/data/v1/epss` (`--epss-live`) for CVE-aliased findings. Provides an exploit-prediction score (0.0-1.0) and percentile rank so reviewers can prioritize CVEs that KEV has not (yet) confirmed as exploited. Per [#173](https://github.com/tvna/claude-md/issues/173) EPSS is **advisory-only**: scores enrich the summary table but never escalate `threat:response-needed` on their own. CISA KEV remains the authoritative known-exploitation signal; the rationale for not adding an EPSS threshold here is recorded below.
- **NVD (supplemental enrichment, [#174](https://github.com/tvna/claude-md/issues/174))** -- `--nvd-file` for fixture-driven tests, `--nvd-live` to query `services.nvd.nist.gov/rest/json/cves/2.0`. NVD is consulted **only for CVEs already surfaced by OSV or GHSA**; it never widens the finding set, never reclassifies severity, and never affects the `threat:response-needed` decision. When NVD enrichment is available it attaches CVSS (v3.1 → v3.0 → v2.0 fallback), CWE identifiers, and reference URLs to the triage summary row and to a follow-up `### NVD references (supplemental)` block. **Limitations:** NVD has strict unauthenticated rate limits (5 requests per 30 seconds) and visible analyst-publish latency on newly assigned CVEs, so transport failure, 404, or empty payloads are silently skipped. **Missing NVD enrichment is not evidence that the underlying OSV/GHSA finding is irrelevant** -- response decisions remain driven by KEV correlation, OSSF `MAL-` findings, and GHSA `malware` advisories, never by NVD presence.

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
   GHSA `malware` advisories, and OSSF `MAL-` findings classify the run
   `response_needed`.
2. **Prediction enriches but does not escalate.** FIRST EPSS scores help humans
   prioritize CVE-aliased findings, but do not escalate the run to
   `response_needed`.
3. **Vulnerability metadata informs context.** OSV.dev, GHSA vulnerability
   advisories, and NVD metadata establish or enrich the finding set, but absent
   exploitation or malware evidence they classify the run `intel_needed` only.

Missing source data is never evidence of safety. Empty, rate-limited, failed, or
unsupported responses mean "no usable data from this source in this run"; they do
not clear another source's finding and do not remove an existing need for human
review. Operators should use fixture inputs when a live source is unreachable and
should state any live-source outage in the workflow summary or follow-up comment
when it affects confidence.

Source quality is reviewed during the retrospective for every PR that changes
`scripts/threat_intel_triage.py`, the `dependency-threat-triage` job in
`.github/workflows/weekly-maintenance.yml`, or
this runbook, and on the quarterly cadence defined under
[Threat-intel triage review cadence](#threat-intel-triage-review-cadence) below.
The review records
false positives, false negatives, stale-label removals, rate-limit failures, and
terms or schema changes. A source that repeatedly produces unactionable findings
or cannot be fixture-tested is parked until a narrower query, better
normalization, or removal plan is documented.

Any external finding classifies the run as `intel_needed`. Any KEV-correlated finding, any GHSA advisory whose `type` is `malware`, *or* any finding whose ID starts with `MAL-` (OSSF malicious-packages) also classifies it as `response_needed`. These were the conditions that previously drove the per-item `threat:intel-needed` / `threat:response-needed` labels; since [#1645](https://github.com/tvna/claude-md/issues/1645) they drive the aggregated umbrella comment and the scheduled-run exit status instead (see below). Fixture inputs (`--osv-file`, `--kev-file`, `--ghsa-file`, `--malpkg-file`, `--epss-file`, `--nvd-file`) exist for tests so CI can verify the routing logic without live network access; the same fixture path is the documented fallback when OSV.dev or GitHub Advisory is unreachable -- an operator can dispatch the workflow with a pre-fetched fixture instead of the corresponding `--*-live` flag. The triage summary lists which sources actually surfaced findings and tags each row with its source string (e.g. `OSV.dev, OSSF malicious-packages`); when EPSS scores are attached, an `EPSS` column shows `<score> (p<percentile>%)` per finding and `FIRST EPSS` appears in the `Sources:` line. NVD never appears in the source string because it is enrichment, not a finding source; when NVD data is attached the row gains `NVD CVSS` and `NVD CWE` columns and a `### NVD references (supplemental)` block lists per-CVE detail.

### Aggregated findings on the security umbrella

Since [#1645](https://github.com/tvna/claude-md/issues/1645), threat-intel findings are recorded in exactly one place: an idempotent, marker-anchored comment on the #178 security umbrella, mirroring how `scripts/security_drift_report.py` posts its weekly drift comment there. This replaces the retired per-item `threat:*` labels and per-item evidence comments.

- **Where it runs.** The `dependency-threat-triage` job in `.github/workflows/weekly-maintenance.yml` (scheduled cadence, plus `workflow_dispatch` with `task=dependency-threat-triage`). The per-event `triage` job in `Issue and PR triage` was removed; findings are repository-global, so a weekly repo-wide scan is the correct cadence and the per-event run added no per-item signal.
- **Idempotent.** The comment is anchored by the hidden marker `<!-- threat-intel-aggregate v1 -->`; the job PATCHes the existing umbrella comment when present and POSTs only when absent, so repeated runs collapse to a single comment. The target issue number is resolved at runtime via `python3 scripts/issue_anchors.py get security-tracking` (`.github/tracking-issues.toml`), never hardcoded, so `scripts/scan_issue_anchor_drift.py` stays clean and an umbrella renumber is a one-file diff.
- **Tracks state.** When findings fire, the comment is created/updated with the full correlation table. When findings clear, the job runs `comment --update-only`, which refreshes an existing comment to the "no findings" state but never creates an empty comment on the umbrella.
- **Still fails loud.** The scan keeps `--fail-on-intel`, so a recurring advisory or an expired accepted-intel suppression turns the scheduled run red independent of PR traffic ([#1277](https://github.com/tvna/claude-md/issues/1277)); the aggregation step runs with `if: always()` so the umbrella is updated even on a red run.
- **No autonomous-PR block.** Dropping the per-item `threat:response-needed` label means a finding no longer blocks an autonomous PR on the triggering item; this block was intentionally retired in #1645. The human-in-the-loop boundary in *Response handoff* below still holds: no workflow converts a finding into an autonomous code or configuration change.

### Threat-intel triage review cadence

The source-quality paragraph above runs per-retrospective; this section is the
recurring, calendar-driven companion that keeps the triage effective once the
one-time completion gates of [#170](https://github.com/tvna/claude-md/issues/170)
have closed. The standing anchor for review records is
[#1076](https://github.com/tvna/claude-md/issues/1076); each cycle is logged
there as a dated comment, the same way the ATT&CK coverage cadence logs to its
tracker (see [`attack-coverage-review-cadence.md`](attack-coverage-review-cadence.md)).

**Frequency.** Quarterly (first Monday of January, April, July, and October, to
align with the ATT&CK coverage review), **plus** a per-retrospective check for
any PR that touches the triage surface -- `scripts/threat_intel_triage.py`,
the `dependency-threat-triage` job in `.github/workflows/weekly-maintenance.yml`,
or this runbook. Quarterly is the
floor; the per-retrospective check catches drift between quarters. This cadence
is currently a **manual procedure** -- there is no scheduled reminder workflow --
so the owner runs it and records the result on #1076.

**Each cycle checks four things:**

1. **True positives.** Findings classified `intel-needed` or `response-needed`
   on the #178 umbrella and acted on. Confirm each acted-on finding had
   a real repository-relevant cause: a locked dependency, a workflow `uses:`
   pin, or a transient `uv run --with` pin actually present in the tree.
2. **False positives.** Findings classified on the umbrella but dismissed.
   Record the *systemic* cause (over-broad query, stale fixture,
   ecosystem mismatch) rather than only the individual dismissal, so the rule or
   its fixtures can be narrowed.
3. **Leftover labels.** The retired per-item `threat:*` assignments still
   present on existing issues/PRs. These are no longer re-evaluated by
   automation; see *Stale-label handling* below for the one-time owner-driven
   cleanup.
4. **Source coverage.** Confirm OSV.dev, CISA KEV, GitHub Advisory Database,
   OSSF malicious-packages, FIRST EPSS, and NVD are reachable and return the
   expected data shapes; note any upstream schema or terms change. Per *Missing
   source data is never evidence of safety* above, an unreachable source is
   recorded as reduced confidence for that cycle, never as an all-clear.

**Stale-label handling (owner-driven cleanup, owner @tvna).** The `threat:*`
labels were **retired**: [#1645](https://github.com/tvna/claude-md/issues/1645)
stopped auto-applying them, and [#1647](https://github.com/tvna/claude-md/issues/1647)
removed the definitions from `.github/labels.json` and `.github/label-policy.toml`.
Every live `threat:*` assignment is therefore a leftover from the retired
per-item regime, and the bulk cleanup is a single owner-driven, dry-run-first
operation rather than a recurring per-item manual sweep:

1. **Dry-run first.** List the open (and recently closed) issues and PRs still
   carrying a `threat:*` label so the deletion scope is visible before any
   mutation (`gh issue list --label threat:intel-needed`,
   `gh issue list --label threat:response-needed`, plus the `gh pr list`
   equivalents, or the GraphQL / MCP search equivalents).
2. **Remove the assignments via the prune dispatch.** Because the definitions
   are gone from `.github/labels.json`, dispatching `apply-labels.yml` with
   `dry_run=true, prune=true` first (confirm only `threat:intel-needed` and
   `threat:response-needed` appear under `plan-only (DELETE)`), then
   `dry_run=false, prune=true`, deletes both labels from every issue and PR in
   one operation. This is destructive on existing assignments per *Apply* and
   *Rollback* above; re-adding a definition does not restore assignments.
3. **Delete the per-item evidence comments.** The old per-item evidence comments
   anchored by the retired marker `<!-- threat-intel-triage v1 -->` are not
   touched by the label prune; delete them per item (owner-driven, confirm
   first). The current aggregated comment uses a different marker
   (`<!-- threat-intel-aggregate v1 -->`) on the #178 umbrella and is left in
   place.
4. **Record the sweep** -- items reviewed, labels removed, evidence comments
   deleted, and any systemic cause -- in a dated comment on
   [#1076](https://github.com/tvna/claude-md/issues/1076).

A manual per-label `gh issue edit --remove-label` sweep remains the fallback if
the prune dispatch is unavailable, but the prune is the single-operation path
now that the definitions are retired.

### Why EPSS is advisory-only (no auto-escalation threshold)

KEV records vulnerabilities **observed** in active exploitation. EPSS is a probabilistic forecast of exploitation likelihood. The two signals are complementary, not interchangeable:

- KEV correlation is rare and unambiguous: when it fires, response action is warranted.
- EPSS distributes across the entire CVE population; even a 0.95 score still admits false positives, and choosing a threshold without observed false-positive data would lock automation into a guess.
- The `response_needed` classification (formerly the `threat:response-needed` label) is the confirmed-exploitation signal recorded on the #178 umbrella and requires investigation. A probabilistic signal raising that flag would generate review load that does not match a confirmed-exploitation incident.

A future sub-issue may revisit this once distribution data has been observed on real findings; until then the score is surfaced for human prioritization only.

### Response handoff

The `threat:*` labels are routing flags, not remediation triggers. No workflow in this repository converts a `threat:*` label into a dependency bump, a workflow-pin change, or any other code or configuration edit. This section records the human-in-the-loop boundary that must hold before an agent applies an autonomous fix on the basis of a threat-intelligence finding (Operating loop item 5 of [#170](https://github.com/tvna/claude-md/issues/170)), alongside the source-selection policy from [#177](https://github.com/tvna/claude-md/issues/177) above.

**What counts as an autonomous fix.** Any security-relevant change an agent would land without a human authoring or signing off on the diff first: a dependency version bump in `pyproject.toml` / `uv.lock`, a GitHub Actions pin update (`uses: owner/repo@<sha>` plus the trailing `# <tag>`), a transient `uv run --with name==version` bump, or any workflow/config edit proposed *because* a finding fired (for example, a pin update triggered by a KEV match). Opening a PR for a human to review is **not** an autonomous fix; pushing the change to `main` or merging it without that review **is**.

**Approval gate -- no finding authorizes an autonomous fix.** A `response_needed` classification (CISA KEV correlation, a GHSA `malware` advisory, or an OSSF `MAL-` finding, per the precedence above) is the confirmed-exploitation signal, recorded on the #178 umbrella. Since [#1645](https://github.com/tvna/claude-md/issues/1645) it no longer applies a per-item label and therefore no longer mechanically blocks an autonomous PR on the triggering item; that block was intentionally retired because the finding is repository-global and the per-item label was pure noise. The human-in-the-loop boundary is unchanged and does not depend on that block: there is **no finding severity and no fully-automated exception** under which a threat-intelligence finding permits an agent to land a dependency or configuration change -- a human must author or sign off on the remediation diff. The only changes that proceed without a per-finding human sign-off are Dependabot PRs on the explicit allowlist in [`.github/dependabot-automerge.json`](../../.github/dependabot-automerge.json); those are gated by their own CI and review policy and are never triggered by a threat-intelligence finding.

**Notification path.** When the scan classifies a finding as `response_needed`, the alert surfaces in three deterministic places, none of which require reading any issue body: (1) the OSV / GHSA / OSSF / KEV correlation table written to `$GITHUB_STEP_SUMMARY` by the `dependency-threat-triage` job, which names each finding, its source string, and the matched dependency surface; (2) the idempotent, marker-anchored **aggregated comment** the same job posts to the #178 umbrella (see [Aggregated findings on the security umbrella](#aggregated-findings-on-the-security-umbrella)), carrying that correlation table; and (3) GitHub's watch/subscription notifications to the repository owner (`@tvna`, the CODEOWNERS primary owner) who watches #178. The scheduled run also goes red (`--fail-on-intel`), a fourth standing signal. The owner is the responsible responder; assigning a finding is a manual step the owner takes when delegating.

The umbrella comment is the handoff artifact ([#1285](https://github.com/tvna/claude-md/issues/1285), [#1645](https://github.com/tvna/claude-md/issues/1645)): the Step Summary records the *evidence* but lives inside the Actions run log and is unreachable once the run ages out, so a neutral third party cannot explain the triage from the run alone -- the gap CLAUDE.md section 6 names ("make state visible by inspection" before handoff). Co-locating the correlation table on #178 closes it. Reduced confidence is preserved: soft-fail live sources (FIRST EPSS, NVD) are listed in a `Live-source outages (reduced confidence)` note at the top of the comment when their live request fails; OSV / KEV / GHSA / OSSF failures stay loud (the `scan` step exits non-zero and the run goes red), consistent with *"Missing source data is never evidence of safety"* above. The comment is posted as `github-actions[bot]` from a scheduled job, so it never re-triggers triage.

**Escalation when a KEV-correlated finding has no response.** The acknowledgement target is **3 business days** from a `response_needed` finding first appearing on the umbrella; the remediation target is the CISA KEV catalog's published remediation due date for the correlated CVE, or **14 calendar days** when the catalog lists no due date. No deterministic timer enforces these windows yet, so escalation is operator-driven and the interim contract is procedural: open `response_needed` findings are reviewed at every retrospective that touches the triage surface (`scripts/threat_intel_triage.py`, `.github/workflows/weekly-maintenance.yml`, or this runbook) and on the quarterly cadence described under [Threat-intel triage review cadence](#threat-intel-triage-review-cadence), recorded on [#1076](https://github.com/tvna/claude-md/issues/1076). A missed window never relaxes the human-in-the-loop boundary, and per *"Missing source data is never evidence of safety"* above, the absence of a response never downgrades the finding. The finding clears only when it stops firing (for example, the flagged dependency is bumped by a human-reviewed PR). The durable fix -- an automated SLA timer that re-pings the owner and records breaches -- is future work tracked on [#1076](https://github.com/tvna/claude-md/issues/1076); until it lands, the per-retrospective review is the enforcement surface.

## Agent routing

Agents read `(type, state, severity, threat)` from the header alone and apply this table -- **no body fetch is required for routing**:

| Condition | Agent action | Body read? |
|---|---|---|
| `state:rfc` OR `state:parked` | no-action | no |
| `type:tracking` | no-action on umbrella; act on sub-issues only | no |
| `severity:security` (regardless of other labels) | investigate (no autonomous PR) | yes |
| `type:fix` AND NOT `severity:security` | auto-fix candidate (mechanical PR allowed) | yes |
| `type:docs` | auto-fix candidate | yes |
| `type:feat` OR `type:refactor` | investigate -- plan first, implementation awaits approval | yes |
| No `type:*` yet | triage-needed: read title only, set `type:*`, re-route | title only |

Rows are evaluated top-to-bottom; the first match wins. This table is the routing decision -- the labels do not encode the decision themselves. The `threat:*` rows were removed when the labels were retired ([#1645](https://github.com/tvna/claude-md/issues/1645), [#1647](https://github.com/tvna/claude-md/issues/1647)); threat-intelligence findings live on the #178 umbrella, so an agent acts on a finding by reading that umbrella comment, not by waiting for a per-item label.

## Apply

The `Apply labels` workflow (`.github/workflows/apply-labels.yml`) is the only supported apply path. It reconciles `.github/labels.json` against the live label set on GitHub via `workflow_dispatch`: POSTs missing labels, PATCHes labels whose color/description differs, and (when `prune=true`) DELETEs labels absent from SoT. Color/description changes propagate through the same dispatch -- there is no separate update path.

### Required secret

`LABELS_PAT` -- fine-grained PAT scoped to `tvna/claude-md` with `Repository permissions → Issues: Read and write` (the labels endpoints live under Issues in the new PAT scopes). Stored in the `labels-apply` GitHub Environment, not at the repo level.

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

- `dry_run` (default `true`) -- plan only; emit a markdown summary, no live mutation.
- `prune` (default `false`) -- when `true` (and `dry_run=false`), DELETE labels present on GitHub but absent from SoT. Destructive on existing issues: GitHub removes the label from every issue and PR it was applied to.

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
                 (.labels | map(.name) | map(select(. == "severity:security")) | length > 1))
        | .number'
# Must print nothing once Phase 3 is complete. (The retired threat:* axis is no
# longer checked here; any leftover threat:* assignment is cleaned by the
# owner-driven prune dispatch -- see Stale-label handling.)
```

## Rollback

```sh
gh api \
  --method DELETE \
  -H "Accept: application/vnd.github+json" \
  -H "X-GitHub-Api-Version: 2022-11-28" \
  /repos/tvna/claude-md/labels/<name>
```

Deleting a label is **destructive on existing issues** -- GitHub removes the label from every issue and PR it was applied to. Re-dispatching the `Apply labels` workflow restores the label definition (if it is still listed in SoT) but does **not** restore per-issue assignments; those must be re-applied manually (Phase 3 of #84 is the operation log for that).

## Drift detection

A scheduled workflow that diffs the live labels returned by `gh api` against `.github/labels.json` **and** verifies issue coverage (every open issue has ≥1 `layer:*`, exactly 1 `type:*`, ≤1 `state:*`, ≤1 `severity:*`) is planned as Phase 5 of [#84](https://github.com/tvna/claude-md/issues/84) (parked). Until it lands, drift is detected only by manual review during retrospectives.

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
