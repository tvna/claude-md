"""Tests for ``scripts/scan_hardcoded_label_literals.py``.

Covers the pure detector (full-value match; family-prefix, search-fragment,
HTML-marker, and docstring non-matches), the two-tier allowlist, the
family-coverage drift guard, the real-repo happy path (a clean tree is this
gate's acceptance bar), and the ``main`` CLI contract (exit 0/1/64).

Refs #2299, #2298, #2246, #1041.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_hardcoded_label_literals as gate

pytestmark = pytest.mark.shard_preflight

_REPO_ROOT = Path(__file__).resolve().parent.parent


# ---------------------------------------------------------------------------
# Detector: iter_label_literals
# ---------------------------------------------------------------------------


class TestIterLabelLiterals:
    def test_flags_full_value_label_constant(self) -> None:
        src = 'BAD = "layer:meta"\n'
        assert gate.iter_label_literals(src) == [(1, "layer:meta")]

    def test_flags_each_family(self) -> None:
        src = "\n".join(f'X{i} = "{fam}:name"' for i, fam in enumerate(gate.KNOWN_FAMILIES))
        found = {lit for _ln, lit in gate.iter_label_literals(src)}
        assert found == {f"{fam}:name" for fam in gate.KNOWN_FAMILIES}

    def test_ignores_family_prefix_without_name_segment(self) -> None:
        # The migration-safe pattern: label.startswith("severity:").
        src = 'if label.startswith("severity:"):\n    pass\n'
        assert gate.iter_label_literals(src) == []

    def test_ignores_search_query_fragment_substring(self) -> None:
        src = 'Q = " type:pr is:merged merged:>=2024"\n'
        assert gate.iter_label_literals(src) == []

    def test_ignores_html_marker_substring(self) -> None:
        # "<!-- auto-retro:back-link -->" contains "retro:back-link" as a
        # substring but is not a whole-value label token.
        src = 'MARKER = "<!-- auto-retro:back-link -->"\n'
        assert gate.iter_label_literals(src) == []

    def test_ignores_docstring_prose(self) -> None:
        src = '"""Applies type:tracking and layer:p3-harness to the issue."""\n'
        assert gate.iter_label_literals(src) == []

    def test_ignores_unknown_family(self) -> None:
        src = 'X = "threat:intel-needed"\n'  # retired family, not in KNOWN_FAMILIES
        assert gate.iter_label_literals(src) == []

    def test_reports_lineno(self) -> None:
        src = "A = 1\n\nB = 2\nC = 'type:fix'\n"
        assert gate.iter_label_literals(src) == [(4, "type:fix")]

    def test_syntax_error_propagates(self) -> None:
        with pytest.raises(SyntaxError):
            gate.iter_label_literals("def (:\n")


# ---------------------------------------------------------------------------
# Allowlist and scan_file
# ---------------------------------------------------------------------------


class TestScanFile:
    def test_flags_literal_in_non_allowlisted_file(self) -> None:
        errors = gate.scan_file("scripts/some_new_gate.py", 'X = "layer:meta"\n')
        assert len(errors) == 1
        assert "scripts/some_new_gate.py,line=1" in errors[0]
        assert "layer:meta" in errors[0]

    def test_ssot_home_file_is_wholly_exempt(self) -> None:
        # _retro_labels.py may hold any retro:* literal; whole file exempt.
        src = 'RETRO_TP = "retro:tp"\nRETRO_FP = "retro:new-one"\n'
        assert gate.scan_file("scripts/_retro_labels.py", src) == []

    def test_literal_allowlist_exempts_exact_pair_only(self) -> None:
        # The allowlisted exact literal passes...
        ok = gate.scan_file("scripts/_ref_classifier.py", 'TRACKING = "type:tracking"\n')
        assert ok == []
        # ...but a different literal in the same file is still rejected.
        bad = gate.scan_file("scripts/_ref_classifier.py", 'OTHER = "layer:meta"\n')
        assert len(bad) == 1
        assert "layer:meta" in bad[0]

    def test_parse_failure_is_a_loud_error(self) -> None:
        errors = gate.scan_file("scripts/broken.py", "def (:\n")
        assert len(errors) == 1
        assert "cannot parse" in errors[0]

    def test_is_allowlisted(self) -> None:
        assert gate.is_allowlisted("scripts/_ssot.py", "type:feat")
        assert gate.is_allowlisted("scripts/_ref_classifier.py", "type:tracking")
        assert not gate.is_allowlisted("scripts/_ref_classifier.py", "type:feat")
        assert not gate.is_allowlisted("scripts/other.py", "type:tracking")


# ---------------------------------------------------------------------------
# Family-coverage drift guard
# ---------------------------------------------------------------------------


class TestFamilyCoverage:
    def test_policy_family_names(self) -> None:
        policy = {"families": [{"name": "layer"}, {"name": "area"}, {"bad": 1}]}
        assert gate.policy_family_names(policy) == frozenset({"layer", "area"})

    def test_uncovered_families_empty_when_covered(self) -> None:
        policy = {"families": [{"name": "layer"}, {"name": "type"}]}
        assert gate.uncovered_families(policy) == frozenset()

    def test_uncovered_families_flags_new_family(self) -> None:
        policy = {"families": [{"name": "brandnew"}]}
        assert gate.uncovered_families(policy) == frozenset({"brandnew"})

    def test_known_families_superset_of_live_label_policy(self) -> None:
        """Drift guard: every governed family must be covered by the gate.

        Shipped in the same change as the gate (CLAUDE.md section 3): adding a
        family to .github/label-policy.toml without teaching KNOWN_FAMILIES
        fails here, forcing the gate to learn the new family's literals.
        """
        import tomllib

        policy = tomllib.loads((_REPO_ROOT / gate._LABEL_POLICY_PATH).read_text(encoding="utf-8"))
        assert gate.uncovered_families(policy) == frozenset()


# ---------------------------------------------------------------------------
# Allowlist hygiene against the real tree
# ---------------------------------------------------------------------------


class TestAllowlistHygiene:
    def test_literal_allowlist_entries_are_live(self) -> None:
        """Every LITERAL_ALLOWLIST (path, literal) must still exist in the tree.

        A stale entry (the literal was removed or the file deleted) would
        silently widen the exemption; this keeps the allowlist a true mirror.
        """
        for (path, literal), rationale in gate.LITERAL_ALLOWLIST.items():
            file_path = _REPO_ROOT / path
            assert file_path.is_file(), f"allowlisted path {path} is gone"
            found = {lit for _ln, lit in gate.iter_label_literals(file_path.read_text(encoding="utf-8"))}
            assert literal in found, (
                f"allowlisted literal {literal!r} no longer appears in {path}; "
                f"drop the stale LITERAL_ALLOWLIST entry"
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
        import tomllib

        policy = tomllib.loads((_REPO_ROOT / gate._LABEL_POLICY_PATH).read_text(encoding="utf-8"))
        assert gate.verify(_REPO_ROOT, "scripts", policy) == []

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
        # A minimal label-policy so the family-coverage guard passes and the
        # exit-1 comes from the injected literal, not a missing policy file.
        (tmp_path / "label-policy.toml").write_text(
            '[[families]]\nname = "layer"\ncardinality = "one_or_more"\n',
            encoding="utf-8",
        )
        # tmp_path is not a git repo, so list_script_files falls back to the
        # on-disk glob under the (redirected) repo root.
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


# ---------------------------------------------------------------------------
# list_script_files
# ---------------------------------------------------------------------------


def test_list_script_files_fallback_globs_on_disk(tmp_path: Path) -> None:
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "a.py").write_text("x = 1\n", encoding="utf-8")
    (scripts / "b.py").write_text("y = 2\n", encoding="utf-8")
    (scripts / "notpy.txt").write_text("z\n", encoding="utf-8")
    # tmp_path is not a git repo; git ls-files returns nonzero -> on-disk glob.
    result = gate.list_script_files(tmp_path, "scripts")
    assert result == ["scripts/a.py", "scripts/b.py"]
