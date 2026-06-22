# Performance Metrics -- Phase 2 Design Contract

This document is the design-only contract for measuring the performance impact of edits to the universal `CLAUDE.md` / `AGENTS.md` master source. It addresses purpose (2) declared in [`docs/standards/repo-scope.md`](repo-scope.md) ("measuring the performance impact of those edits") and is the Phase 2 deliverable of the governance plan tracked in [#58](https://github.com/tvna/claude-md/issues/58), opened as [#61](https://github.com/tvna/claude-md/issues/61).

No numbers, no harness code, and no CI wiring land with this document. Phase 3 ([#62](https://github.com/tvna/claude-md/issues/62)) implements the harness and acquires the first baseline by quoting the schema and contracts named below.

## SoT layout

| File / branch | Target | Purpose |
|---|---|---|
| `docs/standards/performance-metrics.md` *(this file)* | -- | Contract: metric set, harness shape, result record schema, branch layout |
| `benchmarks/spec/v<N>/` on `main` | committed alongside the source | Version-pinned benchmark task spec (created by Phase 3, [#62](https://github.com/tvna/claude-md/issues/62)) |
| `benchmarks` orphan branch | `origin/benchmarks` | Long-lived store of immutable result records, keyed by compiled-source SHA |

## Metrics (v1)

Two metrics are in scope for v1. A third candidate (redundancy / section-overlap score) is **deferred to v2** so a future sub-issue has a clean re-entry point and does not silently expand v1 scope.

### (a) Token count of compiled outputs

Token count of `CLAUDE.md` and `AGENTS.md` as produced by `apm compile` (`apm-cli==0.12.1`, invoked via `uv run --with "apm-cli==0.12.1" apm compile`; mirrors `.github/workflows/generate-agents.yml`). Deterministic and cheap.

- **Tokeniser**: pinned to `tiktoken` encoding `cl100k_base`. Pinned because it is offline, deterministic, and version-locked via `uv.lock`. A model-native tokeniser would be more faithful but introduces an external call and a moving target; record this trade-off explicitly so v2 can revisit.
- **Unit**: integer token count, reported per file (both `CLAUDE.md` and `AGENTS.md` even though they are byte-identical today -- they may diverge if `apm.yml` targets change).

### (b) Agent task-completion rate on a fixed benchmark

Pass/fail tally over the version-pinned task spec at `benchmarks/spec/v<N>/`, run with a specific model id against the compiled instructions at a specific source SHA.

- **Unit**: `tasks_passed / tasks_total`, a float in `[0, 1]`.
- **Variance**: this metric is non-deterministic by construction (see *Reproducibility contract* below). A single number is a point estimate; baselines must aggregate ≥3 runs.

## Harness

### Where it runs

A local script invoked via `uv run`, matching the toolchain already pinned for `apm compile`. Rationale: simplest reproducible path; the maintainer can re-run on any Phase-2-or-later SHA without spinning up CI; `uv.lock` already locks the Python environment.

CI integration is **deferred to Phase ≥5** (e.g. a workflow that runs the harness on tagged commits and pushes records to the `benchmarks` branch). Rationale: until Phase 3 produces a few baselines and we know the variance band of metric (b), gating CI on a noisy signal would create false-positive churn.

### What it ingests

- `CLAUDE.md` and `AGENTS.md` checked out at a given commit SHA on `main` (the harness reads them; it does **not** re-run `apm compile`, so the measurement matches what submodule consumers actually receive at that SHA).
- The version-pinned benchmark spec at `benchmarks/spec/v<N>/` from that same SHA.

Reading the committed compiled artifacts -- rather than recompiling -- means metric (a) measures what consumers see, not what the source could re-emit if `apm-cli` versions drifted. The `portable-pr-policy` job in `verify-pr.yml` already guarantees source and compiled artifacts stay in sync on `main`.

### What it emits

One JSON record per run. Initial schema (`schema_version: "1"`); Phase 3 may extend additively, but field names already used here are stable.

```json
{
  "schema_version": "1",
  "compiled_source_sha": "<40-char git SHA on main>",
  "benchmark_spec_version": "v0",
  "harness_version": "<sha or semver of the harness script>",
  "run_timestamp_utc": "<ISO 8601, e.g. 2026-05-20T12:34:56Z>",
  "metric_a": {
    "tokeniser": "tiktoken:cl100k_base",
    "claude_md_tokens": 0,
    "agents_md_tokens": 0
  },
  "metric_b": {
    "model_id": "<exact model id used, including version suffix>",
    "tasks_total": 0,
    "tasks_passed": 0,
    "pass_rate": 0.0,
    "seed": null,
    "temperature": 0.0
  },
  "environment": {
    "python": "<x.y.z>",
    "uv": "<x.y.z>",
    "apm_cli": "0.12.1"
  }
}
```

Phase 3's `docs/performance-baseline.md` quotes these fields by name; renames require a `schema_version` bump and a migration note here.

### Reproducibility contract

- **Metric (a)**: byte-identical reproducibility. Same `compiled_source_sha` + same `tokeniser` MUST yield the same integers. Any divergence is a bug in the harness or the tokeniser pin.
- **Metric (b)**: non-deterministic. The contract is:
  - Report the **median** of N≥3 runs, with `min`/`max` also recorded.
  - Pin `model_id` (including version suffix), `temperature`, and `seed` where the model exposes it.
  - Pin `benchmark_spec_version` (the directory name under `benchmarks/spec/`).
  - Document the observed variance band in `docs/performance-baseline.md` (Phase 3); single-run numbers are point estimates, not baselines.

## Benchmark spec storage (on `main`)

The benchmark task spec lives on `main` under `benchmarks/spec/v<N>/` and is created by Phase 3 ([#62](https://github.com/tvna/claude-md/issues/62)).

Why on `main`, not on the `benchmarks` orphan branch: the spec evolves alongside the source instructions and must be reviewable through the normal PR flow (`docs/standards/repo-scope.md` SoT layout, CODEOWNERS, `apply-rulesets.yml`-protected `main`). Versioning by directory name (e.g. `v0`, `v1`) -- rather than a moving tag -- lets a baseline at SHA *X* unambiguously reference spec `v2`.

Submodule consumer impact: the spec ships in the submodule checkout but is plain text outside `CLAUDE.md` / `AGENTS.md`, so it does not enter the universal instruction surface and does not bias downstream tool behaviour.

## Results storage -- `benchmarks` orphan branch

Result records live on a dedicated long-lived branch named `benchmarks`, created as a **Git orphan** (no shared history with `main`).

### Layout

Phase 3 writes the first entries. Layout:

```
benchmarks branch (orphan)
├── README.md                                       # points back to this doc on main
└── results/
    └── <compiled_source_sha>/
        └── <benchmark_spec_version>/
            └── <run_timestamp_utc>.json            # one record per run
```

### Append-only update procedure

- Each harness run produces a new timestamped JSON file. Records are **immutable**; re-running the same `(compiled_source_sha, benchmark_spec_version)` pair adds a new timestamped file rather than overwriting an existing one.
- Pushes to the `benchmarks` branch are normal commits (no force-push). Once a CI workflow exists (Phase ≥5), the workflow pushes; until then, the maintainer pushes locally.

### Why a dedicated orphan branch

1. **Keeps `main` and submodule consumers clean.** Downstream projects pull this repo as a git submodule to get `CLAUDE.md` / `AGENTS.md`; they should not also pull megabytes of measurement records. An orphan branch isolates the artifact store from the source checkout.
2. **Audit trail.** Each result is a discrete commit on a long-lived branch, never force-pushed. The branch becomes the answer-of-record for "what was the score at SHA *X*?"
3. **Independent governance.** The `benchmarks` branch can have its own ruleset (e.g. allow bot pushes, forbid force-push, no `main` merge gate) without coupling to `main`'s CODEOWNERS / status-check requirements. Concrete ruleset is **out of scope of this PR** (see *Out of scope*).

### One-time bootstrap

The empty orphan branch is created once, out-of-band from PRs to `main`:

```sh
git checkout --orphan benchmarks
git rm -rf --cached .
git clean -fdx
# add a minimal README.md pointing to docs/standards/performance-metrics.md on main
git add README.md
git commit -m "chore(benchmarks): initialise orphan branch for performance result records (#61)"
git push -u origin benchmarks
git checkout main
```

Re-running this on an existing `benchmarks` branch is destructive and must not happen; treat the branch as long-lived from the moment of first push.

## Open Q2 resolution -- downstream submodule consumer effects

From [#58](https://github.com/tvna/claude-md/issues/58) Open Q2, re-surfaced in #61:

> Should the metrics include downstream submodule consumer effects (i.e. how the compiled instructions perform when consumed by another project via git submodule)?

**Excluded for v1.** Rationale:

- This repo's controllable variable is the compiled master source. Downstream consumers add per-project context, tooling, review workflows, and human factors that confound the signal.
- Mixing the two would prevent attribution: a metric regression could be "the master source got worse" or "consumer X added a noisy custom rule", and v1 has no way to tell them apart.
- v2 may revisit once v1 baselines exist and the noise floor of metric (b) is known; the orphan branch layout is forward-compatible (a future `consumers/<project>/` sub-tree could land without renaming anything).

## Out of scope

Explicitly deferred to later phases / sub-issues:

- Acquiring baseline numbers (Phase 3, [#62](https://github.com/tvna/claude-md/issues/62)).
- Implementing the harness script and the `benchmarks/spec/v0/` content (Phase 3, [#62](https://github.com/tvna/claude-md/issues/62)).
- A ruleset / branch protection entry for the `benchmarks` branch (separate sub-issue once Phase 3 lands and the access pattern is concrete).
- Wiring the harness into CI as a gate (Phase ≥5).
- Redundancy / section-overlap scoring as a third metric (v2).
- Downstream submodule consumer measurement (v2; see Open Q2 above).
- Changing the compiled `CLAUDE.md` / `AGENTS.md` content.

## References

- [#61](https://github.com/tvna/claude-md/issues/61) -- this sub-issue (Phase 2 design doc)
- [#58](https://github.com/tvna/claude-md/issues/58) -- parent tracking issue (purpose, prohibition, phase plan)
- [#60](https://github.com/tvna/claude-md/issues/60) -- Phase 1 (scope governance, sibling)
- [#62](https://github.com/tvna/claude-md/issues/62) -- Phase 3 (baseline numbers, depends on this contract)
- [`docs/standards/repo-scope.md`](repo-scope.md) -- declared repo purpose (the source of "(2) measuring the performance impact")
- [`docs/runbooks/rulesets.md`](../runbooks/rulesets.md), [`docs/runbooks/issue-triage.md`](../runbooks/issue-triage.md) -- runbook format precedent
- [`apm.yml`](../../apm.yml) -- `target: [claude, codex]`; defines what `apm compile` produces (input to metric (a))
- [`.github/workflows/generate-agents.yml`](../../.github/workflows/generate-agents.yml) -- toolchain pin (`apm-cli==0.12.1`, `uv`) reused by the harness
