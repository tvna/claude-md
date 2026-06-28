#!/usr/bin/env sh
# metrics/duckdb/init.sh  (Refs #815)
#
# Detect the execution environment and initialise the per-host DuckDB store
# at the appropriate persistent path.  Idempotent: re-running is safe.
#
# Override with an env var:
#   CLAUDE_MD_METRICS_DB=/custom/path.duckdb ./metrics/duckdb/init.sh
#
# Environment detection (priority order):
#   1. CLAUDE_MD_METRICS_DB  -- explicit override (any environment)
#   2. AGENT_CONTAINER=claude -- devcontainer; session volume /home/claude/.claude
#   3. AGENT_CONTAINER=codex  -- devcontainer; session volume /home/codex/.codex
#   4. fallback               -- local machine, Codespaces, or other persistent host
#
# duckdb must be on PATH.  It is intentionally not a repo dependency (Refs #815).

set -eu

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Schema versions are applied in order. Each file is idempotent
# (IF NOT EXISTS / CREATE OR REPLACE), so re-running is safe. v2 adds the
# OTLP-logs extension (Refs #824) on top of v1's metrics tables (Refs #815);
# v3 adds the tool-overlap measurement table (Refs #1618).
SCHEMA_V1="$SCRIPT_DIR/schema/v1/schema.sql"
SCHEMA_V2="$SCRIPT_DIR/schema/v2/schema.sql"
SCHEMA_V3="$SCRIPT_DIR/schema/v3/schema.sql"

if [ -z "${CLAUDE_MD_METRICS_DB:-}" ]; then
    case "${AGENT_CONTAINER:-}" in
        claude) CLAUDE_MD_METRICS_DB="/home/claude/.claude/metrics.duckdb" ;;
        codex)  CLAUDE_MD_METRICS_DB="/home/codex/.codex/metrics.duckdb" ;;
        *)      CLAUDE_MD_METRICS_DB="${HOME}/.local/state/claude-md/metrics.duckdb" ;;
    esac
fi

mkdir -p "$(dirname "$CLAUDE_MD_METRICS_DB")"
duckdb "$CLAUDE_MD_METRICS_DB" < "$SCHEMA_V1"
duckdb "$CLAUDE_MD_METRICS_DB" < "$SCHEMA_V2"
duckdb "$CLAUDE_MD_METRICS_DB" < "$SCHEMA_V3"
printf 'Initialized: %s\n' "$CLAUDE_MD_METRICS_DB"
