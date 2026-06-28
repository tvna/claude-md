# Documentation Quality Standard

This document records the deterministic documentation checks for
contributor-facing standards and runbooks. It is the issue #202 standard
for deciding which documentation quality signals belong in CI and which
signals remain review guidance until they can be made deterministic.

## Scope

The blocking gates cover Markdown files that define the repository's
contributor-facing contract and the docs inventory that operators use
to find those files:

- Top-level `*.md` files.
- `.github/*.md` templates.
- `docs/INDEX.md`, compatibility pointers such as
  `docs/agent-provenance.md`, and lane README files.
- `docs/standards/**/*.md`.
- `docs/runbooks/**/*.md`.

The first pass intentionally excludes `docs/prd/` except
`docs/prd/README.md`, plus `docs/archive/` and `docs/generated/`. Those
lanes contain design records, frozen history, and generated views; they
can be added after their existing link debt is repaired in focused PRs.

## D1. Local Markdown Link Gate

`scripts/scan_markdown_links.py verify` is the blocking gate. It checks
repository-local Markdown links without network access:

- Relative file links must resolve inside the repository.
- Same-file and cross-file Markdown heading fragments must resolve to a
  GitHub-style heading anchor.
- GitHub line fragments such as `#L12` and `#L12-L20` are allowed when
  the target file exists.
- HTTP(S), `mailto:`, `tel:`, `data:`, and intentional PR-template
  placeholders are skipped.

The gate runs in `.github/workflows/verify-agents.yml` and in
`scripts/preflight_all.py`, so local preflight and PR CI share the same
definition of broken documentation links.

## D2. Docs Inventory And Lane Gate

`scripts/scan_docs_inventory.py verify` is the blocking gate for docs
tree shape. It treats `docs/INDEX.md` as the operator-facing inventory
and fails when:

- a `docs/**/*.md` file is absent from `docs/INDEX.md`,
- a top-level `docs/*.md` file is neither `docs/INDEX.md` nor an
  explicit compatibility pointer, or
- a new top-level document is added to preserve a historical target path
  without documenting that compatibility reason in code review.

The gate intentionally checks placement rather than prose style. It
prevents history-shaped files from accumulating at `docs/` root, while
leaving each lane's README responsible for explaining where a document
belongs.

## D3. Docs Inventory Navigation Budget

`scripts/scan_docs_inventory.py verify` also enforces a byte budget on
`docs/INDEX.md` (`MAX_INDEX_BYTES`, 40 KiB). INDEX is read on demand
whenever an agent navigates `docs/`; it is not part of the per-request
prefix; so its byte weight is a per-navigation read cost. The budget
blocks runaway growth rather than discovering it after the fact, and
forces the split decision at a documented threshold instead of leaving it
to agent memory.

Bytes, not lines, are the signal: a few verbose `Territory`/`Companion`
rows cost more to read than many terse ones, so the byte count is the
faithful proxy for navigation cost.

The remediation when the budget trips is a per-lane split, **not** a
budget bump: keep a small top-level INDEX (lane descriptions plus the
first row per lane) and move each lane's full table into its lane README.
That split also requires teaching the inventory gate to follow links
transitively (INDEX -> lane README -> leaf docs), because today
`collect_index_entries` reads links from `docs/INDEX.md` directly only.

The working-tree budget is not the only read cost that can trip: two
independent docs PRs can each stay under budget while their additive merge
result crosses it, so the overflow surfaces only at merge-time CI (the PR
#2007 class). `scripts/preflight_merge_index_budget.py` closes that blind
spot by measuring `docs/INDEX.md` in the test-merge of HEAD with the freshly
fetched live base (`git merge-tree --write-tree`, no working-tree mutation)
during branch preflight. It imports `MAX_INDEX_BYTES` from
`scan_docs_inventory` so the budget stays single-sourced; the remediation it
names is still the per-lane split, never a bump. The decision record is
[`docs/adr/0002-index-merge-budget.md`](../adr/0002-index-merge-budget.md).

## Deferred Checks

These checks were evaluated for issue #202 but are not blocking yet:

- External links: deferred because live URL fetching adds network
  flakiness and rate-limit failures to PR verification. A future check
  should use a scheduled job or a cached allowlist.
- Required headings: deferred because standards, runbooks, PRDs, and
  archive documents intentionally use different shapes. A future gate
  should start with new or changed files in one lane.
- Stale issue references: deferred because offline existence checks
  require a local issue snapshot, while live GitHub checks would need
  authenticated API access in every PR.
- Command examples: deferred because shell blocks mix runnable commands,
  snippets, and illustrative fragments. A useful gate needs explicit
  metadata before it can distinguish those cases safely.

## Verification

For documentation-only changes, run:

```sh
python3 scripts/scan_markdown_links.py verify
python3 scripts/scan_docs_inventory.py verify
```

For full local parity with PR gates, run:

```sh
python3 scripts/preflight_all.py
```
