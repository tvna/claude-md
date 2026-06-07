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
SCHEMA_V2_PATH = REPO_ROOT / "metrics" / "duckdb" / "schema" / "v2" / "schema.sql"
INIT_PATH = REPO_ROOT / "metrics" / "duckdb" / "init.sh"
GITIGNORE_PATH = REPO_ROOT / ".gitignore"
DOC_PATH = REPO_ROOT / "docs" / "standards" / "host-unit-duckdb-metrics.md"


def squashed(text: str) -> str:
    """Return text with Markdown line wrapping normalized for phrase checks."""
    return " ".join(text.split())


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


class TestLogsSchemaV2:
    """OTLP-logs extension contract (Refs #824)."""

    def test_schema_v2_file_exists(self) -> None:
        assert SCHEMA_V2_PATH.is_file(), f"schema v2 must exist at {SCHEMA_V2_PATH}"

    def test_schema_v2_references_issue_824(self) -> None:
        assert "#824" in SCHEMA_V2_PATH.read_text(encoding="utf-8")

    def test_schema_v2_records_migration_version(self) -> None:
        text = SCHEMA_V2_PATH.read_text(encoding="utf-8")
        assert "INSERT INTO schema_meta" in text
        assert "'2'" in text

    def test_schema_v2_contains_session_log_table(self) -> None:
        text = SCHEMA_V2_PATH.read_text(encoding="utf-8")
        assert "CREATE TABLE IF NOT EXISTS session_log" in text

    def test_schema_v2_contains_otlp_log_export_view(self) -> None:
        text = SCHEMA_V2_PATH.read_text(encoding="utf-8")
        assert "CREATE OR REPLACE VIEW otlp_log_record" in text

    def test_schema_v2_contains_logrecord_columns(self) -> None:
        text = SCHEMA_V2_PATH.read_text(encoding="utf-8")
        for column in (
            "event_code",
            "severity_number",
            "severity_text",
            "body",
            "scope_name",
            "scope_version",
            "time_unix_nano",
            "observed_time_unix_nano",
            "resource_attributes",
            "attributes",
        ):
            assert column in text, f"v2 logs table missing column: {column}"

    def test_schema_v2_resource_attributes_is_map(self) -> None:
        text = SCHEMA_V2_PATH.read_text(encoding="utf-8")
        assert "resource_attributes      MAP(VARCHAR, VARCHAR)" in text

    def test_schema_v2_bounds_severity_to_otlp_range(self) -> None:
        text = SCHEMA_V2_PATH.read_text(encoding="utf-8")
        assert "severity_number BETWEEN 1 AND 24" in text

    def test_schema_v2_has_body_redaction_backstop_check(self) -> None:
        text = SCHEMA_V2_PATH.read_text(encoding="utf-8")
        # Coarse last-line guard: reject path separators in body.
        assert "body_has_no_path_separators" in text
        assert "contains(body, '/')" in text

    def test_schema_v2_documents_redaction_field_classes(self) -> None:
        text = SCHEMA_V2_PATH.read_text(encoding="utf-8").lower()
        for field_class in (
            "filesystem path",
            "key location",
            "token",
            "request id",
            "hostname",
            "raw error payload",
        ):
            assert field_class in text, f"redaction contract omits: {field_class}"

    def test_schema_v2_cites_88_and_section_4(self) -> None:
        text = SCHEMA_V2_PATH.read_text(encoding="utf-8")
        assert "#88" in text
        assert "Section 4" in text

    def test_schema_v2_provides_redacted_write_template(self) -> None:
        text = SCHEMA_V2_PATH.read_text(encoding="utf-8")
        assert "INSERT INTO session_log" in text


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

    def test_init_sh_applies_v2_schema(self) -> None:
        text = INIT_PATH.read_text(encoding="utf-8")
        assert "schema/v2/schema.sql" in text

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

    def test_doc_documents_otlp_logs_extension(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8")
        assert "#824" in text
        assert "session_log" in text
        assert "otlp_log_record" in text

    def test_doc_references_schema_v2(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8")
        assert "schema/v2/schema.sql" in text

    def test_doc_redaction_contract_names_field_classes(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        for field_class in (
            "filesystem path",
            "key location",
            "token",
            "request id",
            "hostname",
            "raw error payload",
        ):
            assert field_class in text, f"doc redaction contract omits: {field_class}"

    def test_doc_redaction_cites_88_and_section_4(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8")
        assert "#88" in text
        assert "Section 4" in text

    def test_doc_records_r2_escrow_reentry_decision(self) -> None:
        text = squashed(DOC_PATH.read_text(encoding="utf-8"))
        assert "#1212" in text
        assert "Decision: adopt option (B) as a manual R2 escrow runbook" in text
        assert "temporary handoff layer" in text
        assert "The canonical metrics store remains the per-host DuckDB database" in text

    def test_doc_defines_r2_escrow_artifact_shape(self) -> None:
        text = squashed(DOC_PATH.read_text(encoding="utf-8"))
        assert "redacted OTLP-shaped export bundle" in text
        assert "manifest.json" in text
        assert "metrics.parquet" in text
        assert "logs.parquet" in text
        assert "*.duckdb" in text
        assert "*.duckdb.wal" in text

    def test_doc_defines_r2_escrow_object_and_lifecycle_contract(self) -> None:
        text = squashed(DOC_PATH.read_text(encoding="utf-8"))
        assert "escrow/session/<opaque-session-id>/<bundle-digest>/" in text
        assert "immutable" in text
        assert "24 hours" in text
        assert "delete-after-import" in text

    def test_doc_defines_r2_escrow_credential_issuance(self) -> None:
        text = squashed(DOC_PATH.read_text(encoding="utf-8"))
        for phrase in (
            "Cloudflare dashboard or API",
            "parent token",
            "Workers R2 Storage Write",
            "object-read-write",
            "prefix-scoped",
            "900 seconds",
            "session token",
            "rotate",
        ):
            assert phrase in text

    def test_doc_defines_r2_escrow_retrieval_import_verification(self) -> None:
        text = squashed(DOC_PATH.read_text(encoding="utf-8"))
        for phrase in (
            "durable macOS host",
            "verify the manifest digest",
            "no raw hostnames",
            "no raw repository names",
            "no raw paths",
            "INSERT OR REPLACE INTO change_measurement",
            "session_log",
            "explicitly delete",
        ):
            assert phrase in text

    def test_doc_defines_r2_first_time_provisioning(self) -> None:
        text = squashed(DOC_PATH.read_text(encoding="utf-8"))
        for phrase in (
            "#1326",
            "First-time R2 provisioning",
            "Create or sign in to a Cloudflare account",
            "R2 subscription checkout",
            "payment method",
            "free tier",
            "Create bucket",
            "Account ID",
            "r2.cloudflarestorage.com",
            "operator actions on the durable host",
            "delegated to an ephemeral agent session",
        ):
            assert phrase in text
