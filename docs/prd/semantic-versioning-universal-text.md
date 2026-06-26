# Semantic Versioning for Universal Text

Tracking issue: [#89](https://github.com/tvna/claude-md/issues/89)

## Purpose

Decide how the universal text is semantically versioned: which kinds of
change increment MAJOR, MINOR, or PATCH, and how a version tag is assigned
automatically *only* when the universal text changes.

## Background

The universal text - `.apm/instructions/master.instructions.md` and its
compiled artifacts `CLAUDE.md` / `AGENTS.md` (see
`docs/standards/ubiquitous-language.md`, term "universal text") - is
identified today only by git SHA. `apm.yml: version` has been static at
`1.0.0` since the initial commit. A SHA is reliable but not human-readable,
so reviewing change history, citing a baseline in conversation, or
correlating a benchmark record (PR #86 keys on `compiled_source_sha`) with a
known instruction revision all require git tooling. Issue #89 opened to
decide the versioning scheme; the owner selected semantic versioning over
the issue's date-based default. This document records that decision.

## Target Users

- Reviewers and the owner, who assign and read version labels on PRs.
- Downstream consumers who pin a release tag of the compiled instructions
  (`docs/runbooks/consumer-instruction-sync.md`).
- The benchmark record schema, which will gain a human-readable
  `compiled_source_version` companion to the existing SHA.

## Use Cases

- Cite "v1.2.0 -> v2.0.0" in a benchmark before/after instead of two SHAs.
- A downstream consumer reads the version component to gauge whether a sync
  is a breaking change requiring re-review.
- The owner declares a change's severity once (a label) and the harness
  applies and tags it deterministically.

## Goals

- A deterministic-as-possible classifier mapping each change class to a
  semver component, with the human judgment confined to one labelled choice.
- A tag assigned automatically and *only* on a universal-text update.
- Reuse of the existing release/distribution machinery; no new tag
  namespace or distribution workflow.

## Success Metrics

- Every universal-text PR carries exactly one `semver:*` label and a
  matching `apm.yml: version` bump, enforced by CI (zero unlabelled
  universal-text merges).
- Every version change produces exactly one `v{version}` tag; no tag is
  produced without a version change (observable in `git tag` vs `git log`).

## Non-Goals

- Retroactively versioning history before the scheme lands (issue #89
  "Out of scope"): history stays un-versioned; the scheme starts at the
  first universal-text change after it lands.
- Treating the compiled outputs as a programmatic API. `CLAUDE.md` is not
  consumed programmatically; "compatibility" here means backward
  compatibility of behavioral expectations for downstream consumers, not API
  signatures.
- The benchmark-record wiring (`compiled_source_version`, `schema_version`
  bump). It depends on this scheme but is a separate change surface; see
  Release Plan.

## Requirements

### R1 - Increment classification (compatibility-based)

The basis is backward compatibility for a downstream consumer already
compliant with version N. Evaluate the decision tree top to bottom; the
first match wins.

1. **Non-normative surface only** (typo, whitespace, formatting, reflow,
   link fix, translation of a non-source file, or a rewording that provably
   preserves the rule's meaning) -> **PATCH**.
2. **Breaks backward compatibility** - any of:
   - removes, reverses, or weakens an existing rule / principle / hardline
     (e.g. `MUST` -> `SHOULD`, removing "No exceptions", adding an in-line
     carve-out to a hardline);
   - tightens a constraint so a behavior compliant under version N becomes
     non-compliant (a new prohibition or new mandatory obligation that
     retroactively invalidates prior-compliant behavior);
   - breaks a stable reference: renumbering P1-P6, renaming or removing a
     section anchor the harness or another doc keys on, changing a
     `ubiquitous-language` term's meaning, or changing trust precedence;

   -> **MAJOR**.
3. **Otherwise** - a backward-compatible addition or clarification that does
   not retroactively make prior-compliant behavior non-compliant (new rule,
   principle, section, example, or supplementary guidance) -> **MINOR**.

The single boundary question separating MAJOR from MINOR:

> Could a consumer compliant with version N become non-compliant under
> version N+1 *without changing its behavior*?

Yes -> MAJOR (the consumer must re-review and possibly act). No -> MINOR
(purely additive / permissive / clarifying). When a PR mixes classes, the
**highest** component wins (MAJOR > MINOR > PATCH).

Worked examples:

| Change | Component | Why |
|---|---|---|
| Fix a typo in a P4 bullet | PATCH | non-normative surface |
| Translate a README into a new language | PATCH | rule meaning unchanged |
| Reword a sentence, meaning preserved | PATCH | normative meaning unchanged |
| Add a permissive sub-bullet under P3 | MINOR | forbids nothing previously allowed |
| Add a wholly new principle section | MINOR | existing compliance still holds |
| Add a new hardline prohibition | MAJOR | a consumer doing X was compliant, is not now |
| `MUST` -> `SHOULD` on an existing rule | MAJOR | weakens a relied-on rule |
| Remove a bullet downstream relied on | MAJOR | rule removed |
| Renumber P1-P6 or rename a section anchor | MAJOR | breaks stable references |
| Change a `ubiquitous-language` term meaning | MAJOR | alters obligations keyed on the term |

### R2 - Canonical version and tag

- `apm.yml: version` is the single source of truth (currently `1.0.0`).
- The release tag is `v{version}` (e.g. `v1.1.0`): a short, conventional
  `v`-prefixed tag.
- `publish-instructions-release.yml` is migrated to trigger on `v*` (from
  `instructions-v*`) and to validate the `v` prefix. No tags exist yet
  (`git tag -l` is empty), so this prefix migration breaks nothing.

### R3 - Version-relevant change set

A PR is "universal-text-touching" if its diff modifies any of:
`.apm/instructions/master.instructions.md`, `CLAUDE.md`, `AGENTS.md`. A
dependency-driven recompile that changes the compiled body is
universal-text-touching and is classified by the same R1 tree (usually PATCH
or MINOR).

### R4 - Bidirectional drift gate (the core invariant)

A CI gate forbids a one-sided update of the
{universal text, `apm.yml: version`} pair in either direction. It is
implemented as a `scripts/` gate (`scripts/verify_source_version_bump.py`)
wired as a step into the existing `verify-pr.yml` `portable-pr-policy` job and
mirrored in `scripts/preflight_all.py` (the repository's standard gate
pattern), rather than a new standalone workflow. Invariant:
**"the universal text changes if and only if `apm.yml: version` is bumped,
and the bump component matches the declared label."** On every PR:

- universal-text-touching but version not bumped -> **fail** (drift).
- version bumped but not universal-text-touching -> **fail** (drift).
- both change together:
  - exactly one `semver:*` label present (else fail);
  - new version strictly greater than base by semver comparison (else fail);
  - the incremented component equals the label (else fail).

Every failure is loud with an actionable message (CLAUDE.md section 4: no
silent default). This drift gate is the deterministic enforcement required
by CLAUDE.md section 3, shipped in the same change that establishes the
version-bump invariant (the "ship the drift gate with the invariant" rule;
see `ubiquitous-language.md` term "drift gate"). It is paired with
`tests/test_verify_source_version_bump.py` per
`docs/standards/workflow-script-quality.md`. The pre-push mirror cannot read
PR labels (labels are repository state, not git-tracked), so it passes
`labels=None`: the text-vs-version iff and the clean single-component bump are
still enforced before push, and only the label-match is deferred to the CI
step, which reads `PR_LABELS`.

### R5 - Post-merge auto-tag

After merge to the default branch, a step in `post-merge.yml`:

1. reads `apm.yml: version` at the merge commit and its first parent;
2. if the version changed, creates and pushes tag `v{version}`;
3. is idempotent: an existing tag is a no-op (no force, no overwrite).

Because R4 guarantees the version changes only when the universal text
changes (and vice versa), the tag is created only on a universal-text
update - satisfying "assign a tag automatically only when the universal text
is updated". The new tag triggers the existing release publish flow.

## Why

Compatibility-based semantics make "breaking for downstream consumers" the
one judgment a human supplies, and a single PR label encodes it. Anchoring
on `apm.yml: version` reuses an existing field and the existing
`v`-tag-triggered release flow, adding no parallel versioning surface. The
bidirectional drift gate is what makes "only when the universal text is
updated" true by construction rather than by reviewer memory.

## Why not

- Date-based (`YYYY.MM.DD`): chronological but signals no severity; rejected
  because the owner wants the breaking/additive/fix signal.
- Conventional Commits auto-classification: fully automatic but misclassifies
  semantic breakage (a machine cannot reliably tell a weakened hardline from
  an added example); rejected in favour of human-declared severity.
- Fully manual (edit `apm.yml`, hand-tag): no automation; rejected because
  the owner wants the tag assigned automatically on universal-text updates.

## Considered Alternatives

| Option | Decision | Reason |
|---|---|---|
| Scheme: semver vs date-based vs PR-number | semver (compatibility-based) | owner choice; carries severity (fact: issue #89 selection) |
| Version home: `apm.yml` vs separate file | `apm.yml: version` | already exists; one source of truth |
| Tag: `v{version}` vs `instructions-v{version}` | `v{version}` | owner choice: shorter; no existing tags to break |
| Classification: label vs commits vs manual | PR label + CI verify | human severity judgment, automated application |

## Acceptance Criteria

- [ ] `scripts/verify_source_version_bump.py` (wired into `verify-pr.yml` and mirrored in `scripts/preflight_all.py`) + `tests/test_verify_source_version_bump.py` land and enforce R4 in both directions.
- [ ] `post-merge.yml` auto-tags `v{version}` on a version change (idempotent).
- [ ] `publish-instructions-release.yml` triggers on `v*` and validates the `v` prefix.
- [ ] `semver:major` / `semver:minor` / `semver:patch` labels exist in the label taxonomy.
- [ ] Consumer docs reference the `v{version}` tag scheme consistently.

## Scope

In scope: the classification rule (R1), version home and tag (R2), the
change-set trigger (R3), the drift gate (R4), and the auto-tag (R5), plus the
label-taxonomy and consumer-doc updates needed for consistency.

Out of scope: the benchmark-record wiring and the README "Versioning"
section (tracked under Release Plan as dependent follow-ups).

## Priority

Drives issue #89 to resolution. R4 (the drift gate) is the gating piece;
R5 (auto-tag) depends on R4's invariant; the consumer-doc and label updates
are low-risk companions.

## Release Plan

1. Land R1-R5 (the scheme, drift gate, auto-tag, prefix migration) plus the
   `semver:*` labels and consumer-doc tag-scheme updates.
2. Follow-up (separate change surface, issue #89 acceptance): add
   `compiled_source_version` to the benchmark record and bump
   `schema_version` to `"3"` in `docs/standards/performance-metrics.md`
   (coordinated with #88's `"2"`); add a "Versioning" section to the READMEs.

Files this scheme touches when implemented (CLAUDE.md section 5 - narrow
surface):

- `scripts/verify_source_version_bump.py` (drift gate) wired as a step in `.github/workflows/verify-pr.yml` (`portable-pr-policy` job) and mirrored in `scripts/preflight_all.py` + `tests/test_verify_source_version_bump.py`.
- `scripts/auto_tag_version.py` (post-merge auto-tag) + `tests/test_auto_tag_version.py`.
- `.github/workflows/post-merge.yml` (auto-tag job).
- `.github/workflows/publish-instructions-release.yml` (`instructions-v*` -> `v*`).
- `.github/labels.json` / `docs/standards/label-taxonomy.md` (`semver:*` labels).
- `docs/runbooks/consumer-instruction-sync.md` and `docs/proposals/instruction-distribution-mechanism.md` (tag-example updates).

## Milestones

N/A - single-phase delivery plus one follow-up; tracked in issue #89.

## Edge cases and open questions

- **Mixed-class PR**: highest component wins (R1).
- **Tag already exists / re-merge**: R5 is idempotent.
- **Compiled drift at tag**: `publish-instructions-release.yml` already
  re-compiles at the tag and fails on drift; no new drift surface.
- **Open - label as source of truth**: labels are repository state, not
  git-tracked. If label-vs-bump consistency must survive post-merge label
  edits, a follow-up could record the declared component in the PR body. For
  v1 the CI gate at merge time is the contract; flagged as a known limit.
- **Open - translated READMEs**: only the three files in R3 are the
  version-relevant set; README translations are PATCH-class doc changes
  outside the trigger set unless they alter those three files.

## Graduation Path

Once R1-R5 land and the scheme is exercised on a real universal-text PR, the
adopted yes/no rules (the R1 classification table and the R4 invariant) move
to `docs/standards/` as a versioning standard, with this document retained as
the decision rationale. The operator bump procedure graduates to a short
section in `docs/runbooks/` or the README per issue #89's acceptance.

## References

- [#89](https://github.com/tvna/claude-md/issues/89) - versioning decision (home issue).
- `docs/standards/ubiquitous-language.md` - "universal text", "drift gate".
- `docs/prd/agent-rules-design-philosophy.md` - what "universal" means (section 2.1).
- `.github/workflows/publish-instructions-release.yml` - existing tag-driven release flow.
- `.github/workflows/post-merge.yml` - post-merge automation extended by R5.
- `apm.yml` - canonical `version` field.
- [#86](https://github.com/tvna/claude-md/pull/86), [#88](https://github.com/tvna/claude-md/issues/88) - benchmark schema coordination.
