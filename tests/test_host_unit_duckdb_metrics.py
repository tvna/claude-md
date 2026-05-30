"""Static-contract tests for the host-unit DuckDB metrics infrastructure.

Verifies that ``metrics/duckdb/schema/v1/schema.sql`` and
``metrics/duckdb/init.sh`` are present, structurally sound, and
consistent with the contract in
``docs/standards/host-unit-duckdb-metrics.md``.

DuckDB is intentionally not a repository dependency (Refs #815), so these
tests validate file structure and SQL/shell text rather than executing the
schema.  The acceptance-criteria items that require DuckDB execution
(init, baseline INSERT, read-back) are operator-local steps documented in
the schema file itself and in the design contract.

Refs #815.
"""

from __future__ import annotations

import stat
from pathlib import Path

import pytest

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parents[1]
SCHEMA_PATH = REPO_ROOT / "metrics" / "duckdb" / "schema" / "v1" / "schema.sql"
INIT_PATH = REPO_ROOT / "metrics" / "duckdb" / "init.sh"
GITIGNORE_PATH = REPO_ROOT / ".gitignore"
DOC_PATH = REPO_ROOT / "docs" / "standards" / "host-unit-duckdb-metrics.md"


class TestSchemaFile:
    def test_schema_file_exists(self) -> None:
        assert SCHEMA_PATH.is_file(), f"schema.sql must exist at {SCHEMA_PATH}"

    def test_schema_contains_change_measurement_table(self) -> None:
        text = SCHEMA_PATH.read_text(encoding="utf-8")
        assert "CREATE TABLE IF NOT EXISTS change_measurement" in text

    def test_schema_contains_schema_meta_table(self) -> None:
        text = SCHEMA_PATH.read_text(encoding="utf-8")
        assert "CREATE TABLE IF NOT EXISTS schema_meta" in text

    def test_schema_contains_otlp_export_view(self) -> None:
        text = SCHEMA_PATH.read_text(encoding="utf-8")
        assert "CREATE OR REPLACE VIEW otlp_metric_data_point" in text

    def test_schema_contains_proportionality_view(self) -> None:
        text = SCHEMA_PATH.read_text(encoding="utf-8")
        assert "CREATE OR REPLACE VIEW v_proportionality" in text

    def test_schema_has_scope_signal_column(self) -> None:
        text = SCHEMA_PATH.read_text(encoding="utf-8")
        assert "scope_compiled_tokens" in text

    def test_schema_has_quality_signal_columns(self) -> None:
        text = SCHEMA_PATH.read_text(encoding="utf-8")
        assert "quality_agent_pass_rate" in text
        assert "quality_agent_pass_rate_min" in text
        assert "quality_agent_pass_rate_max" in text
        assert "quality_agent_runs" in text

    def test_proportionality_is_virtual_generated_column(self) -> None:
        text = SCHEMA_PATH.read_text(encoding="utf-8")
        assert "GENERATED ALWAYS AS" in text
        assert "VIRTUAL" in text

    def test_schema_has_otlp_time_column(self) -> None:
        text = SCHEMA_PATH.read_text(encoding="utf-8")
        assert "measured_at_unix_nano" in text

    def test_schema_has_anonymized_resource_attributes(self) -> None:
        text = SCHEMA_PATH.read_text(encoding="utf-8")
        assert "resource_attributes" in text
        assert "host.id" in text

    def test_primary_key_deduplicates_on_sha_and_spec(self) -> None:
        text = SCHEMA_PATH.read_text(encoding="utf-8")
        assert "PRIMARY KEY (commit_sha, spec_version)" in text

    def test_schema_provides_insert_or_replace_dedup_contract(self) -> None:
        text = SCHEMA_PATH.read_text(encoding="utf-8")
        assert "INSERT OR REPLACE" in text

    def test_schema_contains_baseline_insert_template(self) -> None:
        text = SCHEMA_PATH.read_text(encoding="utf-8")
        assert "initial baseline" in text.lower()

    def test_schema_references_issue_815(self) -> None:
        text = SCHEMA_PATH.read_text(encoding="utf-8")
        assert "#815" in text

    def test_schema_documents_duckdb_not_a_repo_dependency(self) -> None:
        text = SCHEMA_PATH.read_text(encoding="utf-8")
        assert "not a repo dependency" in text.lower()


class TestInitHelper:
    def test_init_sh_exists(self) -> None:
        assert INIT_PATH.is_file(), f"init.sh must exist at {INIT_PATH}"

    def test_init_sh_is_executable(self) -> None:
        mode = INIT_PATH.stat().st_mode
        assert mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH), (
            f"{INIT_PATH} must be executable"
        )

    def test_init_sh_references_schema(self) -> None:
        text = INIT_PATH.read_text(encoding="utf-8")
        assert "schema/v1/schema.sql" in text

    def test_init_sh_detects_claude_container(self) -> None:
        text = INIT_PATH.read_text(encoding="utf-8")
        assert "claude" in text
        assert "AGENT_CONTAINER" in text

    def test_init_sh_detects_codex_container(self) -> None:
        text = INIT_PATH.read_text(encoding="utf-8")
        assert "codex" in text

    def test_init_sh_supports_env_var_override(self) -> None:
        text = INIT_PATH.read_text(encoding="utf-8")
        assert "CLAUDE_MD_METRICS_DB" in text

    def test_init_sh_creates_parent_directory(self) -> None:
        text = INIT_PATH.read_text(encoding="utf-8")
        assert "mkdir -p" in text

    def test_init_sh_exits_on_error(self) -> None:
        text = INIT_PATH.read_text(encoding="utf-8")
        assert "set -e" in text


class TestGitignore:
    def test_gitignore_excludes_duckdb_files(self) -> None:
        text = GITIGNORE_PATH.read_text(encoding="utf-8")
        assert "*.duckdb" in text

    def test_gitignore_excludes_duckdb_wal_files(self) -> None:
        text = GITIGNORE_PATH.read_text(encoding="utf-8")
        assert "*.duckdb.wal" in text


class TestDesignDoc:
    def test_doc_file_exists(self) -> None:
        assert DOC_PATH.is_file(), f"design contract must exist at {DOC_PATH}"

    def test_doc_references_schema_sql(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8")
        assert "schema/v1/schema.sql" in text

    def test_doc_references_init_sh(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8")
        assert "init.sh" in text

    def test_doc_names_issue_815(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8")
        assert "#815" in text

    def test_doc_documents_anonymization_constraint(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8")
        assert "host.id" in text
        # "MUST NOT" may be line-wrapped; check prohibition by keyword
        assert "raw hostname" in text
