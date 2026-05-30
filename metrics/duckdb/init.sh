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
SCHEMA="$SCRIPT_DIR/schema/v1/schema.sql"

if [ -z "${CLAUDE_MD_METRICS_DB:-}" ]; then
    case "${AGENT_CONTAINER:-}" in
        claude) CLAUDE_MD_METRICS_DB="/home/claude/.claude/metrics.duckdb" ;;
        codex)  CLAUDE_MD_METRICS_DB="/home/codex/.codex/metrics.duckdb" ;;
        *)      CLAUDE_MD_METRICS_DB="${HOME}/.local/state/claude-md/metrics.duckdb" ;;
    esac
fi

mkdir -p "$(dirname "$CLAUDE_MD_METRICS_DB")"
duckdb "$CLAUDE_MD_METRICS_DB" < "$SCHEMA"
printf 'Initialized: %s\n' "$CLAUDE_MD_METRICS_DB"
