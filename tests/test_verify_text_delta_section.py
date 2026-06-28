"""Tests for ``scripts/verify_text_delta_section.py``.

Table-driven style: pure functions get parametrize cases, the
subprocess boundary is exercised via a fake ``runner`` injected through
the kwarg the production code already exposes.

The ``scripts/`` directory is on ``sys.path`` via ``pythonpath`` under
``[tool.pytest.ini_options]`` in ``pyproject.toml``.
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

import pytest
import verify_text_delta_section as gate

pytestmark = pytest.mark.shard_ci_ops


def _fake_runner(stdout: str = "", returncode: int = 0):
    """Return a callable mimicking ``subprocess.run(..., check=True)``."""

    def runner(cmd: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if kwargs.get("check") and returncode != 0:
            raise subprocess.CalledProcessError(
                returncode, cmd, output=stdout, stderr=""
            )
        return subprocess.CompletedProcess[str](
            args=cmd, returncode=returncode, stdout=stdout, stderr=""
        )

    return runner


# ---------------------------------------------------------------------------
# is_instruction_path
# ---------------------------------------------------------------------------


class TestIsInstructionPath:
    @pytest.mark.parametrize(
        "path",
        [
            "CLAUDE.md",
            "AGENTS.md",
            ".apm/instructions/master.instructions.md",
            ".apm/instructions/extra.instructions.md",
            "  CLAUDE.md  ",
        ],
    )
    def test_instruction_paths(self, path: str) -> None:
        assert gate.is_instruction_path(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "",
            "   ",
            "README.md",
            "scripts/verify_text_delta_section.py",
            ".apm/CHECKSUMS",
            "docs/CLAUDE.md",
            "CLAUDE.md.bak",
        ],
    )
    def test_non_instruction_paths(self, path: str) -> None:
        assert gate.is_instruction_path(path) is False


# ---------------------------------------------------------------------------
# resolve_base
# ---------------------------------------------------------------------------


class TestResolveBase:
    def test_explicit_base_ref_wins(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("BASE_REF", "origin/feature")
        monkeypatch.setenv("GITHUB_BASE_REF", "main")
        assert gate.resolve_base() == "origin/feature"

    def test_github_base_ref_prefixed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.delenv("BASE_REF", raising=False)
        monkeypatch.setenv("GITHUB_BASE_REF", "release")
        assert gate.resolve_base() == "origin/release"

    def test_local_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("BASE_REF", raising=False)
        monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
        assert gate.resolve_base() == "origin/main"


# ---------------------------------------------------------------------------
# changed_instruction_files
# ---------------------------------------------------------------------------


class TestChangedInstructionFiles:
    def test_filters_to_instruction_subset(self) -> None:
        stdout = (
            "scripts/foo.py\n"
            "CLAUDE.md\n"
            ".apm/instructions/master.instructions.md\n"
            "README.md\n"
        )
        changed = gate.changed_instruction_files(
            "origin/main", runner=_fake_runner(stdout)
        )
        assert changed == frozenset(
            {"CLAUDE.md", ".apm/instructions/master.instructions.md"}
        )

    def test_no_instruction_files(self) -> None:
        changed = gate.changed_instruction_files(
            "origin/main", runner=_fake_runner("scripts/foo.py\nREADME.md\n")
        )
        assert changed == frozenset()

    def test_git_failure_raises(self) -> None:
        with pytest.raises(subprocess.CalledProcessError):
            gate.changed_instruction_files(
                "origin/main", runner=_fake_runner("", returncode=128)
            )


# ---------------------------------------------------------------------------
# section_errors / evaluate
# ---------------------------------------------------------------------------

_WELL_FORMED = (
    "- chars: +20\n"
    "- Added context: broadened scope to every output sink.\n"
    "- Removed context: folded a standalone sentence (concept relocated).\n"
)


class TestSectionErrors:
    @pytest.mark.parametrize(
        "section",
        [
            _WELL_FORMED,
            "chars -3; Added context: x; Removed context: y",
            "char count = +5\nAdded context none\nRemoved context none",
        ],
    )
    def test_well_formed(self, section: str) -> None:
        assert gate.section_errors(section) == []

    def test_missing_char_delta(self) -> None:
        section = "Added context: x\nRemoved context: y\n"
        errors = gate.section_errors(section)
        assert any("character-count" in e for e in errors)
        assert len(errors) == 1

    def test_missing_added_and_removed(self) -> None:
        section = "- chars: +20\n"
        errors = gate.section_errors(section)
        assert len(errors) == 2
        assert any("Added context" in e for e in errors)
        assert any("Removed context" in e for e in errors)


class TestEvaluate:
    def test_no_instruction_change_passes(self) -> None:
        code, errors = gate.evaluate(frozenset(), "anything")
        assert code == 0
        assert errors == []

    def test_instruction_change_without_section_fails(self) -> None:
        body = "## Summary\n\nsome change\n"
        code, errors = gate.evaluate(frozenset({"CLAUDE.md"}), body)
        assert code == 1
        assert any("no '## Text delta' section" in e for e in errors)

    def test_instruction_change_with_section_passes(self) -> None:
        body = f"## Summary\n\n## Text delta\n\n{_WELL_FORMED}\n## Verification\n"
        code, errors = gate.evaluate(frozenset({"AGENTS.md"}), body)
        assert code == 0
        assert errors == []

    def test_instruction_change_with_malformed_section_fails(self) -> None:
        body = "## Text delta\n\n- chars: +20\n\n## Verification\n"
        code, errors = gate.evaluate(
            frozenset({".apm/instructions/master.instructions.md"}), body
        )
        assert code == 1
        assert any("Added context" in e for e in errors)


# ---------------------------------------------------------------------------
# CLI contract (main)
# ---------------------------------------------------------------------------


class TestMainCLI:
    def test_body_file_path_passes_when_well_formed(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        monkeypatch.setattr(
            gate,
            "changed_instruction_files",
            lambda base, head="HEAD", **kw: frozenset({"CLAUDE.md"}),
        )
        body_file = tmp_path / "body.md"
        body_file.write_text(
            f"## Text delta\n\n{_WELL_FORMED}\n## Verification\n",
            encoding="utf-8",
        )
        assert (
            gate.main(
                ["verify", "--base-ref", "origin/main", "--body-file", str(body_file)]
            )
            == 0
        )

    def test_pr_body_env_fallback_fails_without_section(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            gate,
            "changed_instruction_files",
            lambda base, head="HEAD", **kw: frozenset({"CLAUDE.md"}),
        )
        monkeypatch.delenv("BODY_POLICY_CUTOFF", raising=False)
        monkeypatch.setenv("PR_BODY", "## Summary\n\nno delta section\n")
        assert gate.main(["verify", "--base-ref", "origin/main"]) == 1

    def test_cutoff_skips_back_catalog(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # created_at strictly before cutoff -> skip even though an
        # instruction file changed and the body has no section.
        called = False

        def _should_not_run(*args: Any, **kwargs: Any) -> frozenset[str]:
            nonlocal called
            called = True
            return frozenset({"CLAUDE.md"})

        monkeypatch.setattr(gate, "changed_instruction_files", _should_not_run)
        monkeypatch.setenv("PR_BODY", "no section")
        code = gate.main(
            [
                "verify",
                "--created-at",
                "2026-05-01T00:00:00Z",
                "--cutoff",
                "2026-05-26T00:00:00Z",
            ]
        )
        assert code == 0
        assert called is False

    def test_non_instruction_pr_passes(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            gate,
            "changed_instruction_files",
            lambda base, head="HEAD", **kw: frozenset(),
        )
        monkeypatch.setenv("PR_BODY", "## Summary\n\nscript-only change\n")
        assert gate.main(["verify", "--base-ref", "origin/main"]) == 0
