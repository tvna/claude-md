# Host-Unit DuckDB Metrics Store -- OTel-Compatible Design Contract

This document is the adopted contract for the **first measurement setup** of the
repository's declared purpose (2) -- "measuring the performance impact of those
edits" ([`docs/standards/repo-scope.md`](repo-scope.md)). It is the deliverable
for [#815](https://github.com/tvna/claude-md/issues/815) and supersedes the
orphan-branch JSON approach designed in
[`docs/standards/performance-metrics.md`](performance-metrics.md).

The store is a **per-host DuckDB database** that records the quality-vs-scope
signal per change so the proportionality between quality and scalability
(CLAUDE.md Section 5) can be plotted and observed over time.

## Operator decision and the trade-off it resolves

> Aggregating measurement data across hosts eventually needs an OpenTelemetry-
> style platform. But abandoning early data collection until that platform
> exists is the wrong trade-off. So: start collecting **now**, locally, in
> DuckDB -- and shape the storage to be OpenTelemetry-compatible so that
> cross-host aggregation later is an **export** step, not a re-collection.

Two consequences follow and bound everything below:

1. **Collect early, locally.** One DuckDB file per host, written by an
   operator-local step. No collector, no service, no network dependency is
   required to begin recording.
2. **Stay OTLP-compatible.** The stored shape maps 1:1 onto the OpenTelemetry
   metric data model so a future cross-host step exports the same rows to an
   OTLP collector without re-instrumenting or re-collecting anything.

## SoT layout

| File / path | Target | Purpose |
|---|---|---|
| `docs/standards/host-unit-duckdb-metrics.md` *(this file)* | -- | Adopted contract: trade-off, lifecycle, schema, write path, observation, export |
| [`metrics/duckdb/schema/v1/schema.sql`](../../metrics/duckdb/schema/v1/schema.sql) | host-local `*.duckdb` | Versioned init path: tables, OTLP export view, read-back view, baseline template |
| [`metrics/duckdb/init.sh`](../../metrics/duckdb/init.sh) | operator shell | Environment-aware init helper: detects devcontainer vs. local path, supports `CLAUDE_MD_METRICS_DB` override |
| `*.duckdb` (host-local, git-ignored) | each host | The database itself -- local measurement state, never committed (Refs #88) |

## Storage location and lifecycle

- **One database per host.** The path is operator-local; it is never committed
  and never published. The default path depends on the execution environment
  (see table below); override at any time with the `CLAUDE_MD_METRICS_DB`
  environment variable.

  | Execution environment | Default path |
  |---|---|
  | devcontainer (claude) | `/home/claude/.claude/metrics.duckdb` |
  | devcontainer (codex) | `/home/codex/.codex/metrics.duckdb` |
  | local machine / Codespaces / other persistent host | `$HOME/.local/state/claude-md/metrics.duckdb` |
  | CI runners (GitHub Actions etc.) | — (ephemeral; no write path in v1) |

  The devcontainer paths land inside the named Docker volumes
  (`claude-md-claude-session` and `claude-md-codex-session`) that are already
  declared in `.devcontainer/*/devcontainer.json`; no new volume mount is
  required.  The fallback path uses `$HOME/.local/state/` per the XDG Base
  Directory convention and is appropriate for local machines and GitHub
  Codespaces alike.

- **Init.** Use the environment-aware helper, which auto-detects the correct
  path via the `AGENT_CONTAINER` env var (set by devcontainer) and falls back
  to the XDG path:

  ```sh
  ./metrics/duckdb/init.sh
  # override:
  CLAUDE_MD_METRICS_DB=/custom/path.duckdb ./metrics/duckdb/init.sh
  ```

  The helper calls `duckdb … < metrics/duckdb/schema/v1/schema.sql`, which is
  idempotent (`IF NOT EXISTS` on every object), so re-running is safe.

- **Retention / rotation.** The database is append-mostly and small (one row per
  measured change). No rotation is required for v1; if a host's file is lost it
  is rebuilt by re-recording from `main`'s history. Because it is host-local
  state, losing it costs reproducible work, not irreplaceable data.
- **duckdb is intentionally NOT a repository dependency.** The only runtime
  Python dependency stays `pyyaml`. The schema is plain SQL executed by the
  DuckDB CLI (or any DuckDB binding) that the operator already has. This keeps
  the strict `uv` dependency surface untouched (see *Out of scope*).

## OTLP-compatible schema

The schema separates the three OpenTelemetry layers -- **Resource** (who
produced it), **Scope** (which instrumentation), and the **record** (the
measurement) -- exactly as OTLP does.

- **Storage form (`change_measurement`).** One wide, deterministic-dedup row per
  measured change, keyed by `(commit_sha, spec_version)`. It holds the
  reproducibility keys, the scope signal, the quality signal(s), and a derived
  proportionality. The primary key gives the de-duplication contract:
  re-recording the same change with `INSERT OR REPLACE` updates the row instead
  of double-counting it.
- **Export form (`otlp_metric_data_point`).** A view that unpivots each
  measurement into OTLP **gauge data points** in long format. Its columns line
  up with the OpenTelemetry ClickHouse-exporter / DuckDB OTLP-extension layout
  (`ResourceAttributes`, `ScopeName`, `MetricName`, `MetricUnit`, `Attributes`,
  `TimeUnix`, `Value`). Time is stored as UINT64 nanoseconds since the Unix
  epoch (OTLP `TimeUnixNano`), losslessly; views render it to a timestamp only
  on read.
- **Observation form (`v_proportionality`).** A view that returns one wide row
  per change over time for plotting and human read-back.

### Columns and signals

| Column | Role | Notes |
|---|---|---|
| `commit_sha` | reproducibility key | 40-char SHA on `main` |
| `compiled_source_version` | reproducibility key | Refs #89 human-readable label; NULL until #89 lands |
| `spec_version` | reproducibility key | measurement spec/schema version (`v1`) |
| `harness_version` | reproducibility key | sha/semver of the recording procedure |
| `model_id` | reproducibility key | pins the stochastic metric (model + version suffix) |
| `measured_at_unix_nano` | time | OTLP `TimeUnixNano` |
| `scope_compiled_tokens` | **scope signal** | deterministic; `cl100k_base` token count of compiled `CLAUDE.md`/`AGENTS.md` (Refs #61 metric (a)) |
| `quality_agent_pass_rate` (+ `_min`/`_max`/`_runs`) | **quality signal** | stochastic; median of N>=3 runs plus the observed band (Refs #61 metric (b)) |
| `proportionality` | **proportionality metric** | GENERATED, never hand-entered: `quality_agent_pass_rate` per 1k instruction tokens |
| `resource_attributes` | OTLP Resource | anonymized host identity (see below) |

`proportionality` is a derived (generated) column so the inputs remain the
single source of truth; it reads back identically to a stored value, which
makes wrong (inconsistent) entry impossible by construction.

### Anonymization (Refs #88)

A per-host database is local and not published, so the orphan-branch
anonymization machinery is unnecessary. **But** `resource_attributes`, and any
row ever exported or shared, MUST carry only an opaque `host.id` token and MUST
NOT contain a raw hostname, repository name, path, URL, raw prompt, or raw model
output. The export view passes `resource_attributes` through unchanged, so the
anonymization obligation lives at write time.

## Write path

- **Who writes.** An operator-local step (a script or a one-off `duckdb`
  invocation) on the host that produced the change. There is no CI write path in
  v1 -- CI runners are ephemeral and have no host-local database, and `duckdb`
  is not a repo dependency.
- **When.** Once per measured change against `main`, after the signals are
  computed.
- **De-duplication.** `INSERT OR REPLACE INTO change_measurement (...)` keyed on
  `(commit_sha, spec_version)`. Deterministic signals reproduce byte-identically
  for the same key; stochastic signals are stored as the median plus band, not
  as N separate rows. The baseline template is in the schema file.

## Observation

- **Read back:** `SELECT * FROM v_proportionality;` -- one row per change over
  time, ready to plot quality against scope.
- **Export (later cross-host aggregation):**
  `COPY (SELECT * FROM otlp_metric_data_point) TO 'export.parquet' (FORMAT parquet);`
  The exported rows are OTLP-shaped gauge data points; a downstream step feeds
  them to an OTLP collector that aggregates across hosts. That collector and its
  wiring are **out of scope here** -- the point of this contract is that they
  can be added later without changing how any host collects.

## Reproducibility contract (carried from performance-metrics.md)

- **Deterministic signals** (e.g. `scope_compiled_tokens`): the same
  `commit_sha` + the same tokenizer MUST yield the same integer. Any divergence
  is a bug in the recording procedure.
- **Stochastic signals** (e.g. `quality_agent_pass_rate`): report the median of
  N>=3 runs with `min`/`max` recorded; pin `model_id`, `spec_version`, and
  `harness_version`. A single run is a point estimate, not a baseline.

## Relationship to `performance-metrics.md`

`performance-metrics.md` designed an orphan-branch (`benchmarks`) JSON record
store, with the spec on `main` and immutable results on a long-lived orphan
branch. [#815](https://github.com/tvna/claude-md/issues/815) replaces that
**storage approach** with the per-host DuckDB store defined here. What carries
forward unchanged: the metric set (compiled-token count + agent pass-rate), the
reproducibility contract, and the prohibition on repo-identifying or raw
free-text fields in anything exported. What is dropped: the orphan branch and
the immutable per-run JSON file layout. The earlier orphan-branch benchmark
issues ([#61](https://github.com/tvna/claude-md/issues/61),
[#62](https://github.com/tvna/claude-md/issues/62),
[#88](https://github.com/tvna/claude-md/issues/88),
[#90](https://github.com/tvna/claude-md/issues/90)) are superseded by #815;
their still-valid requirements are carried into the columns above.

## Out of scope (deferred, with re-entry points)

- **Adding `duckdb` as a Python / `uv` dependency.** Deliberately excluded; the
  schema is dependency-free plain SQL. Revisit only if an in-repo automated
  recorder is ever justified.
- **A CI write path or a CI gate over the store.** Excluded for v1 (ephemeral
  runners, no host-local DB). A future phase could add a host-scheduled recorder.
- **The cross-host OTLP collector and its aggregation pipeline.** The export
  view makes this a later, additive step.
- **The OTLP *logs* signal (operational session logs, e.g. commit-signing
  failures).** This store is metrics-only (OTLP gauge data points). Capturing
  redacted operational logs is deferred to
  [#824](https://github.com/tvna/claude-md/issues/824), which must define the
  redaction contract -- drop or hash paths, key locations, tokens, request ids,
  hostnames, and raw payloads -- before any such row is written (Refs #88,
  CLAUDE.md Section 4).
- **The structure-sensitive task signal** (Refs #90/#83): a candidate quality
  input once the schema exists; added additively as a new signal column.
- **`compiled_source_version` population** (Refs #89): the column exists now and
  stays NULL until #89 decides the versioning scheme.

## Verify

CI cannot execute the schema: `duckdb` is intentionally not a repository
dependency, so the init, the baseline `INSERT`, and the read-back are
**operator-local** steps, run on a host that has the DuckDB CLI:

```sh
# 1. Init (idempotent; auto-detects environment via AGENT_CONTAINER)
./metrics/duckdb/init.sh
# prints the resolved path, e.g.: Initialized: /home/claude/.claude/metrics.duckdb

# Override path explicitly:
CLAUDE_MD_METRICS_DB=/custom/path.duckdb ./metrics/duckdb/init.sh

# 2. Capture the baseline row against main (fill the template in the schema file)
#    then read it back (substitute the resolved DB path for $DB):
DB="${CLAUDE_MD_METRICS_DB:-$HOME/.local/state/claude-md/metrics.duckdb}"
duckdb "$DB" -c "SELECT * FROM v_proportionality;"

# 3. Confirm the OTLP export surface is populated:
duckdb "$DB" -c "SELECT MetricName, Value FROM otlp_metric_data_point;"
```

What CI *does* verify deterministically: this document's local links and the
schema file's presence (`scripts/scan_markdown_links.py verify`), and that no
unrelated regression is introduced (`pytest`).

## References

- [#815](https://github.com/tvna/claude-md/issues/815) -- this contract (host-unit DuckDB store).
- [#814](https://github.com/tvna/claude-md/issues/814) -- parent: Section 5 quality-scalability proportionality reframe.
- [#226](https://github.com/tvna/claude-md/issues/226) -- CLAUDE.md / AGENTS.md evolution tracker.
- [#89](https://github.com/tvna/claude-md/issues/89) -- instruction-source versioning (OPEN; provides `compiled_source_version`).
- [#61](https://github.com/tvna/claude-md/issues/61), [#62](https://github.com/tvna/claude-md/issues/62), [#88](https://github.com/tvna/claude-md/issues/88), [#90](https://github.com/tvna/claude-md/issues/90) -- superseded orphan-branch benchmark approach (requirements carried forward).
- [`docs/standards/performance-metrics.md`](performance-metrics.md) -- the superseded storage design.
- [`docs/standards/repo-scope.md`](repo-scope.md) -- declared repo purpose (2).
- OpenTelemetry metric data model and the ClickHouse-exporter / DuckDB OTLP-extension column layout -- the external compatibility target the schema mirrors.
