"""Tests for ``scripts/scan_input_contract_drift.py``.

The contract gate is the deterministic enforcement for M4 (boundary
validation) and M9 (fail-loud/open) of the workflow-script-quality
standard: every workflow-called script must declare a ``Contract:``
docstring block. Refs #1087.
"""

from __future__ import annotations

import argparse
import textwrap
from pathlib import Path

import pytest
import scan_input_contract_drift as sicd

pytestmark = pytest.mark.shard_default

# A docstring that satisfies every element of the contract.
_COMPLIANT = textwrap.dedent(
    """\
    One-line purpose.

    Contract:
    - Inputs: the verify subcommand and --path.
    - Outputs: ::error:: annotations; exit 0/1.
    - Failure policy: fails loud per CLAUDE.md section 4.
    """
)


# ---------------------------------------------------------------------------
# check_contract
# ---------------------------------------------------------------------------


class TestCheckContract:
    def test_compliant_has_no_defects(self) -> None:
        assert sicd.check_contract(_COMPLIANT) == []

    def test_none_docstring(self) -> None:
        assert sicd.check_contract(None) == ["missing module docstring"]

    def test_empty_docstring(self) -> None:
        assert sicd.check_contract("") == ["missing module docstring"]

    def test_missing_contract_marker(self) -> None:
        doc = _COMPLIANT.replace("Contract:\n", "")
        assert "missing 'Contract:' marker line" in sicd.check_contract(doc)

    def test_missing_inputs(self) -> None:
        doc = _COMPLIANT.replace("- Inputs: the verify subcommand and --path.\n", "")
        assert "missing 'Inputs:' line" in sicd.check_contract(doc)

    def test_missing_outputs(self) -> None:
        doc = _COMPLIANT.replace("- Outputs: ::error:: annotations; exit 0/1.\n", "")
        assert "missing 'Outputs:' line" in sicd.check_contract(doc)

    def test_missing_failure_policy(self) -> None:
        doc = _COMPLIANT.replace(
            "- Failure policy: fails loud per CLAUDE.md section 4.\n", ""
        )
        assert "missing 'Failure policy:' line" in sicd.check_contract(doc)

    def test_failure_policy_without_loud_or_open(self) -> None:
        doc = _COMPLIANT.replace("fails loud per", "fails maybe per")
        assert (
            "'Failure policy:' must declare 'loud' or 'open'"
            in sicd.check_contract(doc)
        )

    @pytest.mark.parametrize("verb", ["loud", "open", "LOUD", "Open"])
    def test_failure_policy_accepts_loud_or_open_any_case(self, verb: str) -> None:
        doc = _COMPLIANT.replace("fails loud per", f"fails {verb} per")
        assert sicd.check_contract(doc) == []

    def test_tolerates_bullet_and_parenthetical_qualifier(self) -> None:
        # The real-world variant used by security_drift_report.py.
        doc = textwrap.dedent(
            """\
            Purpose.

            Contract:
            - Inputs (aggregate): upstream detector exit codes.
            - Outputs (aggregate): Markdown table to --summary-file.
            - Failure policy: fails loud per CLAUDE.md section 4.
            """
        )
        assert sicd.check_contract(doc) == []


# ---------------------------------------------------------------------------
# read_module_docstring
# ---------------------------------------------------------------------------


class TestReadModuleDocstring:
    def test_reads_module_docstring(self, tmp_path: Path) -> None:
        mod = tmp_path / "m.py"
        mod.write_text(f'"""{_COMPLIANT}"""\n', encoding="utf-8")
        assert sicd.read_module_docstring(mod) is not None
        assert "Contract:" in sicd.read_module_docstring(mod)  # type: ignore[operator]

    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert sicd.read_module_docstring(tmp_path / "absent.py") is None

    def test_syntax_error_returns_none(self, tmp_path: Path) -> None:
        mod = tmp_path / "bad.py"
        mod.write_text("def (:\n", encoding="utf-8")
        assert sicd.read_module_docstring(mod) is None

    def test_body_string_is_not_the_module_docstring(self, tmp_path: Path) -> None:
        # A string literal in the body must not count as the docstring.
        mod = tmp_path / "m.py"
        mod.write_text('x = "Contract:\\nInputs:"\n', encoding="utf-8")
        assert sicd.read_module_docstring(mod) is None


# ---------------------------------------------------------------------------
# collect_target_scripts
# ---------------------------------------------------------------------------


def _make_tree(tmp_path: Path) -> tuple[Path, Path]:
    workflows = tmp_path / "workflows"
    scripts = tmp_path / "scripts"
    workflows.mkdir()
    scripts.mkdir()
    return workflows, scripts


class TestCollectTargetScripts:
    def test_collects_referenced_public_scripts(self, tmp_path: Path) -> None:
        workflows, scripts = _make_tree(tmp_path)
        (workflows / "ci.yml").write_text(
            "run: python3 scripts/alpha.py verify\n", encoding="utf-8"
        )
        (scripts / "alpha.py").write_text('"""x."""\n', encoding="utf-8")
        assert sicd.collect_target_scripts(workflows, scripts) == {"alpha"}

    def test_excludes_private_helpers(self, tmp_path: Path) -> None:
        workflows, scripts = _make_tree(tmp_path)
        (workflows / "ci.yml").write_text(
            "run: python3 scripts/_helper.py\n", encoding="utf-8"
        )
        (scripts / "_helper.py").write_text('"""x."""\n', encoding="utf-8")
        assert sicd.collect_target_scripts(workflows, scripts) == set()

    def test_ignores_reference_to_nonexistent_script(self, tmp_path: Path) -> None:
        workflows, scripts = _make_tree(tmp_path)
        (workflows / "ci.yml").write_text(
            "# scripts/ghost.py was removed\n", encoding="utf-8"
        )
        assert sicd.collect_target_scripts(workflows, scripts) == set()


# ---------------------------------------------------------------------------
# find_violations
# ---------------------------------------------------------------------------


def _write_script(scripts: Path, name: str, docstring: str | None) -> None:
    body = f'"""{docstring}"""\n' if docstring is not None else "x = 1\n"
    (scripts / f"{name}.py").write_text(body, encoding="utf-8")


class TestFindViolations:
    def test_non_baseline_noncompliant_is_a_violation(self, tmp_path: Path) -> None:
        _, scripts = _make_tree(tmp_path)
        _write_script(scripts, "bad", "No contract here.")
        violations, stale = sicd.find_violations({"bad"}, scripts, {})
        assert [name for name, _ in violations] == ["bad"]
        assert stale == []

    def test_compliant_script_is_clean(self, tmp_path: Path) -> None:
        _, scripts = _make_tree(tmp_path)
        _write_script(scripts, "good", _COMPLIANT)
        assert sicd.find_violations({"good"}, scripts, {}) == ([], [])

    def test_baseline_entry_suppresses_violation(self, tmp_path: Path) -> None:
        _, scripts = _make_tree(tmp_path)
        _write_script(scripts, "legacy", "No contract.")
        violations, stale = sicd.find_violations(
            {"legacy"}, scripts, {"legacy": "deferred"}
        )
        assert violations == []
        assert stale == []

    def test_stale_baseline_when_now_compliant(self, tmp_path: Path) -> None:
        _, scripts = _make_tree(tmp_path)
        _write_script(scripts, "fixed", _COMPLIANT)
        violations, stale = sicd.find_violations(
            {"fixed"}, scripts, {"fixed": "deferred"}
        )
        assert violations == []
        assert stale == ["fixed"]

    def test_stale_baseline_when_no_longer_referenced(self, tmp_path: Path) -> None:
        _, scripts = _make_tree(tmp_path)
        _write_script(scripts, "gone", "No contract.")
        violations, stale = sicd.find_violations(set(), scripts, {"gone": "deferred"})
        assert violations == []
        assert stale == ["gone"]


# ---------------------------------------------------------------------------
# cmd_verify
# ---------------------------------------------------------------------------


class TestCmdVerify:
    def test_clean_tree_exits_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # The temp tree has no legacy scripts, so the live baseline would be
        # entirely stale against it; pin an empty baseline for the fixture.
        monkeypatch.setattr(sicd, "BASELINE_MISSING_CONTRACT", {})
        workflows, scripts = _make_tree(tmp_path)
        (workflows / "ci.yml").write_text(
            "run: python3 scripts/good.py verify\n", encoding="utf-8"
        )
        _write_script(scripts, "good", _COMPLIANT)
        args = argparse.Namespace(
            workflows_dir=str(workflows), scripts_dir=str(scripts)
        )
        assert sicd.cmd_verify(args) == 0

    def test_violation_exits_one_with_error_annotation(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr(sicd, "BASELINE_MISSING_CONTRACT", {})
        workflows, scripts = _make_tree(tmp_path)
        (workflows / "ci.yml").write_text(
            "run: python3 scripts/bad.py verify\n", encoding="utf-8"
        )
        _write_script(scripts, "bad", "No contract.")
        args = argparse.Namespace(
            workflows_dir=str(workflows), scripts_dir=str(scripts)
        )
        assert sicd.cmd_verify(args) == 1
        err = capsys.readouterr().err
        assert "::error file=scripts/bad.py::" in err
        assert "Contract:" in err


# ---------------------------------------------------------------------------
# Self-check: the live repository tree must satisfy the gate.
# ---------------------------------------------------------------------------


class TestLiveTree:
    def test_repository_tree_passes(self) -> None:
        target = sicd.collect_target_scripts(sicd.WORKFLOWS_DIR, sicd.SCRIPTS_DIR)
        violations, stale = sicd.find_violations(
            target, sicd.SCRIPTS_DIR, sicd.BASELINE_MISSING_CONTRACT
        )
        assert violations == []
        assert stale == []

    def test_main_verify_exits_zero(self) -> None:
        assert sicd.main(["verify"]) == 0
