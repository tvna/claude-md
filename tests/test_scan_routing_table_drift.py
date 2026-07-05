"""Tests for ``scripts/scan_routing_table_drift.py``.

Covers the runbook-table parser (condition/action/body-read normalization),
the registry-side normalization, the diff function (rule-count and per-rule
mismatch), the real-repo happy path (a clean tree is this gate's acceptance
bar), and the ``main`` CLI contract (exit 0/1/64), including a synthetic
runbook-cell edit and a synthetic registry edit each producing exit 1.

Refs #2300, #2298, #2246.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import scan_routing_table_drift as gate

pytestmark = pytest.mark.shard_preflight

_REPO_ROOT = Path(__file__).resolve().parent.parent

_RUNBOOK = """## Agent routing

Agents read `(type, state, severity, threat)` from the header alone and apply this table; **no body fetch is required for routing**:

| Condition | Agent action | Body read? |
|---|---|---|
| `state:rfc` OR `state:parked` | no-action | no |
| `type:tracking` | no-action on umbrella; act on sub-issues only | no |
| `severity:security` (regardless of other labels) | investigate (no autonomous PR) | yes |
| `type:fix` AND NOT `severity:security` | auto-fix candidate (mechanical PR allowed) | yes |
| `type:docs` | auto-fix candidate | yes |
| `type:feat` OR `type:refactor` | investigate; plan first, implementation awaits approval | yes |
| No `type:*` yet | triage-needed: read title only, set `type:*`, re-route | title only |

## Apply
"""

_REGISTRY_RULES: tuple[dict[str, object], ...] = (
    {"if_any": ["state:rfc", "state:parked"], "action": "no-action", "body_read": "no"},
    {"if_any": ["type:tracking"], "action": "no-action-umbrella", "body_read": "no"},
    {
        "if_any": ["severity:security"],
        "action": "investigate",
        "body_read": "yes",
        "autonomous_pr": False,
    },
    {
        "if_all": ["type:fix"],
        "if_none": ["severity:security"],
        "action": "auto-fix-candidate",
        "body_read": "yes",
        "autonomous_pr": True,
    },
    {
        "if_any": ["type:docs"],
        "action": "auto-fix-candidate",
        "body_read": "yes",
        "autonomous_pr": True,
    },
    {
        "if_any": ["type:feat", "type:refactor"],
        "action": "investigate",
        "body_read": "yes",
        "autonomous_pr": False,
    },
    {"default": True, "action": "triage-needed", "body_read": "title-only"},
)


# ---------------------------------------------------------------------------
# Runbook table parsing
# ---------------------------------------------------------------------------


class TestExtractTableLines:
    def test_extracts_seven_data_rows(self) -> None:
        assert len(gate.extract_table_lines(_RUNBOOK)) == 7

    def test_missing_heading_raises(self) -> None:
        with pytest.raises(gate.TableParseError, match="no '## Agent routing' heading"):
            gate.extract_table_lines("# Something else\n")

    def test_missing_header_row_raises(self) -> None:
        with pytest.raises(gate.TableParseError, match="no table header row"):
            gate.extract_table_lines("## Agent routing\n\nno table here\n")

    def test_no_data_rows_raises(self) -> None:
        text = "## Agent routing\n\n| Condition | Agent action | Body read? |\n|---|---|---|\n"
        with pytest.raises(gate.TableParseError, match="no data rows"):
            gate.extract_table_lines(text)

    def test_missing_separator_raises_instead_of_swallowing_first_row(self) -> None:
        """A deleted |---|---| separator must not silently eat the first data row."""
        text = (
            "## Agent routing\n\n"
            "| Condition | Agent action | Body read? |\n"
            "| `state:rfc` OR `state:parked` | no-action | no |\n"
            "| `type:tracking` | no-action on umbrella; act on sub-issues only | no |\n"
        )
        with pytest.raises(gate.TableParseError, match="separator row"):
            gate.extract_table_lines(text)


class TestSplitRow:
    def test_wrong_cell_count_raises(self) -> None:
        with pytest.raises(gate.TableParseError, match="expected 3 cells"):
            gate.split_row("| only | two |")


class TestParseCondition:
    def test_if_any_two_tokens(self) -> None:
        assert gate.parse_condition("`state:rfc` OR `state:parked`") == {
            "if_any": ["state:rfc", "state:parked"]
        }

    def test_if_any_single_token(self) -> None:
        assert gate.parse_condition("`type:tracking`") == {"if_any": ["type:tracking"]}

    def test_if_any_ignores_parenthetical(self) -> None:
        assert gate.parse_condition("`severity:security` (regardless of other labels)") == {
            "if_any": ["severity:security"]
        }

    def test_if_all_and_if_none(self) -> None:
        assert gate.parse_condition("`type:fix` AND NOT `severity:security`") == {
            "if_all": ["type:fix"],
            "if_none": ["severity:security"],
        }

    def test_default_row(self) -> None:
        assert gate.parse_condition("No `type:*` yet") == {"default": True}

    def test_no_token_raises(self) -> None:
        with pytest.raises(gate.TableParseError, match="no label token"):
            gate.parse_condition("nothing quoted here")

    def test_multi_label_without_or_raises(self) -> None:
        """Codex review on #2325: a mistaken AND must not silently parse as OR."""
        with pytest.raises(gate.TableParseError, match="not joined by ' OR '"):
            gate.parse_condition("`type:feat` AND `type:refactor`")

    def test_multi_label_bare_juxtaposition_raises(self) -> None:
        with pytest.raises(gate.TableParseError, match="not joined by ' OR '"):
            gate.parse_condition("`state:rfc` `state:parked`")

    def test_if_any_tolerates_trailing_parenthetical(self) -> None:
        """A harmless clarifying aside (the single-token rows' own style) must still parse."""
        assert gate.parse_condition("`type:feat` OR `type:refactor` (either kind of change)") == {
            "if_any": ["type:feat", "type:refactor"]
        }

    def test_and_not_before_clause_with_wrong_combinator_raises(self) -> None:
        """Codex review (#2329): if_all means AND semantics, so OR prose must be rejected."""
        with pytest.raises(gate.TableParseError, match="not joined by ' AND '"):
            gate.parse_condition("`type:feat` OR `type:refactor` AND NOT `severity:security`")

    def test_and_not_before_clause_with_correct_and_still_works(self) -> None:
        assert gate.parse_condition("`type:feat` AND `type:refactor` AND NOT `severity:security`") == {
            "if_all": ["type:feat", "type:refactor"],
            "if_none": ["severity:security"],
        }

    def test_and_not_after_clause_with_wrong_combinator_raises(self) -> None:
        """if_none is also AND semantics (each label independently excluded), not OR."""
        with pytest.raises(gate.TableParseError, match="not joined by ' AND '"):
            gate.parse_condition("`type:fix` AND NOT `severity:security` OR `layer:meta`")

    def test_and_not_after_clause_with_correct_and_still_works(self) -> None:
        assert gate.parse_condition("`type:fix` AND NOT `severity:security` AND `layer:meta`") == {
            "if_all": ["type:fix"],
            "if_none": ["severity:security", "layer:meta"],
        }

    def test_default_row_tolerates_extra_label_mention(self) -> None:
        """A clarifying second label mention in the catch-all row must not defeat detection."""
        assert gate.parse_condition("No `type:*` yet (see `type:tracking` for reference)") == {
            "default": True
        }

    def test_bare_negation_outside_and_not_raises(self) -> None:
        with pytest.raises(gate.TableParseError, match="negates a label outside an 'AND NOT' clause"):
            gate.parse_condition("NOT `type:archived`")


class TestParseAction:
    def test_no_action(self) -> None:
        assert gate.parse_action("no-action") == {"action": "no-action"}

    def test_no_action_umbrella(self) -> None:
        assert gate.parse_action("no-action on umbrella; act on sub-issues only") == {
            "action": "no-action-umbrella"
        }

    def test_investigate_with_note(self) -> None:
        assert gate.parse_action("investigate (no autonomous PR)") == {
            "action": "investigate",
            "autonomous_pr": False,
        }

    def test_investigate_plain(self) -> None:
        assert gate.parse_action("investigate; plan first, implementation awaits approval") == {
            "action": "investigate",
            "autonomous_pr": False,
        }

    def test_auto_fix_candidate_with_note(self) -> None:
        assert gate.parse_action("auto-fix candidate (mechanical PR allowed)") == {
            "action": "auto-fix-candidate",
            "autonomous_pr": True,
        }

    def test_auto_fix_candidate_plain(self) -> None:
        assert gate.parse_action("auto-fix candidate") == {
            "action": "auto-fix-candidate",
            "autonomous_pr": True,
        }

    def test_triage_needed(self) -> None:
        assert gate.parse_action("triage-needed: read title only, set `type:*`, re-route") == {
            "action": "triage-needed"
        }

    def test_unrecognised_action_raises(self) -> None:
        with pytest.raises(gate.TableParseError, match="unrecognised action"):
            gate.parse_action("do something else")


class TestParseBodyRead:
    @pytest.mark.parametrize(
        ("cell", "expected"),
        [("no", "no"), ("yes", "yes"), ("title only", "title-only"), ("Title Only", "title-only")],
    )
    def test_known_values(self, cell: str, expected: str) -> None:
        assert gate.parse_body_read(cell) == expected

    def test_unrecognised_raises(self) -> None:
        with pytest.raises(gate.TableParseError, match="unrecognised body-read"):
            gate.parse_body_read("maybe")


class TestParseRunbookRules:
    def test_matches_canonical_registry_shape(self) -> None:
        assert gate.parse_runbook_rules(_RUNBOOK) == list(_REGISTRY_RULES)


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


class TestDiffRules:
    def test_equal_rules_return_none(self) -> None:
        rules = list(_REGISTRY_RULES)
        assert gate.diff_rules(rules, rules) is None

    def test_count_mismatch(self) -> None:
        rules = list(_REGISTRY_RULES)
        message = gate.diff_rules(rules[:-1], rules)
        assert message is not None
        assert "rule count differs" in message

    def test_first_divergent_rule_named(self) -> None:
        rules = list(_REGISTRY_RULES)
        mutated = [dict(rules[0]), *rules[1:]]
        mutated[0]["body_read"] = "yes"
        message = gate.diff_rules(mutated, rules)
        assert message is not None
        assert "rule 0 diverges" in message


# ---------------------------------------------------------------------------
# Real-repo happy path + CLI contract
# ---------------------------------------------------------------------------


class TestRealRepoAndCli:
    def test_verify_clean_tree(self) -> None:
        assert gate.verify(_REPO_ROOT / gate._RUNBOOK_PATH) == []

    def test_main_verify_exit_zero(self) -> None:
        assert gate.main(["verify"]) == 0

    def test_main_unknown_subcommand_exit_64(self) -> None:
        assert gate.main(["bogus"]) == 64

    def test_main_no_subcommand_exit_64(self) -> None:
        assert gate.main([]) == 64

    def test_synthetic_runbook_edit_exits_one(self, tmp_path: Path) -> None:
        """A table-only edit (registry unchanged) fails the gate."""
        mutated = _RUNBOOK.replace(
            "| `type:docs` | auto-fix candidate | yes |",
            "| `type:docs` | auto-fix candidate | no |",
        )
        runbook_path = tmp_path / "issue-triage.md"
        runbook_path.write_text(mutated, encoding="utf-8")
        errors = gate.verify(runbook_path)
        assert len(errors) == 1
        assert "diverges" in errors[0]

    def test_synthetic_registry_edit_exits_one(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A registry-only edit (runbook table unchanged) fails the gate."""
        runbook_path = tmp_path / "issue-triage.md"
        runbook_path.write_text(_RUNBOOK, encoding="utf-8")

        mutated_rules = (*_REGISTRY_RULES[:-1], {"default": True, "action": "no-action", "body_read": "no"})
        monkeypatch.setattr(gate._ssot, "routing_rules", lambda: mutated_rules)
        errors = gate.verify(runbook_path)
        assert len(errors) == 1
        assert "diverges" in errors[0]

    def test_missing_runbook_exits_with_parse_error(self, tmp_path: Path) -> None:
        errors = gate.verify(tmp_path / "nope.md")
        assert len(errors) == 1
        assert "cannot parse" in errors[0]

    def test_registry_type_error_is_a_loud_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise() -> tuple[dict[str, object], ...]:
            raise TypeError("label_routing.rules is missing")

        runbook_path = tmp_path / "issue-triage.md"
        runbook_path.write_text(_RUNBOOK, encoding="utf-8")
        monkeypatch.setattr(gate._ssot, "routing_rules", _raise)
        errors = gate.verify(runbook_path)
        assert len(errors) == 1
        assert "cannot read label_routing.rules" in errors[0]

    def test_registry_json_decode_error_is_a_loud_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A corrupted .gitapex/ssot.json must fail loud, not crash with a raw traceback."""
        import json

        def _raise() -> tuple[dict[str, object], ...]:
            return json.loads("{not valid json")

        runbook_path = tmp_path / "issue-triage.md"
        runbook_path.write_text(_RUNBOOK, encoding="utf-8")
        monkeypatch.setattr(gate._ssot, "routing_rules", _raise)
        errors = gate.verify(runbook_path)
        assert len(errors) == 1
        assert "cannot read label_routing.rules" in errors[0]

    def test_registry_missing_file_is_a_loud_error(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        def _raise() -> tuple[dict[str, object], ...]:
            raise FileNotFoundError("no such file: .gitapex/ssot.json")

        runbook_path = tmp_path / "issue-triage.md"
        runbook_path.write_text(_RUNBOOK, encoding="utf-8")
        monkeypatch.setattr(gate._ssot, "routing_rules", _raise)
        errors = gate.verify(runbook_path)
        assert len(errors) == 1
        assert "cannot read label_routing.rules" in errors[0]

    def test_non_utf8_runbook_is_a_loud_error(self, tmp_path: Path) -> None:
        """A non-UTF-8 runbook must fail loud, not crash with an unhandled UnicodeDecodeError."""
        runbook_path = tmp_path / "issue-triage.md"
        runbook_path.write_bytes(b"## Agent routing\n\n\xff\xfe not valid utf-8")
        errors = gate.verify(runbook_path)
        assert len(errors) == 1
        assert "cannot parse" in errors[0]

    def test_error_annotation_names_the_actual_runbook_path(self, tmp_path: Path) -> None:
        """The file= field must name the path actually read, not the module's default constant."""
        custom_path = tmp_path / "custom-runbook.md"
        custom_path.write_text("no agent routing heading here", encoding="utf-8")
        errors = gate.verify(custom_path)
        assert len(errors) == 1
        assert str(custom_path) in errors[0]
        assert gate._RUNBOOK_PATH not in errors[0]

    def test_main_exit_one_on_mismatch(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        mutated = _RUNBOOK.replace(
            "| `type:docs` | auto-fix candidate | yes |",
            "| `type:docs` | auto-fix candidate | no |",
        )
        (tmp_path / "issue-triage.md").write_text(mutated, encoding="utf-8")
        monkeypatch.setattr(gate, "_REPO_ROOT", tmp_path)
        assert gate.main(["verify", "--runbook", "issue-triage.md"]) == 1

    def test_main_argv_defaults_to_sys_argv(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(sys, "argv", ["scan_routing_table_drift.py", "verify"])
        assert gate.main() == 0
