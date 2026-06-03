# CI caching evaluation and the no-adopt decision

Tracking issue: #1173. Companion code: `scripts/analyze_ci_timings.py`,
`scripts/ci_budget_issue.py`, `.github/actions/setup-uv/action.yml`,
`.github/workflows/verify-agents.yml`, `.github/workflows/verify-flake.yml`,
`.github/workflows/publish-devcontainer-images.yml`.

This standard records the measurement-based decision **not** to add dependency
caching (`actions/cache`) to CI, and the criteria under which that decision must
be re-measured. It exists so the conclusion is reproducible rather than
re-derived from memory each time the question recurs.

## The question

Would introducing caching to CI reduce CI wall-time? Caching is an intuitive
lever, but on this repository the dominant CI jobs install their toolchain with
`uv`, whose cold setup is already fast. The decision must rest on measured
per-step timings, not intuition.

## Measurement (facts)

Source: GitHub Actions job/step timing API for `verify-agents` run
`26914150924` (the `setup-uv` composite action, no cache). Reproduce with
`scripts/analyze_ci_timings.py` against a freshly fetched `jobs/` set.

- **`Set up uv and project environment` step = ~3s per job.** Observed 2-4s
  across the 11-shard `lint-scripts-pytest` matrix plus `lint-scripts-static`
  and `lint-scripts-pytest-gate`. This single step covers the uv tarball
  download, checksum verification against `flake.nix`, `uv python install`, and
  `uv sync --locked`.
- **`verify-agents` total wall-time = ~54s**, dominated by the *sequential gate
  chain* (`lint-scripts-pytest` matrix -> `lint-scripts-pytest-gate` ->
  `Verify repository scripts / gate` -> `Verify agent instructions / gate`),
  not by toolchain setup.
- **Dependency footprint is tiny:** `uv.lock` has 22 packages; the only runtime
  dependency is `pyyaml`, with pytest / pytest-cov / ruff / mypy / types-PyYAML
  / hypothesis as dev dependencies.

## Per-candidate evaluation

| Candidate | Target | Effect | Frequency | Verdict |
| --- | --- | --- | --- | --- |
| uv cache (`~/.cache/uv` wheels) | `uv sync` | ~0 (deps are tiny) | every job | Reject. Cache restore/save round-trip (~2-5s) exceeds the ~3s setup -> net-negative. |
| uv-managed Python (`uv python install`) | CPython download | small | every job | Reject for now. Folded into the ~3s setup; not separable enough to justify a cache. |
| nix store (magic-nix-cache / FlakeHub) | `verify-flake` `nix build` | large per run | rare (only on `flake.nix` / `flake.lock` changes) | Defer. High per-run cost but low fire rate -> weak ROI. Revisit if flake churn rises. |
| Docker layers | `publish-devcontainer-images` | already optimized | push to main | No action. Already uses `--cache-from` / `--cache-to type=registry,mode=max`. |

## Decision

Do **not** add `actions/cache` to the uv path. At ~3s of measured setup, a cache
would on balance slow CI down, while adding a mutable, potentially poisonable
input that runs counter to the repository's pinning posture (SHA-pinned actions,
`flake.nix` single-source hashes, checksum-verified uv download). The nix store
cache is the only candidate with material per-run savings, but its fire rate is
too low to justify the added surface today.

## Where the wall-time actually is (non-caching levers)

The critical path is structural, not setup-bound. Two levers can affect it, but
both touch `verify-agents`'s job graph -- which is a deliberate design
(marker-bucketed shard matrix plus a completeness gate, #545) wired to required
status-check contexts (`scripts/verify_required_check_contexts.py`,
`.github/rulesets/main.json`). Treat either as its own measured, planned change,
not a quick edit:

- **(a) Sequential gate chain.** `lint-scripts-pytest-gate` and the two
  aggregate gate jobs run after the matrix. Collapsing or parallelizing them
  must preserve every required-check context name.
- **(b) Shard count.** The 11 shards run in parallel; merging them reduces
  per-job setup overhead but serializes test execution, which can *increase*
  wall-time. Any change must be justified by measured overhead-vs-parallelism,
  not assumed.

## Revisit criteria

Re-run `scripts/analyze_ci_timings.py` and reconsider caching when any holds:

- The `Set up uv and project environment` step p50 exceeds ~15s (e.g. the
  dependency set grows materially or `uv` regresses).
- `verify-flake` starts firing on most PRs (flake churn), making a nix store
  cache worthwhile.
- `scripts/ci_budget_issue.py` opens a wall-time budget breach for
  `verify-agents` whose root cause is toolchain setup rather than test volume.
