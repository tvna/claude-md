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
| [`metrics/duckdb/schema/v1/schema.sql`](../../metrics/duckdb/schema/v1/schema.sql) | host-local `*.duckdb` | Versioned init path: metrics tables, OTLP gauge export view, read-back view, baseline template |
| [`metrics/duckdb/schema/v2/schema.sql`](../../metrics/duckdb/schema/v2/schema.sql) | host-local `*.duckdb` | Additive migration: OTLP-logs `session_log` table, `otlp_log_record` export view, read-back view, redacted write template (Refs #824) |
| [`metrics/duckdb/init.sh`](../../metrics/duckdb/init.sh) | operator shell | Environment-aware init helper: applies v1 then v2 in order, detects devcontainer vs. local path, supports `CLAUDE_MD_METRICS_DB` override |
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
  | CI runners / Claude agent / web sessions (ephemeral) | -- (out of measurement scope unless the manual R2 escrow path is used; see *Ephemeral-environment measurement boundary*) |

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

  The helper applies the schema versions in order (`schema/v1/schema.sql` then
  `schema/v2/schema.sql`); every object uses `IF NOT EXISTS` / `CREATE OR
  REPLACE`, so re-running is safe.

- **Retention / rotation.** The database is append-mostly and small (one row per
  measured change). No rotation is required for v1; if a host's file is lost it
  is rebuilt by re-recording from `main`'s history. Because it is host-local
  state, losing it costs reproducible work, not irreplaceable data.
- **Ephemeral environments record nothing -- by decision, not by accident.**
  Claude agent / web / CI sessions are explicitly out of measurement scope
  unless they use the manual R2 escrow handoff path; see
  *Ephemeral-environment measurement boundary* below for the recorded decisions
  and the options they resolve (Refs #826, #1212).
- **duckdb is intentionally NOT a repository dependency.** The only runtime
  Python dependency stays `pyyaml`. The schema is plain SQL executed by the
  DuckDB CLI (or any DuckDB binding) that the operator already has. This keeps
  the strict `uv` dependency surface untouched (see *Out of scope*).

## Ephemeral-environment measurement boundary (decision, Refs #826)

The write path above is operator-local by design: one durable DuckDB file per
host, written by an operator-local step, with no CI write path in v1. That
leaves an implicit gap -- measurement produced inside an **ephemeral** Claude
agent / web / CI environment persists nowhere. This section records the
deliberate decision that closes the gap as an explicit, documented boundary
rather than a silent exception to the "collect early, do not abandon early
collection" premise that motivates this contract (Refs #815).

**Facts that bound the decision (measured on the agent container):**

- No `duckdb` runtime is installed (no CLI, no Python module, none in the `uv`
  env), and `duckdb` is intentionally not a repository dependency.
- No `.duckdb` file exists, and the container filesystem is ephemeral: the repo
  is cloned fresh on start and reclaimed on inactivity / session end.
- `*.duckdb` is git-ignored (Refs #88), so a database file is never committed.

An agent / web / CI session therefore cannot contribute a measurement row to any
durable store today: the data would be lost twice over (ephemeral filesystem
plus git-ignore).

**Options considered:**

- **(A) Accept and document the boundary.** Agent / web / CI sessions are
  explicitly out of measurement scope; only durable operator hosts record rows.
  Lowest cost; no new infrastructure; the proportionality signal is openly
  partial.
- (B) Per-session export at session end -- emit OTLP-shaped rows to an external
  sink or OTLP collector before the container is reclaimed. Requires an egress
  destination and must honour the #88 anonymization and #824 redaction
  contracts.
- (C) Commit a redacted, aggregated row to a durable branch or artifact (never
  the raw `*.duckdb`). Requires a reviewed write path.

**Decision for #826: (A) -- accept and document the boundary.** Ephemeral agent
/ web / CI sessions are explicitly **out of measurement scope** by default;
only durable operator hosts record rows. This is consistent with the v1 "no CI
write path" stance (see the lifecycle table and *Out of scope*): the same
ephemerality that excludes CI runners excludes agent / web sessions. The signal
is therefore **openly partial by record** -- changes made in an ephemeral
session are knowingly absent from the store, not silently dropped -- which
removes the silent bias an undocumented boundary would introduce toward changes
made on durable hosts.

**Decision: adopt option (B) as a manual R2 escrow runbook (Refs #1212).** The
default boundary above remains intact for sessions that do not use the escrow.
When an ephemeral session deliberately needs to preserve measurement data, R2
is allowed only as a temporary handoff layer between that session and the
durable macOS host. The canonical metrics store remains the per-host DuckDB
database; R2 is never the canonical store and never a shared live database.
Option (C) remains rejected because committing rows or artifacts would reopen a
reviewed write-path surface that this contract still avoids.

### Manual R2 escrow handoff (Refs #1212)

Use this path only when an ephemeral agent / web / CI session has produced
measurement data that would otherwise be lost before the operator can retrieve
it. It is an operator-run handoff, not an automated recorder and not a new
repository dependency.

**Artifact shape.** Upload one redacted OTLP-shaped export bundle per session or
change. The bundle is a directory or archive containing:

- `manifest.json` -- schema version, opaque session id, producing commit SHA,
  bundle digest, generated-at time, row counts, and artifact file digests.
- `metrics.parquet` -- rows shaped like `otlp_metric_data_point`.
- `logs.parquet` -- optional rows shaped like `otlp_log_record` / `session_log`
  after the #824 redaction contract is applied.

Raw `*.duckdb` and `*.duckdb.wal` files are not valid escrow artifacts. A raw
database upload may contain local state that is outside the export contract, so
the handoff starts from the minimal export bundle and keeps DuckDB itself out of
the repo dependency set.

**R2 object contract.** Store each bundle under an immutable object prefix:
`escrow/session/<opaque-session-id>/<bundle-digest>/`. The session id is not a
hostname, repository name, issue title, URL, path, user name, or raw prompt
fragment. The digest prefix prevents accidental overwrite; a corrected export
uses a new digest prefix rather than mutating the existing object. Configure an
R2 lifecycle rule for the escrow prefix with a 24 hours expiration. Lifecycle is
cleanup defense-in-depth, not correctness: the durable host still uses
delete-after-import behavior and must explicitly delete the object after
successful verification and import.

**Credential issuance.** The parent token lives only with the durable operator,
created in the Cloudflare dashboard or API with the minimum Cloudflare
permission needed to mint scoped R2 credentials and manage the escrow bucket
lifecycle; Cloudflare documents lifecycle management as requiring the `Workers
R2 Storage Write` permission group. The parent token is stored in the
operator's local credential manager, never in the repository, never in an agent
prompt, and never in CI logs. For each handoff, the operator mints a temporary
R2 credential with `object-read-write`, bound to the escrow bucket,
prefix-scoped to `escrow/session/<opaque-session-id>/`, and limited to 900
seconds. The temporary credential includes access key id, secret access key, and
session token; all three are bearer secrets and must be passed only through the
task-specific secure channel. The operator must rotate the parent token on the
operator's normal secret-rotation cadence or immediately after suspected
exposure. Verify the handoff without revealing values by performing a scoped
`PutObject`/`HeadObject` probe against only the session prefix and confirming a
different prefix is denied.

**Retrieval and import.** The durable macOS host downloads the bundle before the
temporary credential expires or mints a separate prefix-scoped read credential
for retrieval. Before import, the host must verify the manifest digest and row
counts, confirm every file digest listed by `manifest.json`, and reject any row
containing raw hostnames, raw repository names, raw paths, URLs, raw prompts,
raw model output, credentials, request ids, or unredacted logs; the accepted
bundle invariant is no raw hostnames, no raw repository names, and no raw
paths. Metrics import
uses the existing idempotent `INSERT OR REPLACE INTO change_measurement`
contract after mapping the OTLP-shaped rows back to the host-unit schema. Log
imports target `session_log` only after the same redaction checks pass. After a
successful import, the operator must explicitly delete the R2 object or prefix;
if that deletion fails, the lifecycle rule remains the backup cleanup path and
the operator records the failed delete as an operational event.

**Sources used for the decision.** Cloudflare R2 documents S3-compatible
temporary credentials with bucket binding, operation permissions, optional
object/prefix scope, session tokens, and TTL up to 604800 seconds; R2 object
lifecycle rules can expire objects by prefix, with deletion typically occurring
within 24 hours of the expiration value. DuckDB documents R2 through its
S3-compatible `httpfs` support and an `R2` secret type, while DuckDB temporary
secrets remain in memory by default and persistent secrets are written to a
local unencrypted secret directory. Those facts make a short-lived export
handoff feasible without adding DuckDB or R2 client libraries to this
repository.

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

## OTLP logs extension (Refs #824)

Schema v2 ([`metrics/duckdb/schema/v2/schema.sql`](../../metrics/duckdb/schema/v2/schema.sql))
adds an OpenTelemetry-**logs**-shaped surface next to the metrics. Where v1
records OTLP **gauge data points** (one measurement per change), v2 records
**redacted operational session events** -- for example a commit-signing
failure -- as OTLP `LogRecord`s. It is an additive migration: it touches no v1
object, records a `'2'` row in `schema_meta`, and is idempotent.

The motivation is concrete. A commit-signing failure observed during the #815
work exposed a host-local filesystem path to a signing key, a signing-server
request identifier, and a raw error payload. Capturing severity-tagged events
next to the metrics makes such anomalies noticeable by intuition (CLAUDE.md
Section 6) without re-collection -- **but only if every host-identifying field
is removed first.**

### Storage form (`session_log`)

One append-only row per event (operational events are distinct occurrences, not
idempotent measurements, so there is no de-duplication key). Columns mirror the
OTLP LogRecord data model:

| Column | OTLP field | Notes |
|---|---|---|
| `event_code` | (classified attribute) | **Required** classified, non-identifying code from a controlled vocabulary (e.g. `commit_signing.failure`). This replaces raw text as the descriptor. |
| `severity_number` | `SeverityNumber` | Integer `1..24` (TRACE=1..FATAL=24), CHECK-bounded |
| `severity_text` | `SeverityText` | e.g. `ERROR` |
| `body` | `Body` | **Redacted** summary only, or NULL -- never a raw payload |
| `scope_name` / `scope_version` | InstrumentationScope | who emitted it |
| `time_unix_nano` | `TimeUnixNano` | when the event occurred |
| `observed_time_unix_nano` | `ObservedTimeUnixNano` | when it was recorded |
| `resource_attributes` | Resource | anonymized `host.id` only (same rule as the metrics table) |
| `attributes` | LogRecord attributes | redacted, non-identifying keys only |

### Export form (`otlp_log_record`) and observation (`v_session_log`)

`otlp_log_record` renames the stored columns to the OpenTelemetry
ClickHouse-exporter / DuckDB OTLP-extension **logs** layout (`Timestamp`,
`ObservedTimestamp`, `SeverityText`, `SeverityNumber`, `ServiceName`, `Body`,
`ResourceAttributes`, `ScopeName`, `ScopeVersion`, `LogAttributes`), so
cross-host aggregation stays an export step. `v_session_log` is the human
read-back view: one row per event over time with timestamps rendered to UTC.

Export (later cross-host aggregation):
`COPY (SELECT * FROM otlp_log_record) TO 'logs.parquet' (FORMAT parquet);`

### Redaction contract (mandatory, before any row is written)

Storing raw operational logs verbatim would violate
[#88](https://github.com/tvna/claude-md/issues/88) (no repo names, paths, URLs,
raw prompts, or raw model output in any exported row) and **CLAUDE.md Section
4** (debug instrumentation is an attack surface; redact credentials, tokens, and
PII before logging). Therefore, **before** the `INSERT`, the writer MUST drop or
hash every one of these field classes:

- **filesystem paths** (e.g. the signing-key path),
- **key locations** (key files, keyring entries, agent socket paths),
- **tokens** (signing tokens, credentials, secrets of any kind),
- **request identifiers** (signing-server request ids, correlation ids),
- **hostnames** (and any raw host identity -- only an opaque `host.id` survives),
- **raw error payloads** (the verbatim error string or server response).

What survives is **only** a severity (`severity_number` + `severity_text`) and a
classified, non-identifying `event_code`. **No raw free text reaches the table.**
The raw signing-server error -- and every operational log like it -- is stored
**only** in this redacted form, citing #88 and CLAUDE.md Section 4.

This contract is enforced primarily at the source (redact before insert). As
defense-in-depth (CLAUDE.md Section 4), the `session_log` table adds a coarse
CHECK that rejects the most unambiguous un-redacted marker -- a path separator
in `body` -- so an un-redacted write **fails loudly** rather than being silently
stored. The CHECK is a backstop, not the contract: it cannot detect a hostname
or a token, so the writer remains responsible for full redaction.

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
  runners, no host-local DB). The ephemeral agent / web / CI measurement
  boundary is now an explicit recorded decision -- option (A), accept and
  document -- not an implicit gap (Refs #826; see *Ephemeral-environment
  measurement boundary*). The #1212 R2 escrow path adopts option (B) only as a
  manual temporary handoff; it does not create a CI write path, a shared remote
  DuckDB database, or an automated recorder. A future phase could still add a
  host-scheduled recorder, or re-open option (C) as a fresh decision.
- **The cross-host OTLP collector and its aggregation pipeline.** The export
  view makes this a later, additive step.
- **The OTLP *logs* signal (operational session logs, e.g. commit-signing
  failures).** Landed in schema v2 (Refs
  [#824](https://github.com/tvna/claude-md/issues/824)); see *OTLP logs
  extension* above. The redaction contract -- drop or hash paths, key locations,
  tokens, request ids, hostnames, and raw payloads before any row is written
  (Refs #88, CLAUDE.md Section 4) -- is defined there. Still deferred: a runtime
  recorder that emits these events automatically (the write path stays
  operator-local, and `duckdb` stays out of the repo dependency set).
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

# 3. Confirm the OTLP export surfaces are populated:
duckdb "$DB" -c "SELECT MetricName, Value FROM otlp_metric_data_point;"
duckdb "$DB" -c "SELECT SeverityText, Body FROM otlp_log_record;"  # redacted logs (v2)
```

What CI *does* verify deterministically: this document's local links and the
schema file's presence (`scripts/scan_markdown_links.py verify`), and that no
unrelated regression is introduced (`pytest`).

## References

- [#815](https://github.com/tvna/claude-md/issues/815) -- this contract (host-unit DuckDB store).
- [#824](https://github.com/tvna/claude-md/issues/824) -- OTLP logs extension (schema v2: redacted operational session logs).
- [#826](https://github.com/tvna/claude-md/issues/826) -- ephemeral-environment measurement boundary (decision: option (A), accept and document).
- [#1212](https://github.com/tvna/claude-md/issues/1212) -- manual Cloudflare R2 escrow handoff for ephemeral measurement export.
- [#814](https://github.com/tvna/claude-md/issues/814) -- parent: Section 5 quality-scalability proportionality reframe.
- [#226](https://github.com/tvna/claude-md/issues/226) -- CLAUDE.md / AGENTS.md evolution tracker.
- [#89](https://github.com/tvna/claude-md/issues/89) -- instruction-source versioning (OPEN; provides `compiled_source_version`).
- [#61](https://github.com/tvna/claude-md/issues/61), [#62](https://github.com/tvna/claude-md/issues/62), [#88](https://github.com/tvna/claude-md/issues/88), [#90](https://github.com/tvna/claude-md/issues/90) -- superseded orphan-branch benchmark approach (requirements carried forward).
- [`docs/standards/performance-metrics.md`](performance-metrics.md) -- the superseded storage design.
- [`docs/standards/repo-scope.md`](repo-scope.md) -- declared repo purpose (2).
- OpenTelemetry metric data model and the ClickHouse-exporter / DuckDB OTLP-extension column layout -- the external compatibility target the schema mirrors.
- Cloudflare R2 temporary credentials, object lifecycle, and S3 compatibility documentation -- the external escrow capability.
- DuckDB S3 API / R2 secret and secrets manager documentation -- the compatibility and secret-storage boundary used for the decision.
