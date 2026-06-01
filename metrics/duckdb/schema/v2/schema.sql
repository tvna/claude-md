-- host-unit DuckDB metrics store -- schema v2: OTLP logs extension (Refs #824)
--
-- Additive migration on top of schema v1 (Refs #815). It adds an
-- OpenTelemetry-logs-shaped table for *redacted* operational session events
-- (for example commit-signing failures) alongside the existing metrics. It
-- does NOT modify any v1 object. Apply v1 first, then this file; both are
-- idempotent (every object uses IF NOT EXISTS / CREATE OR REPLACE), so
-- re-running either is safe.
--
-- Apply (operator, local; duckdb is intentionally NOT a repo dependency):
--   ./metrics/duckdb/init.sh     # applies v1 then v2 in order
--
-- Design contract: docs/standards/host-unit-duckdb-metrics.md
--   (section "OTLP logs extension (Refs #824)").
--
-- OTel compatibility: storage is kept OTLP-LOGS-shaped so cross-host
-- aggregation is a later EXPORT step (feed an OTLP collector), never a
-- re-collection. The otlp_log_record view below maps 1:1 onto the
-- OpenTelemetry ClickHouse-exporter / DuckDB OTLP-extension logs column
-- layout (Timestamp / ObservedTimestamp / SeverityText / SeverityNumber /
-- ServiceName / Body / ResourceAttributes / ScopeName / ScopeVersion /
-- LogAttributes). Time is stored as UINT64 nanoseconds since the Unix epoch
-- (OTLP TimeUnixNano / ObservedTimeUnixNano), losslessly, and rendered to
-- TIMESTAMP only on read.
--
-- REDACTION CONTRACT (mandatory, enforced before any row is written):
--   Real operational error logs carry sensitive, host-identifying data. A
--   commit-signing failure observed during the #815 work exposed a host-local
--   filesystem path to a signing key, a signing-server request identifier, and
--   a raw error payload. Storing those verbatim would violate #88 (no repo
--   names, paths, URLs, raw prompts, or raw model output in any exported row)
--   and CLAUDE.md Section 4 (debug instrumentation is an attack surface;
--   redact credentials, tokens, and PII before logging).
--   Therefore, before INSERT, the writer MUST drop or hash every one of these
--   field classes -- filesystem paths, key locations, tokens, request
--   identifiers, hostnames, and raw error payloads -- and keep only:
--     * a severity (severity_number + severity_text), and
--     * a classified, non-identifying event_code (controlled vocabulary).
--   No raw free text reaches the table. The body column holds only a redacted
--   summary (or NULL); the CHECK constraints below are a coarse last-line
--   backstop (defense-in-depth), NOT a substitute for redacting at the source.
--
-- Requires DuckDB >= 0.10 (MAP columns).

-- ---------------------------------------------------------------------------
-- Record this migration in the schema version marker created by v1. Both the
-- '1' and '2' rows coexist: schema_meta is the ledger of applied migrations.
-- ---------------------------------------------------------------------------
INSERT INTO schema_meta (schema_version, applied_at_unix_nano)
SELECT '2', CAST(epoch_ns(now()) AS UBIGINT)
WHERE NOT EXISTS (SELECT 1 FROM schema_meta WHERE schema_version = '2');

-- ---------------------------------------------------------------------------
-- session_log: one row per redacted operational session event, OTLP-logs
-- shaped. Append-only (no de-duplication key): operational events are
-- distinct occurrences, not idempotent measurements.
--
-- Columns mirror the OTLP LogRecord data model:
--   event_code              classified, non-identifying event code (controlled
--                           vocabulary, e.g. 'commit_signing.failure'). This is
--                           the ONLY required descriptor; it replaces raw text.
--   severity_number         OTLP SeverityNumber (1..24; TRACE=1..FATAL=24).
--   severity_text           OTLP SeverityText (e.g. 'ERROR').
--   body                    REDACTED summary only, or NULL. Never raw payload.
--   scope_name/scope_version OTLP InstrumentationScope name + version.
--   time_unix_nano          OTLP TimeUnixNano (when the event occurred).
--   observed_time_unix_nano OTLP ObservedTimeUnixNano (when it was recorded).
--   resource_attributes     OTLP Resource. MUST be anonymized: an opaque
--                           host.id token only -- never a raw hostname, repo
--                           name, path, URL, raw prompt, or raw model output
--                           (Refs #88).
--   attributes              OTLP LogRecord attributes. MUST be redacted: no
--                           paths, key locations, tokens, request ids, or
--                           hostnames -- only classified, non-identifying keys.
--
-- The CHECK constraints reject the most unambiguous un-redacted markers in
-- body (path separators) and bound severity_number to the OTLP range. They
-- fail loudly (CLAUDE.md Section 4) so an un-redacted write is caught, not
-- silently stored -- but they are a backstop, not the redaction contract.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS session_log (
    event_code               VARCHAR  NOT NULL,             -- classified, non-identifying
    severity_number          INTEGER  NOT NULL,             -- OTLP SeverityNumber 1..24
    severity_text            VARCHAR  NOT NULL,             -- OTLP SeverityText
    body                     VARCHAR,                       -- REDACTED summary only, or NULL
    scope_name               VARCHAR  NOT NULL,             -- OTLP InstrumentationScope name
    scope_version            VARCHAR,                       -- OTLP InstrumentationScope version
    time_unix_nano           UBIGINT  NOT NULL,             -- OTLP TimeUnixNano
    observed_time_unix_nano  UBIGINT  NOT NULL,             -- OTLP ObservedTimeUnixNano
    resource_attributes      MAP(VARCHAR, VARCHAR) NOT NULL,-- anonymized host.id only
    attributes               MAP(VARCHAR, VARCHAR),         -- redacted, non-identifying keys
    CONSTRAINT severity_number_in_otlp_range
        CHECK (severity_number BETWEEN 1 AND 24),
    CONSTRAINT body_has_no_path_separators
        CHECK (body IS NULL OR (NOT contains(body, '/') AND NOT contains(body, chr(92))))
);

-- ---------------------------------------------------------------------------
-- otlp_log_record: OTLP-compatible EXPORT surface. Renames the stored columns
-- to the OpenTelemetry ClickHouse-exporter / DuckDB OTLP-extension logs layout
-- so a later cross-host step exports these rows to an OTLP collector with no
-- change to the local store. The redacted body and event_code pass through
-- unchanged -- the anonymization obligation lives at write time.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW otlp_log_record AS
SELECT
    time_unix_nano                                AS Timestamp,
    observed_time_unix_nano                       AS ObservedTimestamp,
    severity_text                                 AS SeverityText,
    severity_number                               AS SeverityNumber,
    COALESCE(resource_attributes['service.name'], 'claude-md-metrics') AS ServiceName,
    body                                          AS Body,
    resource_attributes                           AS ResourceAttributes,
    scope_name                                    AS ScopeName,
    scope_version                                 AS ScopeVersion,
    map_concat(
        MAP { 'claude_md.event_code': event_code },
        COALESCE(attributes, MAP {})
    )                                             AS LogAttributes
FROM session_log;

-- ---------------------------------------------------------------------------
-- v_session_log: human read-back / observation surface. One row per event,
-- ordered over time, with timestamps rendered to UTC so severity-tagged
-- anomalies are noticeable by intuition (CLAUDE.md Section 6) without
-- re-collection. Carries no raw text -- only the redacted body and event_code.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_session_log AS
SELECT
    event_code,
    severity_number,
    severity_text,
    body,
    scope_name,
    scope_version,
    to_timestamp(time_unix_nano / 1e9)            AS occurred_at_utc,
    to_timestamp(observed_time_unix_nano / 1e9)   AS observed_at_utc
FROM session_log
ORDER BY time_unix_nano;

-- ---------------------------------------------------------------------------
-- Redacted write template (Refs #824, #88). The operator runs this locally
-- AFTER redacting at the source: every path, key location, token, request id,
-- hostname, and raw payload has already been dropped or hashed, leaving only a
-- severity and a classified event_code. The raw signing-server error and
-- similar operational logs are stored ONLY in this redacted form.
--
--   INSERT INTO session_log (
--       event_code, severity_number, severity_text, body,
--       scope_name, scope_version,
--       time_unix_nano, observed_time_unix_nano,
--       resource_attributes, attributes
--   ) VALUES (
--       'commit_signing.failure',        -- classified, non-identifying code
--       17, 'ERROR',                     -- OTLP SeverityNumber/Text
--       'signing key unavailable',       -- REDACTED summary (no path/id/token)
--       'claude-md-metrics', '<harness-sha-or-semver>',
--       CAST(epoch_ns(now()) AS UBIGINT), CAST(epoch_ns(now()) AS UBIGINT),
--       MAP {'host.id': '<opaque-anonymized-token>',
--            'service.name': 'claude-md-metrics'},
--       MAP {'claude_md.signing_backend': 'ssh'}  -- redacted, non-identifying
--   );
--
-- Read back:
--   SELECT * FROM v_session_log;
-- Export (OTLP-logs-shaped) for later cross-host aggregation:
--   COPY (SELECT * FROM otlp_log_record) TO 'logs.parquet' (FORMAT parquet);
