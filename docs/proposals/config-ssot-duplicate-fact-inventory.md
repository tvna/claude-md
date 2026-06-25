# Config SSoT Duplicate-Fact Inventory

Tracking issue: [#1984](https://github.com/tvna/claude-md/issues/1984)

This proposal inventories facts that are currently duplicated across
configuration files (`*.toml`, `*.yaml`/`*.yml`, and the markdown standards
that pair with them), inside and outside `docs/`, and evaluates whether
single-sourcing them would improve the single-source-of-truth (SSoT) posture.
It is a `proposals/` document (not `prd/` or `standards/`) because the
remediation decision for each candidate is not yet decidable: each one needs a
human yes/no on which of three disciplines to apply, and that choice is the
open question this document leaves to the owner. No code or config is changed
here; remediation is deferred to follow-up issues.

## Problem

- Fact: the original prompt asked whether "consolidating the toml files into a
  single file" carries merits. A prior analysis (this branch) concluded that
  physical consolidation of files with distinct owners, lifecycles, and
  enforcing scripts degrades SSoT rather than improving it, because it collapses
  CODEOWNERS boundaries, mixes a high-churn generated snapshot with low-churn
  hand-maintained declarations, and turns four independent drift gates into one
  single point of failure.
- Fact: the follow-up question reframed the goal as "improve SSoT by integrating
  with toml/yaml outside `docs/`." The SSoT win is therefore NOT physical file
  merging. It is the elimination of duplicated facts: a single value, list, or
  identifier that is copied into more than one place and can drift between them.
- Fact: this repository already encodes two disciplined patterns for a shared
  fact. Naming them makes the recommendation framework concrete:
  - single-source-and-read: the fact lives in exactly one declarative file and
    every consumer reads it at runtime. Examples: `.github/owners.toml`
    (`@tvna` -> `ja`, read by `scripts/plan_language_context.py`);
    `.github/tracking-issues.toml` (every CI-written issue number, resolved at
    runtime by its listed consumers).
  - duplicate-but-gate: the fact is intentionally repeated where a single source
    is impractical, and a deterministic drift gate fails CI when the copies
    disagree. Example: the Python version is pinned in `.python-version`,
    `pyproject.toml` `requires-python`, and mypy `python_version`, with
    `.github/workflows/verify-agents.yml` keeping the pin from drifting from
    `requires-python`.
- Fact: a true SSoT gap is therefore a fact that is duplicated with NEITHER a
  single source NOR a drift gate. Those are the only candidates that warrant
  remediation; everything else is already disciplined and should be left alone.

## Methodology

The scan is reproducible. Each observation below was produced by an axis-based
search over tracked `*.toml`, `*.yaml`/`*.yml`, `*.py`, and `*.md` files,
excluding `.venv/` and `node_modules/`. The five axes:

- numeric thresholds and budgets (e.g. size limits, coverage floors);
- enumerations (e.g. commit types, label sets, allowlists);
- identifiers (e.g. issue numbers, owner handles, language codes);
- hardcoded paths (a path string that is itself a duplicated fact);
- version pins (language and tool versions).

For each candidate the report records: the fact, every location it appears,
whether a single source or a drift gate already governs it, and the
classification below.

Classification:

- Class A (true gap): duplicated, no single source, no drift gate.
- Class B (single-sourced): one declarative source, consumers read it. Keep.
- Class C (duplicate-but-gated): repeated but a drift gate enforces agreement.
  Keep.
- Class D (weak or non-duplicate): partial projections of one concept, or
  complementary facts that only look duplicated. Judge case by case.

## Inventory

### Class A: true gaps (remediation candidates)

None. The single candidate first flagged for this class, the module-size budget
`800` / `640`, was disproven on inspection: the value is already single-sourced
via a Python import, so it belongs in Class B and is recorded as B3 below
(including the one minor residual coupling it still carries). The investigation
therefore found no config-file fact that is duplicated with neither a single
source nor a drift gate.

### Class B: single-sourced (keep, models to imitate)

#### B1. Coverage floor `fail_under = 95.00`

- Fact: the blocking coverage threshold lives only in `pyproject.toml`
  (`[tool.coverage.report] fail_under = 95.00`, annotated as "the authoritative
  blocking gate"). `codecov.yml`, `.github/workflows/post-merge.yml`, and
  `.github/workflows/verify-agents.yml` reference it in comments but do NOT
  restate the number ("No --cov-fail-under here: the threshold lives only in
  ... pyproject.toml"). The separate `PER_FILE_FLOOR = 90.0` in
  `scripts/preflight_coverage.py` is a different concern (per-file vs aggregate),
  not a duplicate.
- Recommendation: keep. The number exists once and every other location points
  at it.

#### B2. Owner language code and CI issue numbers

- Fact: `.github/owners.toml` maps `@tvna` -> `ja` and is the only source;
  `scripts/plan_language_context.py` reads it at SessionStart. Test files restate
  `"ja"` as fixtures, which is acceptable (a test asserting behavior is not a
  second source of truth).
- Fact: `.github/tracking-issues.toml` is the declared single source for every
  issue number CI writes to, with each anchor listing its `consumers`. Comment
  references such as "Refs #178" elsewhere are historical provenance markers, not
  live consumers, so they are not duplicates of the anchor.
- Recommendation: keep both.

#### B3. Module-size budget `800` / `640`

- Fact: the budget is defined once, in `scripts/scan_maintainability_metrics.py`
  (`MAX_MODULE_LINES = 800`; `WARN_MODULE_LINES = int(MAX_MODULE_LINES * 0.8)`
  derives `640`). `scripts/scan_module_size_distribution.py` does NOT redefine
  it: it imports both constants (`from scan_maintainability_metrics import
  MAX_MODULE_LINES, WARN_MODULE_LINES`) and writes the imported values into the
  generated `docs/standards/module-size-distribution.toml` `[budget]` table.
  Both scripts and the snapshot therefore trace back to one source.
- Fact: the standard prose (`docs/standards/maintainability-metrics.md`,
  asserted by `tests/test_scan_maintainability_metrics.py` via
  `"800 physical lines" in standard_text`) restates `800` in text; this is a
  prose copy of the single source, not a second authority.
- Fact: the one residual coupling is `BUCKET_EDGES = (160, 320, 480, 640, 800)`
  in `scan_module_size_distribution.py`. Its top two edges repeat the literals
  `640` / `800` rather than deriving them from the imported constants, so a
  budget change would update the gate and the snapshot automatically but leave
  the histogram edges stale until edited by hand. This is cosmetic (the edges
  are bucket boundaries, not the budget itself) and cannot cause a silent budget
  divergence.
- Recommendation: keep; the budget is correctly single-sourced. Optionally
  derive the top two `BUCKET_EDGES` from `WARN_MODULE_LINES` / `MAX_MODULE_LINES`
  so the histogram tracks the budget without a manual edit. No drift gate is
  warranted for a cosmetic, non-divergent coupling.

Revision note: an earlier draft classified this budget as a Class A "two
independent `800` literals" gap. That was a factual error
(`scan_module_size_distribution.py` imports the constants rather than
re-hardcoding them); corrected after PR #2004 review.

### Class C: duplicate-but-gated (keep)

#### C1. Python version pins

- Fact: the interpreter version appears in `.python-version` (exact patch),
  `pyproject.toml` `requires-python = ">=3.12"`, and mypy `python_version =
  "3.12"`. `.github/workflows/verify-agents.yml` documents and runs a gate that
  keeps `.python-version` from silently drifting from `requires-python`.
- Recommendation: keep. This is the duplicate-but-gate model and needs no change.

### Class D: weak or non-duplicate (judge case by case)

#### D1. Commit-type enumeration (medium)

- Fact: the canonical commit-type list lives in `.github/title-policy.toml`
  (`types = [build, chore, ci, docs, feat, fix, perf, refactor, revert, style,
  test]`), read by `scripts/title_policy.py` and the verify workflows.
- Fact: two other files hold partial projections of the same concept:
  - `.github/label-policy.toml` defines five `type:*` labels: `type:feat`,
    `type:fix`, `type:refactor`, `type:docs`, and `type:tracking` (and denies
    bare `feat` / `fix` as "noisy duplicates"). Note `type:tracking` has no
    counterpart in `title-policy.toml` `types`: it is an intentional label for
    tracking issues (`.github/ISSUE_TEMPLATE/tracking.yml` applies it), not a
    commit type. Any subset check must treat it as an explicit exception.
  - `.github/ISSUE_TEMPLATE/*.yml` provides templates for an overlapping set
    (`chore`, `config`, `docs`, `feat`, `fix`, `generic`, `refactor`,
    `tracking`), which both omits canonical types (`build`, `ci`, `perf`,
    `revert`, `style`, `test`) and adds non-type categories (`config`,
    `generic`, `tracking`).
- Speculation: this is not a strict duplication because each projection is an
  intentional subset for a different purpose (validation vs labeling vs issue
  authoring). The risk is that a new type added to `title-policy.toml` is not
  reflected where it should be (e.g. a missing `type:*` label), with nothing
  catching the omission.
- Recommendation: do NOT merge the files. If tightening is wanted, add a
  consistency check asserting `label-policy.toml`'s `type:*` label stems are a
  subset of `title-policy.toml` `types` PLUS a small allowlist for intentional
  non-commit labels (`tracking`); a drift gate over the relationship, not a
  single source. Without that allowlist the gate would false-positive on today's
  deliberate `type:tracking` label. Otherwise keep as-is; the subsets are
  deliberate.

#### D2. Security floor vs surface inventory (non-duplicate)

- Fact: `.github/security-control-floor.toml` keys facts by control family with
  a drift `tier` (`detect-and-file`, `detect-only`, `pr-gate-only`).
  `.github/security-surface-inventory.toml` keys facts by file path with a
  `status` (`inventory`, `exempt`). They share a referenced source of truth
  (`docs/prd/security-control-inventory.md`, issue #178) but record different
  axes; neither restates the other's values.
- Recommendation: keep separate. Merging would conflate two orthogonal axes and
  has no SSoT benefit. The inventory file already notes its own exempt table is
  a drift surface, so the meta-risk is consciously handled.

#### D3. Hardcoded `docs/...` paths across scripts (low)

- Fact: standard/PRD/graph paths are restated as literals across many scripts
  (for example `docs/graph/doc-dependencies.toml` appears in roughly ten files).
- Speculation: a path literal is a duplicated fact, but co-change of a renamed
  doc with its consumers is partially governed already by the doc dependency
  graph (`docs/graph/doc-dependencies.toml` + `scripts/gate_doc_graph_pr.py`),
  and a path constant per script is idiomatic. The SSoT payoff of centralizing
  path literals is low relative to the churn it would introduce.
- Recommendation: keep as-is; not worth a shared path registry today.

## Summary table

| ID | Fact | Class | Recommendation |
| --- | --- | --- | --- |
| (none) | no Class A true gaps found | A | none |
| B1 | coverage fail_under 95 | B (single-sourced) | keep |
| B2 | owner language, CI issue numbers | B (single-sourced) | keep |
| B3 | module-size budget 800/640 | B (single-sourced via import) | keep; optionally derive histogram edges from the budget constants |
| C1 | Python version pins | C (gated) | keep |
| D1 | commit-type enumeration | D (partial projections) | keep files; optional subset drift gate (must allowlist type:tracking) |
| D2 | security floor vs inventory | D (non-duplicate) | keep separate |
| D3 | hardcoded docs paths | D (low value) | keep as-is |

## Open questions (blocking a yes/no decision)

1. For B3, is the cosmetic histogram-edge coupling worth a tidy (derive the top
   two `BUCKET_EDGES` from the budget constants), or left as-is? Low stakes: the
   budget cannot silently diverge either way.
2. For D1, is the current "intentional subsets, no cross-check" state acceptable,
   or is a `label-policy` subset-of-`title-policy` drift gate wanted? Such a gate
   must allowlist `type:tracking` (intentionally absent from `title-policy.toml`)
   to avoid a false positive. This trades a small standing gate for protection
   against a rare omission.
3. Given no Class A true gap was found, is any remediation desired at all, or
   does this inventory close as "config-file SSoT posture is already
   disciplined", with the two optional tidies (B3 edges, D1 gate) deferred?

## Out of scope

- No code or config is changed by this document.
- No physical consolidation of files with distinct owners or lifecycles; the
  prior analysis on this branch already rejected that direction.
