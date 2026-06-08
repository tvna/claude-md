"""Tests for scripts/scan_apm_lock_drift.py.

The gate compares the MCP deps declared in apm.yml against the locked
mcp_servers / mcp_configs in apm.lock.yaml and fails on any mismatch (#1321).
These tests pin the parsing of both files, the three drift classes (missing
server, transport/url mismatch, orphan lock), the clean case, and a real-repo
self-check so the committed lockfile stays in step with apm.yml.
"""

from __future__ import annotations

import pytest
import scan_apm_lock_drift as gate

pytestmark = pytest.mark.shard_ci_ops

_APM_YML = """\
name: claude-md
dependencies:
  apm:
  - obra/superpowers#deadbeef
  mcp:
  - name: context7
    transport: http
    url: https://mcp.context7.com/mcp
"""

_LOCK_OK = """\
mcp_servers:
- context7
mcp_configs:
  context7:
    name: context7
    transport: http
    url: https://mcp.context7.com/mcp
"""


def test_declared_mcp_parses_name_and_fields() -> None:
    declared = gate.declared_mcp(_APM_YML)
    assert declared == {
        "context7": {"transport": "http", "url": "https://mcp.context7.com/mcp"}
    }


def test_declared_mcp_empty_when_no_mcp_block() -> None:
    assert gate.declared_mcp("name: x\ndependencies:\n  apm: []\n") == {}


def test_declared_mcp_skips_malformed_rows() -> None:
    assert gate.declared_mcp("dependencies:\n  mcp:\n  - http\n") == {}


def test_locked_mcp_parses_servers_and_configs() -> None:
    servers, configs = gate.locked_mcp(_LOCK_OK)
    assert servers == {"context7"}
    assert configs["context7"]["url"] == "https://mcp.context7.com/mcp"


def test_locked_mcp_empty_when_absent() -> None:
    servers, configs = gate.locked_mcp("apm_version: '0.12.1'\n")
    assert servers == set()
    assert configs == {}


def test_find_drift_clean() -> None:
    declared = gate.declared_mcp(_APM_YML)
    servers, configs = gate.locked_mcp(_LOCK_OK)
    assert gate.find_drift(declared, servers, configs) == []


def test_find_drift_missing_from_lock() -> None:
    """The exact #1321 drift: declared in apm.yml, absent from the lock."""
    declared = gate.declared_mcp(_APM_YML)
    errors = gate.find_drift(declared, set(), {})
    assert len(errors) == 2  # missing from mcp_servers AND mcp_configs
    assert all("context7" in e for e in errors)


def test_find_drift_url_mismatch() -> None:
    declared = gate.declared_mcp(_APM_YML)
    servers, configs = gate.locked_mcp(_LOCK_OK)
    configs["context7"]["url"] = "https://evil.example/mcp"
    errors = gate.find_drift(declared, servers, configs)
    assert len(errors) == 1
    assert "url drifted" in errors[0]


def test_find_drift_orphan_lock() -> None:
    """A server left in the lock after removal from apm.yml is flagged."""
    servers, configs = gate.locked_mcp(_LOCK_OK)
    errors = gate.find_drift({}, servers, configs)
    assert errors
    assert all("not declared in apm.yml" in e for e in errors)


def test_real_repo_lock_matches_apm_yml() -> None:
    """The committed apm.lock.yaml must lock every apm.yml MCP dep."""
    declared, servers, configs = gate._load(gate.REPO_ROOT)
    assert declared, "expected at least one MCP dep declared in apm.yml"
    assert gate.find_drift(declared, servers, configs) == []


def test_locked_mcp_skips_malformed_config() -> None:
    servers, configs = gate.locked_mcp(
        "mcp_servers:\n- context7\nmcp_configs:\n  context7: http\n"
    )
    assert servers == {"context7"}
    assert configs == {}


def test_read_missing_file_exits(tmp_path) -> None:
    with pytest.raises(SystemExit):
        gate._read(tmp_path, gate.APM_YML_REL)


def test_cli_verify_reports_drift(tmp_path, monkeypatch) -> None:
    """A repo whose lock lacks the declared MCP dep makes `verify` exit 1."""
    (tmp_path / gate.APM_YML_REL).write_text(_APM_YML, encoding="utf-8")
    (tmp_path / gate.APM_LOCK_REL).write_text(
        "apm_version: '0.12.1'\n", encoding="utf-8"
    )
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    assert gate.main(["verify"]) == 1


def test_cli_verify_clean_repo() -> None:
    assert gate.main(["verify"]) == 0


def test_cli_list_prints_servers(capsys: pytest.CaptureFixture[str]) -> None:
    assert gate.main(["list"]) == 0
    assert "context7" in capsys.readouterr().out
