"""Tests asserting that the ruff lint gate flags actionable security findings.

These tests exist to satisfy the acceptance criterion in #190:

    "The chosen check fails on actionable findings."

They do not exercise application code; they pin the configuration so a
future PR that silently drops ``S`` from ``[tool.ruff.lint] select`` will
fail this gate before merging.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest
import tomllib

REPO_ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = REPO_ROOT / "pyproject.toml"


# ---------------------------------------------------------------------------
# Configuration assertion
# ---------------------------------------------------------------------------


class TestRuffSelectIncludesSecurityFamily:
    def test_pyproject_select_contains_S(self) -> None:
        """``S`` (flake8-bandit) must be in ruff's selected rule families."""
        config = tomllib.loads(PYPROJECT.read_text(encoding="utf-8"))
        select = config["tool"]["ruff"]["lint"]["select"]
        assert "S" in select, (
            "pyproject.toml [tool.ruff.lint] select must include 'S' "
            "(flake8-bandit) so the security gate from #190 stays active."
        )


# ---------------------------------------------------------------------------
# End-to-end fail-on-actionable-finding assertion
# ---------------------------------------------------------------------------


VULNERABLE_SAMPLE = (
    "import os\n"
    "import subprocess\n"
    "\n"
    "def go(user_input: str) -> None:\n"
    "    os.system(user_input)\n"
    "    subprocess.Popen(user_input, shell=True)\n"
)


class TestRuffFailsOnActionableFinding:
    """Pipe a deliberately unsafe snippet through ``ruff check`` and assert it
    is rejected. Uses ``--select S`` to isolate the security family from any
    unrelated rules the snippet might also trigger.
    """

    def test_unsafe_subprocess_and_os_system_are_flagged(
        self, tmp_path: Path
    ) -> None:
        sample = tmp_path / "vulnerable_sample.py"
        sample.write_text(VULNERABLE_SAMPLE, encoding="utf-8")

        result = subprocess.run(
            [
                sys.executable, "-m", "ruff", "check",
                "--select", "S",
                "--no-cache",
                "--isolated",
                str(sample),
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        # ruff exits 1 when violations are found.
        assert result.returncode == 1, (
            f"expected ruff to fail with code 1 on unsafe sample, got "
            f"{result.returncode}; stdout={result.stdout!r} stderr={result.stderr!r}"
        )
        # At least one of S605 (start-process-with-shell), S602 (subprocess
        # with shell=True), or S607 (partial path) should be reported.
        flagged_codes = {"S602", "S605", "S607"}
        assert any(code in result.stdout for code in flagged_codes), (
            f"expected at least one of {sorted(flagged_codes)} in ruff output; "
            f"got: {result.stdout!r}"
        )


# ---------------------------------------------------------------------------
# Clean-source baseline
# ---------------------------------------------------------------------------


class TestRuffPassesOnRepository:
    """Smoke test: the repository's own scripts/ and tests/ trees pass
    ``ruff check`` with the S family enabled. This is the same invocation CI
    runs in verify-agents.yml lint-scripts; the test fails fast locally if a
    fixture or new code regresses.
    """

    @pytest.mark.parametrize("target", ["scripts", "tests"])
    def test_target_passes_ruff(self, target: str) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "ruff", "check", str(REPO_ROOT / target)],
            capture_output=True,
            text=True,
            check=False,
            cwd=REPO_ROOT,
        )
        assert result.returncode == 0, (
            f"ruff check {target} failed:\n"
            f"stdout={result.stdout}\nstderr={result.stderr}"
        )
