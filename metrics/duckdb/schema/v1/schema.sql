-- host-unit DuckDB metrics store -- schema v1 (Refs #815)
--
-- One DuckDB database per host. This file is the init path: it is loaded
-- against a fresh, host-local database and is safe to re-run (every object
-- uses IF NOT EXISTS). The database file itself (*.duckdb) is git-ignored
-- and never committed -- it is local measurement state, not source (Refs #88).
--
-- Init (operator, local; duckdb is intentionally NOT a repo dependency):
--   ./metrics/duckdb/init.sh
--   # or with an explicit path override:
--   CLAUDE_MD_METRICS_DB=/custom/path.duckdb ./metrics/duckdb/init.sh
--
-- Design contract: docs/standards/host-unit-duckdb-metrics.md
--
-- OTel compatibility: storage is kept OTLP-shaped so cross-host aggregation
-- is a later EXPORT step (feed an OTLP collector), never a re-collection.
-- The otlp_metric_data_point view below maps 1:1 onto the OpenTelemetry
-- ClickHouse-exporter / DuckDB OTLP-extension gauge column layout
-- (ResourceAttributes / ScopeName / MetricName / Attributes / TimeUnix /
-- Value). Time is stored as UINT64 nanoseconds since the Unix epoch
-- (OTLP TimeUnixNano), losslessly, and rendered to TIMESTAMP only on read.
--
-- Requires DuckDB >= 0.10 (MAP columns + VIRTUAL generated columns).

-- ---------------------------------------------------------------------------
-- Schema version marker (migration discipline; mirrors
-- docs/standards/performance-metrics.md schema_version contract).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS schema_meta (
    schema_version    VARCHAR  PRIMARY KEY,
    applied_at_unix_nano UBIGINT NOT NULL
);

INSERT INTO schema_meta (schema_version, applied_at_unix_nano)
SELECT '1', CAST(epoch_ns(now()) AS UBIGINT)
WHERE NOT EXISTS (SELECT 1 FROM schema_meta WHERE schema_version = '1');

-- ---------------------------------------------------------------------------
-- change_measurement: one row per measured change, keyed by commit SHA and
-- the measurement spec version. The PRIMARY KEY gives deterministic
-- de-duplication: re-recording the same (commit_sha, spec_version) replaces
-- the row (use INSERT OR REPLACE) instead of double-counting.
--
-- Reproducibility keys: commit_sha, compiled_source_version (Refs #89; NULL
-- until that scheme lands), spec_version, harness_version, model_id.
-- Signals:
--   - scope_compiled_tokens: scope-of-change signal (deterministic, Refs #61
--     metric (a): cl100k_base token count of the compiled CLAUDE.md/AGENTS.md).
--   - quality_agent_pass_rate (+ _min/_max/_runs): quality signal
--     (stochastic, Refs #61 metric (b)); store the median of N>=3 runs with
--     the observed band, per the performance-metrics.md reproducibility
--     contract. NULL until captured.
--   - proportionality: GENERATED (derived, never hand-entered) so the inputs
--     stay the single source of truth -- quality pass-rate per 1k instruction
--     tokens. Reads back identically to a stored column.
--
-- resource_attributes carries the OTLP Resource for this host. It MUST be
-- anonymized: an opaque host.id token only -- never a raw hostname, repo
-- name, path, URL, raw prompt, or raw model output (Refs #88).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS change_measurement (
    commit_sha                VARCHAR  NOT NULL,
    spec_version              VARCHAR  NOT NULL,
    compiled_source_version   VARCHAR,                       -- Refs #89, nullable
    harness_version           VARCHAR  NOT NULL,
    model_id                  VARCHAR,                       -- pins the stochastic metric
    measured_at_unix_nano     UBIGINT  NOT NULL,             -- OTLP TimeUnixNano
    recorded_at_unix_nano     UBIGINT  NOT NULL,             -- OTLP ObservedTimeUnixNano analog
    scope_compiled_tokens     BIGINT,                        -- scope signal
    quality_agent_pass_rate   DOUBLE,                        -- quality signal (median)
    quality_agent_pass_rate_min DOUBLE,
    quality_agent_pass_rate_max DOUBLE,
    quality_agent_runs        INTEGER,
    resource_attributes       MAP(VARCHAR, VARCHAR) NOT NULL,
    notes                     VARCHAR,
    proportionality DOUBLE GENERATED ALWAYS AS (
        quality_agent_pass_rate / NULLIF(scope_compiled_tokens / 1000.0, 0)
    ) VIRTUAL,
    PRIMARY KEY (commit_sha, spec_version)
);

-- ---------------------------------------------------------------------------
-- otlp_metric_data_point: OTLP-compatible EXPORT surface. Unpivots each
-- measurement into long-format gauge data points whose columns line up with
-- the OpenTelemetry ClickHouse-exporter / DuckDB OTLP-extension layout.
-- A later cross-host step exports these rows to an OTLP collector; nothing
-- about the local store has to change for that to happen.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW otlp_metric_data_point AS
WITH points AS (
    SELECT
        'claude_md.scope.compiled_tokens' AS metric_name,
        '{token}'                         AS metric_unit,
        'scope'                           AS measurement_kind,
        CAST(scope_compiled_tokens AS DOUBLE) AS value,
        *
    FROM change_measurement
    UNION ALL
    SELECT
        'claude_md.quality.agent_pass_rate',
        '1',
        'quality',
        quality_agent_pass_rate,
        *
    FROM change_measurement
    UNION ALL
    SELECT
        'claude_md.proportionality',
        '1/k{token}',
        'proportionality',
        proportionality,
        *
    FROM change_measurement
)
SELECT
    resource_attributes                       AS ResourceAttributes,
    'claude-md-metrics'                        AS ScopeName,
    harness_version                            AS ScopeVersion,
    metric_name                                AS MetricName,
    metric_unit                                AS MetricUnit,
    MAP {
        'vcs.revision': commit_sha,
        'claude_md.compiled_source_version': COALESCE(compiled_source_version, ''),
        'claude_md.spec_version': spec_version,
        'claude_md.measurement_kind': measurement_kind,
        'claude_md.model_id': COALESCE(model_id, '')
    }                                          AS Attributes,
    measured_at_unix_nano                      AS TimeUnix,
    measured_at_unix_nano                      AS StartTimeUnix,
    value                                      AS Value
FROM points
WHERE value IS NOT NULL;

-- ---------------------------------------------------------------------------
-- v_proportionality: human read-back / observation surface. One wide row per
-- measured change, ordered over time, so the quality-vs-scope proportionality
-- can be plotted and observed (Refs #815 acceptance: read back and observe).
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_proportionality AS
SELECT
    commit_sha,
    compiled_source_version,
    spec_version,
    scope_compiled_tokens,
    quality_agent_pass_rate,
    quality_agent_pass_rate_min,
    quality_agent_pass_rate_max,
    quality_agent_runs,
    proportionality,
    model_id,
    to_timestamp(measured_at_unix_nano / 1e9) AS measured_at_utc
FROM change_measurement
ORDER BY measured_at_unix_nano;

-- ---------------------------------------------------------------------------
-- Baseline capture template (Refs #62). The operator runs this locally after
-- computing the signals for current main; CI cannot run it because duckdb is
-- deliberately not a repo dependency. Replace the placeholders, then execute.
-- INSERT OR REPLACE keeps re-runs idempotent (deterministic de-duplication).
--
--   INSERT OR REPLACE INTO change_measurement (
--       commit_sha, spec_version, compiled_source_version, harness_version,
--       model_id, measured_at_unix_nano, recorded_at_unix_nano,
--       scope_compiled_tokens, quality_agent_pass_rate,
--       quality_agent_pass_rate_min, quality_agent_pass_rate_max,
--       quality_agent_runs, resource_attributes, notes
--   ) VALUES (
--       '<40-char-main-sha>', 'v1', NULL, '<harness-sha-or-semver>',
--       '<model-id-or-NULL>',
--       CAST(epoch_ns(now()) AS UBIGINT), CAST(epoch_ns(now()) AS UBIGINT),
--       <compiled-token-count>, <median-pass-rate-or-NULL>,
--       <min-or-NULL>, <max-or-NULL>, <runs-or-NULL>,
--       MAP {'host.id': '<opaque-anonymized-token>',
--            'service.name': 'claude-md-metrics'},
--       'initial baseline against main'
--   );
--
-- Read back:
--   SELECT * FROM v_proportionality;
-- Export (OTLP-shaped) for later cross-host aggregation:
--   COPY (SELECT * FROM otlp_metric_data_point) TO 'export.parquet' (FORMAT parquet);
