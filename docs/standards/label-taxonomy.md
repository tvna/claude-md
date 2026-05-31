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
| `.github/labels.json` | Current live GitHub label apply source until #972 migrates it |
| `docs/standards/label-taxonomy.md` | Human-readable taxonomy standard |
| `docs/runbooks/issue-triage.md` | Operator procedure and routing runbook |

The TOML policy records target labels, family cardinality, rename sources,
retired labels, and area-to-path mappings. The JSON catalog must not be
changed until the migration issue executes the rollout.

## Final Label Families

Every final label belongs to exactly one declared family.

| Family | Cardinality | Purpose |
|---|---|---|
| `layer:*` | One or more | CLAUDE.md principle responsibility |
| `type:*` | Exactly one for normal issues | Issue purpose or structural kind |
| `state:*` | Zero or one | Lifecycle and actionability |
| `severity:*` | Zero or one | Human safety or content sensitivity |
| `threat:*` | Zero to two | Threat-intelligence overlay |
| `area:*` | One or more for active implementation | File and directory ownership or conflict domain |
| `ops:*` | As required by deterministic workflows | Workflow, bot, or maintenance state |

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

## Severity And Threat Labels

`threat:*` is retained as an overlay axis because it records security
intelligence state, not repository ownership or issue purpose.

| Label | Writer | Routing effect |
|---|---|---|
| `severity:security` | Human or security workflow | Bias toward investigation |
| `severity:non-ascii-content` | Non-ASCII content scan | Content-boundary signal |
| `threat:intel-needed` | `issue-pr-triage.yml` / `scripts/threat_intel_triage.py` | Collect threat intelligence before ordinary routing |
| `threat:response-needed` | `issue-pr-triage.yml` / `scripts/threat_intel_triage.py` | Block autonomous PRs until response planning occurs |

Threat labels may be removed only when the finding is proven stale, false
positive, or remediated in the linked evidence trail. Source outages do not
prove safety.

## Area Labels

Area labels name the conflict domain. They do not replace `layer:*`; a change
needs both responsibility and file ownership context.

| Area | Primary paths |
|---|---|
| `area:agent-instructions` | `CLAUDE.md`, `AGENTS.md`, `.agents/**` |
| `area:apm` | `.apm/**`, `apm.yml`, `apm.lock.yaml` |
| `area:hooks` | `.claude/settings.json`, `.codex/hooks.json`, `.githooks/**`, `.pre-commit-config.yaml`, `docs/runbooks/prek.md` |
| `area:preflight` | `scripts/preflight_*.py`, `scripts/gate_*.py`, `scripts/check_*.py`, preflight runbooks |
| `area:github-workflows` | `.github/**`, ruleset and workflow runbooks, generated workflow diagrams |
| `area:scripts-tests` | `scripts/**`, `tests/**` |
| `area:docs` | `README*.md`, `docs/**` |
| `area:toolchain` | `pyproject.toml`, `uv.lock`, `flake.nix`, `flake.lock`, uv/install scripts, toolchain standards |
| `area:devcontainer` | `.devcontainer/**`, devcontainer runbook |
| `area:security-intel` | Threat triage, security drift, non-ASCII defense, and security runbooks |
| `area:metrics` | `metrics/**`, performance, maintainability, and host-unit metric docs/scripts |
| `area:area-policy` | Label policy, label catalog, issue triage, and label apply code |

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
| `ops:coverage-failure` | add | `post-merge.yml` and `scripts/coverage_failure_issue.py` | coverage repair queues and post-merge operational triage |

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
