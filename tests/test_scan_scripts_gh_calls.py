"""Tests for ``scripts/scan_scripts_gh_calls.py``.

The ``scripts/`` directory is added to ``sys.path`` via the ``pythonpath``
key under ``[tool.pytest.ini_options]`` in ``pyproject.toml``.

Covers #909: the deterministic gate that fails when a new direct ``gh`` CLI
subprocess call is added to ``scripts/*.py``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_scripts_gh_calls as gate

pytestmark = pytest.mark.shard_ci_ops

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write(scripts_dir: Path, name: str, source: str) -> None:
    (scripts_dir / name).write_text(source, encoding="utf-8")


class TestFindViolations:
    def test_argv_list_literal_is_flagged(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "bad.py",
            'import subprocess\n'
            'subprocess.run(["gh", "api", "/repos/o/r/issues/1"], check=True)\n',
        )
        violations = gate.find_violations(tmp_path)
        assert [v.script for v in violations] == ["bad.py"]
        assert "argv literal" in violations[0].fragment

    def test_string_command_is_flagged(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "bad.py",
            'import subprocess\n'
            'subprocess.run("gh pr list --json number", shell=True)\n',
        )
        violations = gate.find_violations(tmp_path)
        assert [v.script for v in violations] == ["bad.py"]
        assert "command string" in violations[0].fragment

    def test_docstring_mention_is_not_flagged(self, tmp_path: Path) -> None:
        # A module docstring describing an operator's manual `gh api` step must
        # NOT trip the gate; only executable calls do.
        _write(
            tmp_path,
            "ok.py",
            '"""Run ``gh api repos/o/r`` then process the JSON offline."""\n'
            "VALUE = 1\n",
        )
        assert gate.find_violations(tmp_path) == []

    def test_comment_mention_is_not_flagged(self, tmp_path: Path) -> None:
        _write(tmp_path, "ok.py", "# replicate gh issue close behaviour\nX = 1\n")
        assert gate.find_violations(tmp_path) == []

    def test_rest_helper_usage_is_not_flagged(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "ok.py",
            "from _github_api import rest_json\n"
            'rest_json("GET", "/repos/o/r/issues/1", token="t")\n',
        )
        assert gate.find_violations(tmp_path) == []

    def test_non_gh_argv_is_not_flagged(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "ok.py",
            'import subprocess\nsubprocess.run(["git", "status"], check=True)\n',
        )
        assert gate.find_violations(tmp_path) == []

    def test_unparseable_file_is_skipped(self, tmp_path: Path) -> None:
        _write(tmp_path, "broken.py", "def (((\n")
        assert gate.find_violations(tmp_path) == []

    def test_multiple_violations_reported(self, tmp_path: Path) -> None:
        _write(
            tmp_path,
            "bad.py",
            "import subprocess\n"
            'subprocess.run(["gh", "api", "/a"])\n'
            'subprocess.run(["gh", "issue", "list"])\n',
        )
        assert len(gate.find_violations(tmp_path)) == 2


class TestRealRepo:
    def test_repo_scripts_have_no_direct_gh_calls(self) -> None:
        """The checked-in scripts/ tree must pass the gate end-to-end (#909)."""
        violations = gate.find_violations(REPO_ROOT / "scripts")
        assert violations == [], "\n".join(
            f"scripts/{v.script}:{v.line}: {v.fragment}" for v in violations
        )


class TestCLI:
    def test_verify_clean_tree_exits_zero(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        _write(tmp_path, "ok.py", "X = 1\n")
        monkeypatch.setattr(gate, "SCRIPTS_DIR", tmp_path)
        assert gate.main(["verify"]) == 0

    def test_verify_dirty_tree_exits_one(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write(tmp_path, "bad.py", 'import subprocess\nsubprocess.run(["gh", "api"])\n')
        monkeypatch.setattr(gate, "SCRIPTS_DIR", tmp_path)
        assert gate.main(["verify"]) == 1
        assert "::error" in capsys.readouterr().err

    def test_list_prints_matches(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        _write(tmp_path, "bad.py", 'import subprocess\nsubprocess.run(["gh", "api"])\n')
        monkeypatch.setattr(gate, "SCRIPTS_DIR", tmp_path)
        assert gate.main(["list"]) == 0
        out = capsys.readouterr().out
        assert "VIOLATION" in out
        assert "bad.py" in out
