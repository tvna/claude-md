-- host-unit DuckDB metrics store -- schema v3: tool-overlap measurement (Refs #1618)
--
-- Additive migration on top of schema v1 (Refs #815) and v2 (Refs #824). It
-- adds a table that records, per measurement run, how a newly provisioned
-- single-binary tool (zizmor / lychee / betterleaks, provisioned in #1610)
-- compares against the overlapping bespoke deterministic gate when both scan
-- the SAME scope. It does NOT modify any v1 or v2 object. Apply v1, then v2,
-- then this file; every object uses IF NOT EXISTS / CREATE OR REPLACE, so
-- re-running any of them is safe.
--
-- Apply (operator, local; duckdb is intentionally NOT a repo dependency):
--   ./metrics/duckdb/init.sh     # applies v1, then v2, then v3 in order
--
-- Design contract: docs/standards/tool-overlap-measurement.md
--
-- Why this exists (Refs #1618, follow-up to #1610):
--   #1610 provisioned the three tools ALONGSIDE the existing gates and
--   deferred the output comparison. This table is the structured sink for that
--   comparison: it captures the evidence (per-pair finding counts, the
--   agree / new-tool-only / existing-gate-only diff partition, and each side's
--   wall-clock time) that the keep / replace / drop decision rests on. Nothing
--   is removed during the measurement phase; this only records.
--
-- OTel compatibility: storage stays OTLP-shaped (UINT64 TimeUnixNano stored
-- losslessly, rendered to TIMESTAMP only on read; host.id-only resource
-- attributes) so a later cross-host EXPORT is a step, never a re-collection.
-- A dedicated OTLP gauge export view is deferred until the measurement window
-- closes and the gauge set is settled; v_tool_overlap below is the read-back
-- surface used during the window.
--
-- REDACTION CONTRACT (mandatory, enforced before any row is written):
--   One of the measured tools (betterleaks) is a secret scanner; its raw
--   findings can contain live secret values. Storing those verbatim would
--   violate #88 (no repo names, paths-to-secrets, URLs, raw prompts, or raw
--   model output in any exported row) and CLAUDE.md Section 4 (debug
--   instrumentation is an attack surface; redact credentials, tokens, and PII
--   before logging). Therefore the writer MUST record only:
--     * non-sensitive aggregate counts (findings, the diff partition), and
--     * each side's wall-clock duration.
--   The matched secret VALUE never reaches this table (or the JSON / Markdown
--   artifacts the writer emits): betterleaks is run with --redact=100 and the
--   writer keeps only rule id, repo-relative path, and line number for the
--   per-finding detail it writes to the artifact, never the secret itself.
--
-- Requires DuckDB >= 0.10 (MAP columns).

-- ---------------------------------------------------------------------------
-- Record this migration in the schema version marker created by v1. The '1',
-- '2', and '3' rows coexist: schema_meta is the ledger of applied migrations.
-- ---------------------------------------------------------------------------
INSERT INTO schema_meta (schema_version, applied_at_unix_nano)
SELECT '3', CAST(epoch_ns(now()) AS UBIGINT)
WHERE NOT EXISTS (SELECT 1 FROM schema_meta WHERE schema_version = '3');

-- ---------------------------------------------------------------------------
-- tool_overlap_measurement: one row per (pair, measurement run). The PRIMARY
-- KEY gives deterministic de-duplication: re-recording the same
-- (commit_sha, pair_name, measured_at_unix_nano) replaces the row (use
-- INSERT OR REPLACE) instead of double-counting.
--
-- Pair identity: pair_name is the stable label (workflow-static / markdown-
-- links / secrets); new_tool and existing_gate name the two sides compared.
-- scope_label records WHAT was scanned (for example ".github/workflows" or
-- "DOC_GLOBS markdown") so a reader knows the inputs were identical on both
-- sides without re-deriving them.
--
-- Signals (all non-sensitive; see the REDACTION CONTRACT above):
--   - new_tool_findings / existing_gate_findings: total finding counts.
--   - agree_count / new_tool_only_count / existing_gate_only_count: the diff
--     partition over (repo-relative path, line). agree = both sides flag the
--     same location; *_only = flagged by exactly one side. The CHECK
--     constraints below assert the partition is internally consistent
--     (defense-in-depth, not a substitute for the writer computing it right).
--   - new_tool_duration_ms / existing_gate_duration_ms: each side's wall-clock
--     time, so the cost half of keep/replace/drop is on the record too.
--
-- resource_attributes carries the OTLP Resource for this host. It MUST be
-- anonymized: an opaque host.id token only -- never a raw hostname, repo
-- name, path, URL, raw prompt, or raw model output (Refs #88).
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tool_overlap_measurement (
    pair_name                  VARCHAR  NOT NULL,
    new_tool                   VARCHAR  NOT NULL,
    existing_gate              VARCHAR  NOT NULL,
    commit_sha                 VARCHAR  NOT NULL,
    scope_label                VARCHAR  NOT NULL,
    measured_at_unix_nano      UBIGINT  NOT NULL,             -- OTLP TimeUnixNano
    recorded_at_unix_nano      UBIGINT  NOT NULL,             -- OTLP ObservedTimeUnixNano analog
    new_tool_findings          INTEGER  NOT NULL,
    existing_gate_findings     INTEGER  NOT NULL,
    agree_count                INTEGER  NOT NULL,
    new_tool_only_count        INTEGER  NOT NULL,
    existing_gate_only_count   INTEGER  NOT NULL,
    new_tool_duration_ms       DOUBLE   NOT NULL,
    existing_gate_duration_ms  DOUBLE   NOT NULL,
    resource_attributes        MAP(VARCHAR, VARCHAR) NOT NULL,
    notes                      VARCHAR,
    CONSTRAINT new_tool_partition_consistent
        CHECK (new_tool_findings = agree_count + new_tool_only_count),
    CONSTRAINT existing_gate_partition_consistent
        CHECK (existing_gate_findings = agree_count + existing_gate_only_count),
    CONSTRAINT counts_non_negative
        CHECK (agree_count >= 0 AND new_tool_only_count >= 0
               AND existing_gate_only_count >= 0),
    PRIMARY KEY (commit_sha, pair_name, measured_at_unix_nano)
);

-- ---------------------------------------------------------------------------
-- v_tool_overlap: human read-back / observation surface. One row per measured
-- pair-run, ordered over time, so the keep/replace/drop signal can be scanned:
-- existing_gate_only_count == 0 across the window points at REPLACE; both
-- *_only columns > 0 points at KEEP both; new_tool_only_count == 0 across the
-- window points at DROP the new tool. divergence is the total number of
-- locations the two sides disagree on.
-- ---------------------------------------------------------------------------
CREATE OR REPLACE VIEW v_tool_overlap AS
SELECT
    pair_name,
    new_tool,
    existing_gate,
    scope_label,
    new_tool_findings,
    existing_gate_findings,
    agree_count,
    new_tool_only_count,
    existing_gate_only_count,
    (new_tool_only_count + existing_gate_only_count) AS divergence,
    new_tool_duration_ms,
    existing_gate_duration_ms,
    commit_sha,
    to_timestamp(measured_at_unix_nano / 1e9) AS measured_at_utc
FROM tool_overlap_measurement
ORDER BY measured_at_unix_nano, pair_name;

-- ---------------------------------------------------------------------------
-- Ingest template (Refs #1618). scripts/measure_tool_overlap.py emits a JSON
-- record array whose keys are exactly the INSERT column list below. The
-- operator ingests it locally (CI is ephemeral and out of scope for the
-- host-local store by the #826 decision, so the workflow uploads the JSON as
-- an artifact instead of writing the DB in CI). INSERT OR REPLACE keeps
-- re-runs idempotent (deterministic de-duplication).
--
--   INSERT OR REPLACE INTO tool_overlap_measurement (
--       pair_name, new_tool, existing_gate, commit_sha, scope_label,
--       measured_at_unix_nano, recorded_at_unix_nano,
--       new_tool_findings, existing_gate_findings,
--       agree_count, new_tool_only_count, existing_gate_only_count,
--       new_tool_duration_ms, existing_gate_duration_ms,
--       resource_attributes, notes
--   ) VALUES (
--       'secrets', 'betterleaks', 'scan_secrets.py', '<40-char-sha>',
--       'git ls-files (non-Python tracked)',
--       CAST(epoch_ns(now()) AS UBIGINT), CAST(epoch_ns(now()) AS UBIGINT),
--       <new_findings>, <gate_findings>,
--       <agree>, <new_only>, <gate_only>,
--       <new_ms>, <gate_ms>,
--       MAP {'host.id': '<opaque-anonymized-token>',
--            'service.name': 'claude-md-metrics'},
--       'measurement window cycle N'
--   );
--
-- Read back:
--   SELECT * FROM v_tool_overlap;
