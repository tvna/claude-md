# Label Taxonomy Standard

This standard is the adopted design contract for repository labels after
issue #970. The live label catalog remains `.github/labels.json` until the
migration issue #972 applies the design. The machine-readable design source
is `.github/label-policy.toml`.

## Scope

The taxonomy answers three questions:

- What kind of work is this?
- Which repository area can conflict with the change?
- Which lifecycle, safety, or operational state changes routing?

This document is normative for new design decisions. It does not mutate live
GitHub labels by itself.

## PR Boundary

A PR may not be opened for a broad label-design topic until scoped child
issues exist for the intended change. Tracking issues are coordination
objects; implementation PRs act on child issues. If a proposed PR mixes
documentation, automation migration, and live prune work, split it before
opening the PR.

Retro is the only explicit exception: retrospective automation may open
operational follow-up issues after merge because the evidence exists only
after the terminal PR event. That exception does not create `area:retro`.

## Source Of Truth

| File | Role |
|---|---|
| `.github/label-policy.toml` | Adopted design contract and target label policy |
| `.github/labels.json` | Live GitHub label apply source; the #972 renames batch (#2139) flips its five renamed entries |
| `docs/standards/label-taxonomy.md` | Human-readable taxonomy standard |
| `docs/runbooks/issue-triage.md` | Operator procedure and routing runbook |

The TOML policy records target labels, family cardinality, rename sources,
retired labels, and area-to-path mappings. The JSON catalog now carries the
five final rename names (#972 renames batch, #2139); `labels_apply.py` reads the
`rename_from` map from this TOML to rename the live labels in place so existing
assignments are preserved. Retirements and area additions are otherwise
deferred to later #972 batches and must not be applied to the catalog before
then. The one exception: `area:ci-ops`, `area:governance`, and
`area:security-intel` were added to the live catalog ahead of that batch, per
the owner's `layer:meta` successor decision (#1041 comment 4882932274, #2313)
and the scoped `[rollout].area_addition_exception` entry in
`.github/label-policy.toml`. No other area label is affected; the remaining
#972 area batch stays deferred.

For the labels shared by both files, `.github/label-policy.toml` `[[labels]]`
is the single authored source of truth for label identity (name, description,
color); `.github/labels.json` must match it. `scripts/scan_label_sot_drift.py`
is the deterministic gate that enforces this parity and fails on any drift
(Refs #2442, Phase A). The `retro:*` labels and `type:retrospective` are
exempt because they are sourced from `scripts/_retro_labels.py`, not the TOML;
the 11 `area:*` labels declared only in `[[labels]]` are not yet in the live
catalog and are validated only in the labels.json-to-policy direction.

## Final Label Families

Every final label belongs to exactly one declared family.

| Family | Cardinality | Purpose |
|---|---|---|
| `layer:*` | One or more | CLAUDE.md principle responsibility |
| `type:*` | Exactly one for normal issues | Issue purpose or structural kind |
| `state:*` | Zero or one | Lifecycle and actionability |
| `severity:*` | Zero or one | Human safety or content sensitivity |
| `area:*` | One or more for active implementation | File and directory ownership or conflict domain |
| `ops:*` | As required by deterministic workflows | Workflow, bot, or maintenance state |
| `semver:*` | Exactly one for universal-text PRs | Declared semantic-version severity of a universal-text change |

Labels outside these families are retired unless the policy file adds an
explicit grandfathered exception with a removal deadline.

## Layer Labels

Layer labels follow the current CLAUDE.md responsibilities. `layer:meta` is
retired because it hides ownership instead of naming the affected principle.

| Final label | Migration | Meaning |
|---|---|---|
| `layer:p1-goal-plan` | keep | Goal, plan, and verification structure |
| `layer:p2-input-boundary` | rename from `layer:p2-precode` | Trusted inputs, unknowns, facts, assumptions, and ambiguity |
| `layer:p3-harness` | keep | Issues, CI, hooks, dependencies, and PR loop |
| `layer:p4-safety-boundary` | rename from `layer:p4-artifact` | Simplicity bounded by safety, tool scope, and secret exposure |
| `layer:p5-scale-quality` | rename from `layer:p5-scope-split` | Change scope, agent split, and quality proportional to scale |
| `layer:p6-handoff` | keep | Handoff, communication, and operator-language output |
| `layer:meta` | drop | No replacement; use the concrete layer plus `area:area-policy` when needed |

## Type And State Labels

`type:*` remains the purpose axis. `type:tracking` remains structural and
must not be moved into `state:*` because a tracking issue can also be RFC or
parked.

| Label | Rule |
|---|---|
| `type:feat` | New behavior or rule |
| `type:fix` | Defect or broken workflow |
| `type:refactor` | Restructure without behavior change |
| `type:docs` | Operator docs, standards, or README changes |
| `type:tracking` | Umbrella issue coordinating scoped child issues |
| `state:rfc` | Proposal is open but not yet actionable |
| `state:parked` | Explicitly deferred until new evidence or owner decision |

No-action routes are `state:rfc`, `state:parked`, and `type:tracking`.
Tracking issues may carry broad areas, but agents act on children.

Each `type:*` label's stem must match a commit type declared in
`.github/title-policy.toml` `[title_policy].types`; set `commit_type = false`
on any `type:*` label that is intentionally not a commit type (currently only
`type:tracking`). This is enforced by `scripts/scan_commit_type_label_drift.py`
(Refs #2081).

Apply `type:tracking` only when both conditions hold:

1. **Sub-issue umbrella**; the issue coordinates one or more child issues
   and takes no direct implementation commit itself; it closes only when all
   children close.
2. **1-issue/N-PR**; multiple PRs reference it with non-closing `Refs #N`
   and none of them closes it on its own. The label is the structural
   requirement that lets those Refs-only PRs pass `verify-issue-link.yml`
   (`scripts/issue_link.py`), which otherwise rejects a Refs-only body unless
   the referenced issue carries `type:tracking`.

Do not apply `type:tracking` to an issue that a single PR closes via
`Closes #N`, including a one-off retrospective. The title type is independent:
pick the conventional type that fits the work (for example `chore`, `docs`,
or `ci`) and mark the umbrella with the label, not with the title prefix.

### Retrospective Issue Kind Label

One-off retrospective issues (`chore(auto-retro): review PR #N repair loops`,
detected by `scripts/auto_retro.py:is_retro_issue_title`) are closed by a
single retro PR, so they are normal issues under the `type:*` exactly-one
rule. Their canonical kind label is `type:docs`: a retrospective records an
operator-facing process finding and none of `feat`/`fix`/`refactor` fits.
They must not carry `type:tracking` (a single PR closes them; see the
`type:tracking` rule above), and the ad-hoc `retrospective` and
`type:retrospective` labels are not declared families and must not be used.

The title prefix is `chore(auto-retro)`, not `fix(auto-retro)` (Refs #1069).
A retro issue is a triage signal, not a unit of work to implement directly,
so the neutral `chore` prefix avoids the `fix(...)` reading that invited a
direct implementation PR off an un-triaged retro. `is_retro_issue_title`
also recognizes the legacy `fix(auto-retro)` prefix for closed historical
retros. A PR that links a retro issue must itself be a retro-close PR (a
`type(auto-retro): ...` title); `scripts/auto_retro.py verify-no-direct-retro-pr`
(wired into `.github/workflows/verify-pr.yml`) rejects any other PR
that closes or references a retro issue, so triage cannot be skipped.

As of PR #2383, `scripts/auto_retro.py` no longer emits the retired
`layer:meta` on a newly opened retro: its create-time identity set
(`_identity_labels`) is `layer:p3-harness` + `area:ci-ops` alongside
`type:docs` (successor decided at #1041 comment 4882932274). The
retro-discovery queries in `fetch_past_retro_labels`,
`search_open_retro_issues`, and `scripts/scan_retro_followup_drift.py`
no longer key on a bare `label:layer:meta`; they now use a family-grouped
OR of `layer:meta` and `layer:p3-harness` (via
`_ssot.group_labels_by_family`, since `_discovery_labels` retains the
retired label for search only) so retros filed before and after the
migration both stay discoverable. `layer:meta` therefore survives in the
registry entry as a deliberate transition aid; its removal from the live
catalog and the registry is tracked by #2393. Refs #1060, #1050, #2313,
#1041, #2383.

## Severity Labels

| Label | Writer | Routing effect |
|---|---|---|
| `severity:security` | Human or security workflow | Bias toward investigation |
| `severity:non-ascii-content` | Non-ASCII content scan | Content-boundary signal |

The `threat:*` overlay axis (`threat:intel-needed`, `threat:response-needed`)
was **retired** in [#1647](https://github.com/tvna/claude-md/issues/1647),
following the [#1645](https://github.com/tvna/claude-md/issues/1645) consolidation
that stopped auto-applying the labels per issue/PR. Threat-intelligence findings
are repository-global, so `scripts/threat_intel_triage.py` aggregates them into a
single idempotent comment on the #178 security umbrella (posted weekly by the
`dependency-threat-triage` job in `.github/workflows/weekly-maintenance.yml`)
instead of stamping a label onto whichever item triggered a run. The
`intel-needed` / `response-needed` *classifications* survive only as descriptors
in that aggregated comment, not as live labels. The label definitions were
removed from `.github/labels.json` and `.github/label-policy.toml`, and the
live per-item assignments are swept by the owner-driven prune dispatch. Source
outages do not prove safety. See
[`docs/runbooks/issue-triage.md`](../runbooks/issue-triage.md#threat-retired)
for the aggregation mechanism and the cleanup procedure.

## Semver Labels

Semver labels are the human-declared severity of a change to the universal
text (`.apm/instructions/master.instructions.md` and the compiled `CLAUDE.md`
/ `AGENTS.md`). Exactly one is required on a universal-text-touching PR, and
it must match the `apm.yml: version` bump component. The classification rule
is the R1 decision tree in
[`docs/prd/semantic-versioning-universal-text.md`](../prd/semantic-versioning-universal-text.md);
enforcement is the source version drift gate
(`scripts/verify_source_version_bump.py`, wired into
`.github/workflows/verify-pr.yml` and mirrored in
`scripts/preflight_all.py`).

| Label | R1 class | Meaning |
|---|---|---|
| `semver:major` | Breaks backward compatibility | Removes, reverses, or weakens an existing rule; tightens a constraint so prior-compliant behavior is non-compliant; or breaks a stable reference (P1-P6 numbering, a keyed anchor, a ubiquitous-language term, trust precedence) |
| `semver:minor` | Backward-compatible addition | New rule, principle, section, example, or clarification that does not retroactively invalidate prior-compliant behavior |
| `semver:patch` | Non-normative surface | Typo, whitespace, formatting, reflow, link fix, translation, or a meaning-preserving reword |

A mixed-class PR takes the highest component (MAJOR > MINOR > PATCH). These
labels apply only to universal-text PRs; non-universal-text PRs carry none.

## Area Labels

Area labels name the conflict domain. They do not replace `layer:*`; a change
needs both responsibility and file ownership context.

| Area | Primary paths |
|---|---|
| `area:agent-instructions` | `CLAUDE.md`, `AGENTS.md`, `.agents/**` |
| `area:apm` | `.apm/**`, `apm.yml`, `apm.lock.yaml` |
| `area:hooks` | `.claude/settings.json`, `.codex/hooks.json`, `.githooks/**`, `.pre-commit-config.yaml`, `docs/runbooks/prek.md` |
| `area:preflight` | `scripts/preflight_*.py`, `scripts/gate_*.py`, `scripts/check_*.py`, `scripts/scan_*.py`, `scripts/verify_*.py`, and individual policy gate scripts; preflight runbooks |
| `area:github-workflows` | `.github/**`, ruleset and workflow runbooks, generated workflow diagrams |
| `area:scripts-tests` | `scripts/**`, `tests/**` |
| `area:docs` | `README*.md`, `docs/**` |
| `area:toolchain` | `pyproject.toml`, `uv.lock`, `flake.nix`, `flake.lock`, uv/install scripts, toolchain standards |
| `area:devcontainer` | `.devcontainer/**`, devcontainer runbook |
| `area:security-intel` | Threat triage, security drift, non-ASCII defense, and security runbooks |
| `area:metrics` | `metrics/**`, performance, maintainability, and host-unit metric docs/scripts |
| `area:area-policy` | Label policy, label catalog, issue triage, and label apply code |
| `area:ci-ops` | CI automation scripts, issue/PR operation utilities, and maintenance workflows |
| `area:governance` | Repo structure analysis, document dependency graph, and governance tooling |

When a path matches more than one area, apply every relevant area. For
example, `.github/workflows/post-merge.yml` with coverage-failure behavior is
both `area:github-workflows` and, if it changes coverage routing, the
affected quality area. `.pre-commit-config.yaml` is `area:hooks`; uv version
or lockfile changes are `area:toolchain`; universal instruction text changes
are `area:agent-instructions` and may also be `area:apm` when they change APM
source or compiled output.

Coverage is intentionally conservative: a new top-level directory, hidden
configuration directory, or generated-document lane must add an `area:*`
mapping in the same design issue that introduces it.

## Operational Labels

Operational labels use the `ops:*` prefix and are excluded from normal
taxonomy cardinality checks. Each one must declare a writer, reader,
lifecycle, human meaning, and failure behavior.

| Label | Migration | Writer | Reader |
|---|---|---|---|
| `ops:dependencies` | rename from `dependencies` | Dependabot and dependency-maintenance workflows | dependency automerge, dependency freshness, operator queues |
| `ops:retro-opened` | rename from `harness:retro-opened` | auto-retro and post-merge retrospective automation | auto-retro sentinel, rescan, duplicate-retro prevention |

Do not add broad labels such as `ops:quality`. Lint, type, security,
maintainability, and coverage checks are quality gates. They become `ops:*`
labels only when a deterministic writer and reader create a machine-tracked
operational queue.

## Retired Labels

The migration issue must prune these labels only after replacements are
assigned and the dry-run delete plan is reviewed.

| Label | Reason |
|---|---|
| `layer:meta` | Responsibility is unstable and overlaps the typed axes |
| `agent:*` | Old routing design replaced by typed axes |
| `bug` | Duplicate of `type:fix` |
| `question` | Noisy state; use `state:rfc`, `state:parked`, or a scoped issue |
| `enhancement` | Duplicate of `type:feat` |
| `fix` | Duplicate of `type:fix` |
| `governance` | Recreates retired `layer:meta` ambiguity |

## Migration Boundary

Issue #972 owns rollout. It must update label writers, readers, issue
templates, tests, backfill assignments, and then run `apply-labels.yml` with
`prune=true` only after the dry-run plan contains exactly the authorized
delete set.

For retrospectives specifically, the label re-key has already landed ahead
of the broader #972 rollout, via #2313 (PR #2383):
`scripts/auto_retro.py` no longer emits `layer:meta` on a newly opened retro
(`_identity_labels` now yields `layer:p3-harness` + `area:ci-ops`), and retro
discovery in `scripts/auto_retro.py` (`fetch_past_retro_labels`,
`search_open_retro_issues`) and `scripts/scan_retro_followup_drift.py` was
re-keyed onto a family-grouped OR of `layer:meta` and `layer:p3-harness`
(via `_ssot.group_labels_by_family`), not the `is_retro_issue_title` predicate
originally sketched here. The residual retro work is the live-catalog and
registry removal of `layer:meta`, owned by #2393; the #963/#929/#957 backfill
to `type:docs` (removing `type:tracking`, `retrospective`, and
`type:retrospective`) and the prune of the undeclared `retrospective` /
`type:retrospective` labels remain with #972. Refs #1060, #2313, #2383, #2393.
