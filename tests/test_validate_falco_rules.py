"""Tests for scripts/validate_falco_rules.py.

Covers: valid file passes, missing required fields fail, invalid priority
fails, wrong field name fails, malformed YAML fails, non-list top-level
fails, and the CLI verify subcommand exit codes. Refs #1847.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import validate_falco_rules as vfr

pytestmark = pytest.mark.shard_preflight

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_RULE = {
    "rule": "Test rule",
    "desc": "A test rule",
    "condition": "proc.name = bash",
    "output": "Test output proc=%proc.name",
    "priority": "WARNING",
    "tags": ["test"],
}

VALID_MACRO = {"macro": "is_bash", "condition": "proc.name = bash"}

VALID_LIST = {"list": "allowed_procs", "items": ["bash", "sh"]}


# ---------------------------------------------------------------------------
# _entry_type
# ---------------------------------------------------------------------------


def test_entry_type_rule() -> None:
    assert vfr._entry_type({"rule": "x", "desc": "y"}) == "rule"


def test_entry_type_macro() -> None:
    assert vfr._entry_type({"macro": "x"}) == "macro"


def test_entry_type_list() -> None:
    assert vfr._entry_type({"list": "x"}) == "list"


def test_entry_type_unknown() -> None:
    assert vfr._entry_type({"unknown_key": "x"}) is None


# ---------------------------------------------------------------------------
# validate_entries: valid cases
# ---------------------------------------------------------------------------


def test_valid_rule_no_errors() -> None:
    assert vfr.validate_entries("f.yaml", [VALID_RULE]) == []


def test_valid_macro_no_errors() -> None:
    assert vfr.validate_entries("f.yaml", [VALID_MACRO]) == []


def test_valid_list_no_errors() -> None:
    assert vfr.validate_entries("f.yaml", [VALID_LIST]) == []


def test_mixed_valid_entries_no_errors() -> None:
    entries = [VALID_RULE, VALID_MACRO, VALID_LIST]
    assert vfr.validate_entries("f.yaml", entries) == []


# ---------------------------------------------------------------------------
# validate_entries: missing required fields
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("missing_field", ["desc", "condition", "output", "priority"])
def test_missing_rule_body_field(missing_field: str) -> None:
    entry = dict(VALID_RULE)
    del entry[missing_field]
    errors = vfr.validate_entries("f.yaml", [entry])
    assert any(f"missing required field '{missing_field}'" in e for e in errors)


def test_missing_rule_type_key_reports_unrecognised() -> None:
    # When the 'rule' key itself is absent, _entry_type returns None
    # and the entry is reported as unrecognised, not as a missing field.
    entry = {k: v for k, v in VALID_RULE.items() if k != "rule"}
    errors = vfr.validate_entries("f.yaml", [entry])
    assert any("unrecognised type" in e for e in errors)


def test_missing_macro_condition() -> None:
    entry = {"macro": "is_bash"}
    errors = vfr.validate_entries("f.yaml", [entry])
    assert any("missing required field 'condition'" in e for e in errors)


def test_missing_macro_type_key_reports_unrecognised() -> None:
    entry = {"condition": "proc.name = bash"}
    errors = vfr.validate_entries("f.yaml", [entry])
    assert any("unrecognised type" in e for e in errors)


def test_missing_list_items() -> None:
    entry = {"list": "allowed_procs"}
    errors = vfr.validate_entries("f.yaml", [entry])
    assert any("missing required field 'items'" in e for e in errors)


def test_missing_list_type_key_reports_unrecognised() -> None:
    entry = {"items": ["bash", "sh"]}
    errors = vfr.validate_entries("f.yaml", [entry])
    assert any("unrecognised type" in e for e in errors)


# ---------------------------------------------------------------------------
# validate_entries: invalid priority
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "priority",
    ["SUPER_HIGH", "info", "critical_very", ""],
)
def test_invalid_priority(priority: str) -> None:
    entry = {**VALID_RULE, "priority": priority}
    errors = vfr.validate_entries("f.yaml", [entry])
    assert any("invalid priority" in e for e in errors)


@pytest.mark.parametrize(
    "priority",
    ["DEBUG", "INFORMATIONAL", "NOTICE", "WARNING", "ERROR", "CRITICAL", "ALERT", "EMERGENCY"],
)
def test_valid_priority_all_levels(priority: str) -> None:
    entry = {**VALID_RULE, "priority": priority}
    assert vfr.validate_entries("f.yaml", [entry]) == []


# ---------------------------------------------------------------------------
# validate_entries: wrong field names
# ---------------------------------------------------------------------------


def test_wrong_field_proc_exe_in_condition() -> None:
    entry = {**VALID_RULE, "condition": "proc.exe = /bin/bash"}
    errors = vfr.validate_entries("f.yaml", [entry])
    assert any("proc.exe" in e and "proc.exepath" in e for e in errors)


def test_wrong_field_proc_exe_in_output() -> None:
    entry = {**VALID_RULE, "output": "exe=%proc.exe name=%proc.name"}
    errors = vfr.validate_entries("f.yaml", [entry])
    assert any("proc.exe" in e and "proc.exepath" in e for e in errors)


def test_wrong_field_proc_cmdargs() -> None:
    entry = {**VALID_RULE, "condition": "proc.cmdargs contains --steal"}
    errors = vfr.validate_entries("f.yaml", [entry])
    assert any("proc.cmdargs" in e and "proc.cmdline" in e for e in errors)


def test_wrong_field_container_image() -> None:
    entry = {**VALID_RULE, "condition": "container.image startswith evil"}
    errors = vfr.validate_entries("f.yaml", [entry])
    assert any("container.image" in e and "container.image.repository" in e for e in errors)


def test_correct_field_proc_exepath_passes() -> None:
    entry = {**VALID_RULE, "condition": "proc.exepath startswith /tmp/"}
    assert vfr.validate_entries("f.yaml", [entry]) == []


# ---------------------------------------------------------------------------
# validate_entries: non-dict entries
# ---------------------------------------------------------------------------


def test_non_dict_entry_is_reported() -> None:
    errors = vfr.validate_entries("f.yaml", ["not a dict"])
    assert any("expected a mapping" in e for e in errors)


def test_unrecognised_entry_type_is_reported() -> None:
    errors = vfr.validate_entries("f.yaml", [{"unknown": "x"}])
    assert any("unrecognised type" in e for e in errors)


# ---------------------------------------------------------------------------
# validate_file: file-level errors
# ---------------------------------------------------------------------------


def test_invalid_yaml_is_rejected(tmp_path: Path) -> None:
    f = tmp_path / "bad.yaml"
    f.write_text("key: [unclosed bracket\n", encoding="utf-8")
    errors = vfr.validate_file(str(f))
    assert any("invalid YAML syntax" in e for e in errors)


def test_non_list_top_level_is_rejected(tmp_path: Path) -> None:
    f = tmp_path / "not_list.yaml"
    f.write_text("rule: just_a_mapping\n", encoding="utf-8")
    errors = vfr.validate_file(str(f))
    assert any("must be a YAML sequence" in e for e in errors)


def test_unreadable_file_is_rejected() -> None:
    errors = vfr.validate_file("/nonexistent/path/rules.yaml")
    assert any("cannot read file" in e for e in errors)


def test_valid_file_passes(tmp_path: Path) -> None:
    content = textwrap.dedent("""\
        - rule: Test rule
          desc: A test rule
          condition: proc.name = bash
          output: "Test output proc=%proc.name"
          priority: WARNING
          tags: [test]
        - macro: is_bash
          condition: proc.name = bash
        - list: allowed_procs
          items: [bash, sh]
    """)
    f = tmp_path / "rules.yaml"
    f.write_text(content, encoding="utf-8")
    assert vfr.validate_file(str(f)) == []


def test_current_custom_rules_file_passes() -> None:
    """The shipped custom-rules.yaml must pass the validator as-is."""
    errors = vfr.validate_file(".devcontainer/falco/custom-rules.yaml")
    assert errors == [], f"Validator failed on the shipped rules: {errors}"


# ---------------------------------------------------------------------------
# CLI: main() exit codes
# ---------------------------------------------------------------------------


def test_cli_verify_passes_on_valid_file(tmp_path: Path) -> None:
    f = tmp_path / "rules.yaml"
    f.write_text(
        "- rule: r\n  desc: d\n  condition: 'true'\n  output: o\n  priority: WARNING\n",
        encoding="utf-8",
    )
    assert vfr.main(["verify", "--file", str(f)]) == 0


def test_cli_verify_fails_on_invalid_file(tmp_path: Path) -> None:
    f = tmp_path / "rules.yaml"
    f.write_text(
        "- rule: r\n  desc: d\n  condition: 'true'\n  output: o\n",
        encoding="utf-8",
    )
    assert vfr.main(["verify", "--file", str(f)]) == 1


def test_cli_verify_fails_on_missing_file() -> None:
    assert vfr.main(["verify", "--file", "/nonexistent/rules.yaml"]) == 1
