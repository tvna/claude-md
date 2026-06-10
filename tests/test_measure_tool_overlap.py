"""Tests for scripts/measure_tool_overlap.py and the v3 metrics schema (#1618).

Two layers, matching the repo conventions:

* Static-contract tests (like test_host_unit_duckdb_metrics.py): the v3 schema
  file, init.sh wiring, and the standards doc are present and structurally
  sound. duckdb is intentionally not a repo dependency, so these assert on file
  text rather than executing SQL.
* Functional tests of the collector's pure functions and thin-IO adapters,
  with the external binaries replaced by injected callables / monkeypatched
  ``_run`` -- the binaries are web-session only and absent on the coverage
  runner.

The redaction test is deliberately adversarial: it feeds a betterleaks fixture
whose ``Match``/``Secret`` carry a (fake) secret VALUE and proves the value
never reaches a Finding, a record, or the rendered Markdown -- i.e. the
redaction boundary lives in our parser, not only in the ``--redact`` flag.
"""

from __future__ import annotations

import json
import stat
import subprocess
from pathlib import Path

import measure_tool_overlap as mto
import pytest

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA_V3 = REPO_ROOT / "metrics" / "duckdb" / "schema" / "v3" / "schema.sql"
INIT_PATH = REPO_ROOT / "metrics" / "duckdb" / "init.sh"
DOC_PATH = REPO_ROOT / "docs" / "standards" / "tool-overlap-measurement.md"

# A fake, non-real secret value used only to prove our parser drops it. It is
# not a live credential; it exists so the redaction assertion has a needle.
_FAKE_SECRET = "ghp_FAKE0000000000000000000000000000fake"


# ---------------------------------------------------------------------------
# Static contract: v3 schema
# ---------------------------------------------------------------------------
class TestSchemaV3:
    def test_schema_file_exists(self) -> None:
        assert SCHEMA_V3.is_file(), f"v3 schema must exist at {SCHEMA_V3}"

    def test_records_migration_version(self) -> None:
        text = SCHEMA_V3.read_text(encoding="utf-8")
        assert "INSERT INTO schema_meta" in text
        assert "'3'" in text

    def test_references_issue(self) -> None:
        assert "#1618" in SCHEMA_V3.read_text(encoding="utf-8")

    def test_contains_measurement_table(self) -> None:
        text = SCHEMA_V3.read_text(encoding="utf-8")
        assert "CREATE TABLE IF NOT EXISTS tool_overlap_measurement" in text

    def test_table_columns_match_record_columns(self) -> None:
        text = SCHEMA_V3.read_text(encoding="utf-8")
        for column in mto.RECORD_COLUMNS:
            assert column in text, f"v3 table missing column referenced by code: {column}"

    def test_partition_check_constraints(self) -> None:
        text = SCHEMA_V3.read_text(encoding="utf-8")
        assert "new_tool_findings = agree_count + new_tool_only_count" in text
        assert "existing_gate_findings = agree_count + existing_gate_only_count" in text

    def test_resource_attributes_is_anonymized_map(self) -> None:
        text = SCHEMA_V3.read_text(encoding="utf-8")
        assert "resource_attributes        MAP(VARCHAR, VARCHAR)" in text
        assert "host.id" in text

    def test_documents_redaction_contract(self) -> None:
        text = SCHEMA_V3.read_text(encoding="utf-8").lower()
        assert "redaction contract" in text
        assert "--redact=100" in text
        assert "never" in text

    def test_has_readback_view(self) -> None:
        text = SCHEMA_V3.read_text(encoding="utf-8")
        assert "CREATE OR REPLACE VIEW v_tool_overlap" in text


class TestInitWiring:
    def test_init_applies_v3(self) -> None:
        text = INIT_PATH.read_text(encoding="utf-8")
        assert "schema/v3/schema.sql" in text

    def test_init_is_executable(self) -> None:
        mode = INIT_PATH.stat().st_mode
        assert mode & stat.S_IXUSR


class TestStandardsDoc:
    def test_doc_exists(self) -> None:
        assert DOC_PATH.is_file(), f"standards doc must exist at {DOC_PATH}"

    def test_doc_references_issues(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8")
        assert "#1618" in text
        assert "#1610" in text

    def test_doc_states_decision_criteria(self) -> None:
        text = DOC_PATH.read_text(encoding="utf-8").lower()
        for keyword in ("replace", "keep", "drop", "stopping", "window"):
            assert keyword in text, f"decision-criteria doc missing: {keyword}"


# ---------------------------------------------------------------------------
# Pure parsers
# ---------------------------------------------------------------------------
class TestParsers:
    def test_parse_zizmor_converts_row_to_one_based(self) -> None:
        payload = json.dumps(
            [
                {
                    "ident": "template-injection",
                    "locations": [
                        {
                            "symbolic": {"key": {"Local": {"given_path": ".github/workflows/x.yml"}}},
                            "concrete": {"location": {"start_point": {"row": 32}}},
                        }
                    ],
                }
            ]
        )
        findings = mto.parse_zizmor(payload)
        assert findings == [
            mto.Finding(rule_id="template-injection", path=".github/workflows/x.yml", line=33)
        ]

    def test_parse_zizmor_skips_non_local_locations(self) -> None:
        payload = json.dumps(
            [{"ident": "r", "locations": [{"symbolic": {"key": {}}, "concrete": {}}]}]
        )
        assert mto.parse_zizmor(payload) == []

    def test_parse_zizmor_empty(self) -> None:
        assert mto.parse_zizmor("") == []
        assert mto.parse_zizmor("[]") == []

    def test_parse_lychee_reads_error_map(self) -> None:
        payload = json.dumps(
            {"error_map": {"README.md": [{"url": "u", "span": {"line": 7}}]}}
        )
        assert mto.parse_lychee(payload) == [
            mto.Finding(rule_id="broken-link", path="README.md", line=7)
        ]

    def test_parse_lychee_empty(self) -> None:
        assert mto.parse_lychee("") == []
        assert mto.parse_lychee("{}") == []

    def test_parse_betterleaks_handles_null(self) -> None:
        assert mto.parse_betterleaks("null", REPO_ROOT) == []
        assert mto.parse_betterleaks("", REPO_ROOT) == []

    def test_parse_betterleaks_keeps_only_rule_path_line(self, tmp_path: Path) -> None:
        target = tmp_path / "leak.txt"
        payload = json.dumps(
            [
                {
                    "RuleID": "github-pat",
                    "File": str(target),
                    "StartLine": 3,
                    "Match": _FAKE_SECRET,
                    "Secret": _FAKE_SECRET,
                }
            ]
        )
        findings = mto.parse_betterleaks(payload, tmp_path)
        assert findings == [mto.Finding(rule_id="github-pat", path="leak.txt", line=3)]
        # The Finding dataclass has no field that could carry the value.
        assert _FAKE_SECRET not in repr(findings)

    def test_relativize_outside_root_keeps_path(self) -> None:
        assert mto._relativize("/etc/hosts", REPO_ROOT) == "/etc/hosts"


# ---------------------------------------------------------------------------
# Diff + record assembly
# ---------------------------------------------------------------------------
class TestDiffAndRecord:
    def test_diff_partition(self) -> None:
        new = [mto.Finding("a", "f.md", 1), mto.Finding("a", "g.md", 2)]
        gate = [mto.Finding("b", "f.md", 1), mto.Finding("b", "h.md", 3)]
        agree, new_only, gate_only = mto.diff_findings(new, gate)
        assert agree == {("f.md", 1)}
        assert new_only == {("g.md", 2)}
        assert gate_only == {("h.md", 3)}

    def test_build_record_columns_exact(self) -> None:
        record = mto.build_record(
            pair_name="p",
            new_tool="nt",
            existing_gate="eg",
            scope_label="s",
            commit_sha="sha",
            host_id="h",
            new_findings=[mto.Finding("a", "f", 1), mto.Finding("a", "g", 2)],
            gate_findings=[mto.Finding("b", "f", 1)],
            new_duration_ms=1.2345,
            gate_duration_ms=2.0,
            measured_at_unix_nano=10,
            recorded_at_unix_nano=10,
            notes="n",
        )
        assert tuple(record.keys()) == mto.RECORD_COLUMNS
        # Partition invariant the schema CHECK also enforces, asserted via exact
        # literals so the components and the totals line up:
        #   new_tool_findings == agree + new_tool_only  (2 == 1 + 1)
        #   existing_gate_findings == agree + existing_gate_only  (1 == 1 + 0)
        assert record["agree_count"] == 1
        assert record["new_tool_only_count"] == 1
        assert record["existing_gate_only_count"] == 0
        assert record["new_tool_findings"] == 2
        assert record["existing_gate_findings"] == 1
        assert record["resource_attributes"] == {
            "host.id": "h",
            "service.name": "claude-md-metrics",
        }
        assert record["new_tool_duration_ms"] == 1.234

    def test_record_is_json_serializable(self) -> None:
        record = mto.build_record(
            pair_name="p", new_tool="nt", existing_gate="eg", scope_label="s",
            commit_sha="sha", host_id="h", new_findings=[], gate_findings=[],
            new_duration_ms=0.0, gate_duration_ms=0.0,
            measured_at_unix_nano=1, recorded_at_unix_nano=1, notes="",
        )
        json.dumps(record)  # must not raise


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
class TestRendering:
    def test_render_markdown_table(self) -> None:
        record = mto.build_record(
            pair_name="secrets", new_tool="betterleaks", existing_gate="scan_secrets.py",
            scope_label="s", commit_sha="sha", host_id="h",
            new_findings=[mto.Finding("github-pat", "f.py", 1)], gate_findings=[],
            new_duration_ms=1.0, gate_duration_ms=2.0,
            measured_at_unix_nano=1, recorded_at_unix_nano=1, notes="",
        )
        md = mto.render_markdown([record], "Title")
        assert "## Title" in md
        assert "| secrets | betterleaks |" in md
        assert "REPLACE" in md  # decision-rule guidance is in the report

    def test_render_detail_lists_locations_without_values(self) -> None:
        new = [mto.Finding("github-pat", "f.py", 9)]
        _agree, new_only, gate_only = mto.diff_findings(new, [])
        detail = mto.render_detail("secrets", new_only, gate_only, new, [])
        assert "f.py:9 (github-pat)" in detail
        assert "existing-gate-only (0)" in detail

    def test_render_detail_caps_listing(self) -> None:
        new = [mto.Finding("r", f"f{i}.md", i) for i in range(mto._MAX_LISTED + 5)]
        _a, new_only, gate_only = mto.diff_findings(new, [])
        detail = mto.render_detail("p", new_only, gate_only, new, [])
        assert "and 5 more" in detail


# ---------------------------------------------------------------------------
# Gate adapters (in-process; no external binary)
# ---------------------------------------------------------------------------
class TestGateAdapters:
    def test_secrets_gate_finds_planted_fake_secret_path_only(self, tmp_path: Path) -> None:
        # scan_secrets discovers files via git ls-files, so init a tmp git repo.
        subprocess.run(["git", "-C", str(tmp_path), "init", "-q"], check=True)
        leak = tmp_path / "config.env"
        leak.write_text(f"token={_FAKE_SECRET}\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(tmp_path), "add", "-A"], check=True)
        findings = mto.collect_secrets_gate(tmp_path)
        assert any(f.path == "config.env" for f in findings)
        # The gate, like our normalization, never carries the value.
        assert _FAKE_SECRET not in repr(findings)

    def test_markdown_gate_flags_broken_link(self, tmp_path: Path) -> None:
        (tmp_path / "doc.md").write_text("[x](./missing.md)\n", encoding="utf-8")
        findings = mto.collect_markdown_links_gate(tmp_path)
        assert any(f.rule_id == "broken-link" for f in findings)

    def test_workflow_static_gate_runs_clean_on_empty(self, tmp_path: Path) -> None:
        (tmp_path / ".github" / "workflows").mkdir(parents=True)
        assert mto.collect_workflow_static_gate(tmp_path) == []


# ---------------------------------------------------------------------------
# Thin-IO runners (monkeypatched _run) + orchestration
# ---------------------------------------------------------------------------
class TestRunners:
    def test_argv_builders(self) -> None:
        assert mto.zizmor_argv()[0] == "zizmor"
        assert "--format" in mto.zizmor_argv()
        assert mto.lychee_argv(["a.md"])[-1] == "a.md"
        bl = mto.betterleaks_argv()
        assert "--redact=100" in bl and bl[-1] == "."

    def test_run_raises_when_binary_absent(self, tmp_path: Path) -> None:
        with pytest.raises(mto.ToolUnavailableError):
            mto._run(["definitely-not-a-real-binary-xyz"], tmp_path)

    def test_run_times_a_trivial_command(self, tmp_path: Path) -> None:
        out, ms = mto._run(["git", "--version"], tmp_path)
        assert out.startswith("git version")
        assert ms >= 0.0

    def test_run_zizmor_uses_parser(self, monkeypatch: pytest.MonkeyPatch) -> None:
        payload = json.dumps(
            [{"ident": "r", "locations": [
                {"symbolic": {"key": {"Local": {"given_path": "w.yml"}}},
                 "concrete": {"location": {"start_point": {"row": 0}}}}]}]
        )
        monkeypatch.setattr(mto, "_run", lambda argv, cwd: (payload, 5.0))
        findings, ms = mto.run_zizmor(REPO_ROOT)
        assert findings == [mto.Finding("r", "w.yml", 1)]
        assert ms == 5.0

    def test_run_lychee_uses_parser(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        (tmp_path / "a.md").write_text("# h\n", encoding="utf-8")
        payload = json.dumps({"error_map": {"a.md": [{"span": {"line": 2}}]}})
        monkeypatch.setattr(mto, "_run", lambda argv, cwd: (payload, 3.0))
        findings, ms = mto.run_lychee(tmp_path)
        assert findings == [mto.Finding("broken-link", "a.md", 2)]

    def test_run_betterleaks_redacts_via_parser(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        payload = json.dumps([{"RuleID": "github-pat", "File": "x.py", "StartLine": 1, "Secret": _FAKE_SECRET}])
        monkeypatch.setattr(mto, "_run", lambda argv, cwd: (payload, 1.0))
        findings, _ms = mto.run_betterleaks(tmp_path)
        assert findings == [mto.Finding("github-pat", "x.py", 1)]
        assert _FAKE_SECRET not in repr(findings)


class TestOrchestration:
    def _fake_spec(self) -> mto.PairSpec:
        return mto.PairSpec(
            pair_name="fake",
            new_tool="nt",
            existing_gate="eg",
            scope_label="s",
            run_tool=lambda root: ([mto.Finding("r", "f", 1), mto.Finding("r", "g", 2)], 4.0),
            collect_gate=lambda root: [mto.Finding("e", "f", 1)],
        )

    def test_measure_pair_with_fakes(self) -> None:
        record, new_f, gate_f = mto.measure_pair(
            self._fake_spec(), REPO_ROOT, commit_sha="sha", host_id="h", notes="n",
            now_ns=lambda: 123,
        )
        assert record["pair_name"] == "fake"
        assert record["measured_at_unix_nano"] == 123
        assert record["new_tool_findings"] == 2
        assert record["agree_count"] == 1
        assert len(new_f) == 2 and len(gate_f) == 1

    def test_select_pairs_default_is_all(self) -> None:
        assert mto._select_pairs(None) == mto.PAIRS

    def test_select_pairs_unknown_raises(self) -> None:
        with pytest.raises(ValueError, match="unknown pair"):
            mto._select_pairs("nope")

    def test_select_pairs_single(self) -> None:
        selected = mto._select_pairs("secrets")
        assert len(selected) == 1 and selected[0].pair_name == "secrets"

    def test_resolve_commit_explicit(self) -> None:
        assert mto._resolve_commit(REPO_ROOT, "abc") == "abc"

    def test_resolve_commit_fallback_no_git(self, monkeypatch: pytest.MonkeyPatch) -> None:
        def _boom(*a: object, **k: object) -> None:
            raise FileNotFoundError

        monkeypatch.setattr(mto.subprocess, "run", _boom)
        assert mto._resolve_commit(REPO_ROOT, None) == "unknown"

    def test_main_end_to_end_with_fake_pair(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(mto, "PAIRS", (self._fake_spec(),))
        out = tmp_path / "records.json"
        report = tmp_path / "report.md"
        rc = mto.main(
            [
                "--scope-root", str(REPO_ROOT),
                "--commit", "deadbeef",
                "--host-id", "hostx",
                "--output", str(out),
                "--report", str(report),
                "--notes", "cycle",
            ]
        )
        assert rc == 0
        records = json.loads(out.read_text(encoding="utf-8"))
        assert len(records) == 1
        assert tuple(records[0].keys()) == mto.RECORD_COLUMNS
        assert records[0]["commit_sha"] == "deadbeef"
        assert "## Tool overlap measurement" in report.read_text(encoding="utf-8")

    def test_main_writes_report_to_stdout(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        monkeypatch.setattr(mto, "PAIRS", (self._fake_spec(),))
        rc = mto.main(["--scope-root", str(REPO_ROOT), "--commit", "x", "--host-id", "h"])
        assert rc == 0
        assert "Tool overlap measurement" in capsys.readouterr().out


class TestSmoke:
    """Opt-in argv smoke validation (Refs #1632, Fact 1).

    The collector parses leniently, so a tool that REJECTS its argv (empty
    stdout, help on stderr) was recorded as a false zero-finding result. These
    tests prove the smoke step turns that masquerade into a loud failure, while
    an absent binary is a benign skip.
    """

    def _spec(self) -> mto.PairSpec:
        return mto.PairSpec(
            pair_name="secrets",
            new_tool="betterleaks",
            existing_gate="eg",
            scope_label="s",
            run_tool=lambda root: ([], 1.0),
            collect_gate=lambda root: [],
            argv_builder=lambda root: ["betterleaks", "dir", "."],
        )

    def test_empty_stdout_is_a_loud_fail(self) -> None:
        # The exact Fact 1 shape: a rejected flag prints help to stderr and
        # leaves stdout empty -- which must NOT pass as a clean (zero) scan.
        result = mto.smoke_pair(self._spec(), REPO_ROOT, run=lambda argv, cwd: ("", 10.0))
        assert result.status == "fail"
        assert "no stdout" in result.detail

    def test_unparseable_stdout_is_a_fail(self) -> None:
        result = mto.smoke_pair(self._spec(), REPO_ROOT, run=lambda argv, cwd: ("not json", 1.0))
        assert result.status == "fail"
        assert "parseable JSON" in result.detail

    def test_valid_json_is_ok(self) -> None:
        # betterleaks emits the literal `null` for a clean scan -- valid JSON,
        # non-empty stdout, so the argv was accepted.
        result = mto.smoke_pair(self._spec(), REPO_ROOT, run=lambda argv, cwd: ("null\n", 1.0))
        assert result.status == "ok"

    def test_absent_binary_is_skipped(self) -> None:
        def _absent(argv: object, cwd: object) -> tuple[str, float]:
            raise mto.ToolUnavailableError("required tool 'betterleaks' is not on PATH")

        result = mto.smoke_pair(self._spec(), REPO_ROOT, run=_absent)
        assert result.status == "skipped"

    def test_no_argv_builder_is_skipped(self) -> None:
        spec = mto.PairSpec(
            pair_name="p", new_tool="t", existing_gate="g", scope_label="s",
            run_tool=lambda root: ([], 1.0), collect_gate=lambda root: [],
        )
        assert mto.smoke_pair(spec, REPO_ROOT).status == "skipped"

    def test_cmd_smoke_exit_codes(self, capsys: pytest.CaptureFixture[str]) -> None:
        ok = mto.PairSpec(
            pair_name="ok", new_tool="t", existing_gate="g", scope_label="s",
            run_tool=lambda root: ([], 1.0), collect_gate=lambda root: [],
            argv_builder=lambda root: ["x"],
        )
        # Inject a passing then a failing run via _run monkeypatch is awkward for
        # two pairs; instead exercise cmd_smoke through smoke_pair's real path
        # with a binary that is absent (skip) -> exit 0.
        assert mto.cmd_smoke([ok], REPO_ROOT) == 0
        out = capsys.readouterr().out
        assert "smoke ok" in out

    def test_main_smoke_flag_skips_absent_binaries(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        # With --smoke and no binaries, every pair is skipped -> exit 0 (no-op
        # on the coverage runner). Force ToolUnavailableError for determinism.
        def _absent(argv: object, cwd: object) -> tuple[str, float]:
            raise mto.ToolUnavailableError("absent")

        monkeypatch.setattr(mto, "_run", _absent)
        rc = mto.main(["--scope-root", str(REPO_ROOT), "--smoke"])
        assert rc == 0
        assert "skipped" in capsys.readouterr().out

    def test_main_smoke_flag_fails_loud_on_bad_argv(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(mto, "_run", lambda argv, cwd: ("", 10.0))
        monkeypatch.setattr(mto, "PAIRS", (self._spec(),))
        rc = mto.main(["--scope-root", str(REPO_ROOT), "--smoke"])
        assert rc == 1
