"""Tests for ``scripts/scan_hardcoded_label_literals.py``.

Covers the derived known-family set (live + retired + runtime-only), the pure
detector (full-value match; family-prefix, search-fragment, HTML-marker, and
docstring non-matches), the count-bound allowlist (a second copy of an
allowlisted literal is still rejected), the real-repo happy path (a clean tree
is this gate's acceptance bar), and the ``main`` CLI contract (exit 0/1/64).

Refs #2299, #2298, #2246, #1041.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import scan_hardcoded_label_literals as gate

pytestmark = pytest.mark.shard_preflight

_REPO_ROOT = Path(__file__).resolve().parent.parent


def _live_policy() -> dict[str, object]:
    return tomllib.loads((_REPO_ROOT / gate._LABEL_POLICY_PATH).read_text(encoding="utf-8"))


def _live_label_re() -> re.Pattern[str]:
    return gate.build_label_re(gate.known_families(_live_policy()))


# ---------------------------------------------------------------------------
# Known families (derived from label-policy)
# ---------------------------------------------------------------------------


class TestKnownFamilies:
    def test_policy_family_names(self) -> None:
        policy = {"families": [{"name": "layer"}, {"name": "area"}, {"bad": 1}]}
        assert gate.policy_family_names(policy) == frozenset({"layer", "area"})

    def test_retired_family_names_extracts_prefix(self) -> None:
        policy = {
            "retired_labels": [
                {"name": "threat:intel-needed"},
                {"name": "agent:*"},
                {"name": "layer:meta"},
                {"name": "bug"},  # bare name, no family
            ]
        }
        assert gate.retired_family_names(policy) == frozenset({"threat", "agent", "layer"})

    def test_known_families_unions_live_retired_runtime(self) -> None:
        # RUNTIME_ONLY_FAMILIES is empty since #2442 batch 1 (retro moved into the
        # catalog), so the derived set is exactly live [[families]] + retired
        # family prefixes for a synthetic policy that declares no retro family.
        policy = {
            "families": [{"name": "layer"}, {"name": "type"}],
            "retired_labels": [{"name": "threat:x"}, {"name": "agent:y"}],
        }
        assert gate.known_families(policy) == frozenset({"layer", "type", "threat", "agent"})

    def test_runtime_only_families_is_empty(self) -> None:
        # Pins the post-#2442 state: retro is now a live catalog family, so no
        # runtime-only family remains. A future runtime-only family added here is
        # a conscious change that updates this pin.
        assert not gate.RUNTIME_ONLY_FAMILIES

    def test_live_policy_covers_retired_threat_and_agent(self) -> None:
        """Regression guard for the Codex review: retired families are scanned.

        The retired threat:* / agent:* families must be in the derived set so a
        hardcoded reference to a retired label is caught (#1041 AC#3). ``retro``
        is now a live [[families]] entry (#2442), so it is covered too.
        """
        fams = gate.known_families(_live_policy())
        assert {"threat", "agent", "retro"} <= fams
        # And a retired threat literal actually matches the built regex.
        assert _live_label_re().match("threat:response-needed")


# ---------------------------------------------------------------------------
# Detector: iter_label_literals
# ---------------------------------------------------------------------------


class TestIterLabelLiterals:
    def test_flags_full_value_label_constant(self) -> None:
        assert gate.iter_label_literals('BAD = "layer:meta"\n', _live_label_re()) == [(1, "layer:meta")]

    def test_flags_retired_threat_literal(self) -> None:
        assert gate.iter_label_literals('X = "threat:response-needed"\n', _live_label_re()) == [
            (1, "threat:response-needed")
        ]

    def test_ignores_family_prefix_without_name_segment(self) -> None:
        # The migration-safe pattern: label.startswith("severity:").
        assert gate.iter_label_literals('if label.startswith("severity:"):\n    pass\n', _live_label_re()) == []

    def test_ignores_search_query_fragment_substring(self) -> None:
        assert gate.iter_label_literals('Q = " type:pr is:merged merged:>=2024"\n', _live_label_re()) == []

    def test_ignores_html_marker_substring(self) -> None:
        # "<!-- auto-retro:back-link -->" contains "retro:back-link" as a
        # substring but is not a whole-value label token.
        assert gate.iter_label_literals('MARKER = "<!-- auto-retro:back-link -->"\n', _live_label_re()) == []

    def test_ignores_docstring_prose(self) -> None:
        assert (
            gate.iter_label_literals(
                '"""Applies type:tracking and layer:p3-harness to the issue."""\n',
                _live_label_re(),
            )
            == []
        )

    def test_ignores_unknown_family(self) -> None:
        # "colour" is not a known family, live or retired.
        assert gate.iter_label_literals('X = "colour:blue"\n', _live_label_re()) == []

    def test_syntax_error_propagates(self) -> None:
        with pytest.raises(SyntaxError):
            gate.iter_label_literals("def (:\n", _live_label_re())


# ---------------------------------------------------------------------------
# Allowlist and scan_file (count-bound)
# ---------------------------------------------------------------------------


class TestScanFile:
    def test_flags_literal_in_non_allowlisted_file(self) -> None:
        errors = gate.scan_file("scripts/some_new_gate.py", 'X = "layer:meta"\n', _live_label_re())
        assert len(errors) == 1
        assert "scripts/some_new_gate.py,line=1" in errors[0]
        assert "layer:meta" in errors[0]

    def test_ssot_home_file_is_wholly_exempt(self) -> None:
        src = 'RETRO_TP = "retro:tp"\nRETRO_FP = "retro:new-one"\n'
        assert gate.scan_file("scripts/_retro_labels.py", src, _live_label_re()) == []

    def test_allowlisted_literal_first_occurrence_passes(self) -> None:
        assert (
            gate.scan_file(
                "scripts/_ref_classifier.py",
                'TRACKING = "type:tracking"\n',
                _live_label_re(),
            )
            == []
        )

    def test_second_copy_of_allowlisted_literal_is_rejected(self) -> None:
        """Codex review: bind the exemption to the sanctioned occurrence only."""
        src = 'A = "type:tracking"\nB = "type:tracking"\n'
        errors = gate.scan_file("scripts/_ref_classifier.py", src, _live_label_re())
        assert len(errors) == 1
        assert "line=2" in errors[0]
        assert "exceeds the 1 allowlisted" in errors[0]

    def test_different_literal_in_allowlisted_file_is_rejected(self) -> None:
        errors = gate.scan_file("scripts/_ref_classifier.py", 'OTHER = "layer:meta"\n', _live_label_re())
        assert len(errors) == 1
        assert "layer:meta" in errors[0]

    def test_parse_failure_is_a_loud_error(self) -> None:
        errors = gate.scan_file("scripts/broken.py", "def (:\n", _live_label_re())
        assert len(errors) == 1
        assert "cannot parse" in errors[0]

    def test_allowed_occurrences(self) -> None:
        assert gate.allowed_occurrences("scripts/_ref_classifier.py", "type:tracking") == 1
        assert gate.allowed_occurrences("scripts/other.py", "type:tracking") == 0


# ---------------------------------------------------------------------------
# Allowlist hygiene against the real tree
# ---------------------------------------------------------------------------


class TestAllowlistHygiene:
    def test_literal_allowlist_entries_are_live_and_counted(self) -> None:
        """Every LITERAL_ALLOWLIST entry must match its file's actual count.

        A stale entry (literal removed, file deleted) or a wrong count would
        silently widen or misstate the exemption; this keeps it a true mirror.
        """
        label_re = _live_label_re()
        for (path, literal), (count, rationale) in gate.LITERAL_ALLOWLIST.items():
            file_path = _REPO_ROOT / path
            assert file_path.is_file(), f"allowlisted path {path} is gone"
            actual = [
                lit
                for _ln, lit in gate.iter_label_literals(file_path.read_text(encoding="utf-8"), label_re)
                if lit == literal
            ]
            assert actual, (
                f"allowlisted literal {literal!r} no longer appears in {path}; "
                f"drop the stale LITERAL_ALLOWLIST entry"
            )
            assert len(actual) == count, (
                f"{path}: {literal!r} appears {len(actual)} time(s) but the "
                f"allowlist expects {count}; update the count"
            )
            assert rationale.strip(), f"empty rationale for ({path}, {literal})"

    def test_ssot_home_files_exist(self) -> None:
        for path in gate.SSOT_HOME_FILES:
            assert (_REPO_ROOT / path).is_file(), f"SSoT home {path} is gone"


# ---------------------------------------------------------------------------
# Real-repo happy path + CLI contract
# ---------------------------------------------------------------------------


class TestRealRepoAndCli:
    def test_verify_clean_tree(self) -> None:
        """The tree that introduces the gate carries no unsanctioned literal."""
        assert gate.verify(_REPO_ROOT, "scripts", _live_policy()) == []

    def test_verify_empty_policy_is_loud_error(self) -> None:
        errors = gate.verify(_REPO_ROOT, "scripts", {"families": []})
        assert len(errors) == 1
        assert "no [[families]]" in errors[0]

    def test_main_verify_exit_zero(self) -> None:
        assert gate.main(["verify"]) == 0

    def test_main_unknown_subcommand_exit_64(self) -> None:
        assert gate.main(["bogus"]) == 64

    def test_main_no_subcommand_exit_64(self) -> None:
        assert gate.main([]) == 64

    def test_main_exit_one_on_injected_literal(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A hardcoded literal in a scanned scripts/*.py fails the gate."""
        scripts = tmp_path / "scripts"
        scripts.mkdir()
        (scripts / "offender.py").write_text('X = "layer:meta"\n', encoding="utf-8")
        (tmp_path / "label-policy.toml").write_text(
            '[[families]]\nname = "layer"\ncardinality = "one_or_more"\n',
            encoding="utf-8",
        )
        monkeypatch.setattr(gate, "_REPO_ROOT", tmp_path)
        assert (
            gate.main(
                [
                    "verify",
                    "--scripts-dir",
                    "scripts",
                    "--label-policy",
                    "label-policy.toml",
                ]
            )
            == 1
        )

    def test_missing_label_policy_exit_one(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr(gate, "_REPO_ROOT", tmp_path)
        assert gate.main(["verify", "--label-policy", "nope.toml"]) == 1


def test_list_script_files_fallback_globs_on_disk(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "a.py").write_text("x = 1\n", encoding="utf-8")
    (scripts / "b.py").write_text("y = 2\n", encoding="utf-8")
    (scripts / "notpy.txt").write_text("z\n", encoding="utf-8")
    # tmp_path is not a git repo; git ls-files returns nonzero -> on-disk glob.
    assert gate.list_script_files(tmp_path, "scripts") == ["scripts/a.py", "scripts/b.py"]
