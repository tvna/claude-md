"""Tests for ``scripts/scan_repo_double_hyphen.py``.

The ``scripts/`` directory is added to ``sys.path`` via the
``pythonpath`` key under ``[tool.pytest.ini_options]`` in
``pyproject.toml``. Double-hyphen fixtures use the literal string
``" -- "`` since it is plain ASCII and not flagged by the gate being
tested; unlike the em-dash gate, this gate detects ASCII sequences.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import scan_repo_double_hyphen as srdh

pytestmark = pytest.mark.shard_default
REPO_ROOT = Path(__file__).resolve().parents[1]

_DH = " -- "  # the prose separator pattern under test


# ---------------------------------------------------------------------------
# _should_skip_line
# ---------------------------------------------------------------------------


class TestShouldSkipLine:
    def test_plain_prose_not_skipped(self) -> None:
        assert not srdh._should_skip_line("this sentence has a separator here")

    def test_noqa_line_skipped(self) -> None:
        assert srdh._should_skip_line(
            "subprocess.run(  # noqa: S603 -- fixed argv, shell=False"
        )

    def test_noqa_line_any_code_skipped(self) -> None:
        assert srdh._should_skip_line("import os  # noqa: F401 -- used elsewhere")

    def test_dh_ok_marker_skipped(self) -> None:
        assert srdh._should_skip_line(
            'assert func("git push origin -- feat/x") == "feat/x"  # dh-ok: git end-of-options'
        )

    def test_markdown_table_row_skipped(self) -> None:
        assert srdh._should_skip_line("| col1 | col2 -- col3 |")

    def test_markdown_table_row_with_leading_spaces_skipped(self) -> None:
        assert srdh._should_skip_line("  | indented | table -- row |")

    def test_empty_line_not_skipped(self) -> None:
        assert not srdh._should_skip_line("")

    def test_line_with_pipe_in_middle_not_skipped(self) -> None:
        # A pipe that is not the first non-whitespace char is not a table row
        assert not srdh._should_skip_line("code | value -- reason")


# ---------------------------------------------------------------------------
# scan_text
# ---------------------------------------------------------------------------


class TestScanText:
    def test_pure_ascii_is_clean(self) -> None:
        assert srdh.scan_text("hello; world\n") == []

    def test_empty_is_clean(self) -> None:
        assert srdh.scan_text("") == []

    def test_single_hyphen_is_clean(self) -> None:
        assert srdh.scan_text("word - other\n") == []

    def test_double_hyphen_no_spaces_is_clean(self) -> None:
        # --flag style (no surrounding spaces) must not be flagged
        assert srdh.scan_text("python3 script.py --git-tracked\n") == []

    def test_double_hyphen_prose_flagged(self) -> None:
        text = f"word{_DH}other\n"
        assert srdh.scan_text(text) == [(1, 5)]

    def test_double_hyphen_on_second_line(self) -> None:
        text = f"clean line\nsecond{_DH}line\n"
        # "second" is 6 chars, so " -- " starts at column 7
        assert srdh.scan_text(text) == [(2, 7)]

    def test_multiple_occurrences_same_line(self) -> None:
        text = f"a{_DH}b{_DH}c\n"
        assert srdh.scan_text(text) == [(1, 2), (1, 7)]

    def test_noqa_line_skipped(self) -> None:
        text = f"cmd  # noqa: S603{_DH}reason\n"
        assert srdh.scan_text(text) == []

    def test_markdown_table_row_skipped(self) -> None:
        text = f"| cell1{_DH}cell2 |\n"
        assert srdh.scan_text(text) == []

    def test_mixed_lines_only_prose_flagged(self) -> None:
        text = (
            f"prose{_DH}word\n"
            f"| table{_DH}row |\n"
            f"cmd  # noqa: S603{_DH}reason\n"
            "clean line\n"
        )
        assert srdh.scan_text(text) == [(1, 6)]

    def test_newline_advances_line_counter(self) -> None:
        lines = ["a\n", "b\n", f"c{_DH}d\n"]
        text = "".join(lines)
        assert srdh.scan_text(text) == [(3, 2)]


# ---------------------------------------------------------------------------
# scan_file
# ---------------------------------------------------------------------------


class TestScanFile:
    def test_clean_file(self, tmp_path: Path) -> None:
        p = tmp_path / "clean.md"
        p.write_text("No prose separator here; only semicolons.\n", encoding="utf-8")
        assert srdh.scan_file(p) == []

    def test_file_with_double_hyphen(self, tmp_path: Path) -> None:
        p = tmp_path / "dirty.py"
        p.write_text(f"# comment{_DH}reason\n", encoding="utf-8")
        assert srdh.scan_file(p) == [(1, 10)]

    def test_binary_file_skipped(self, tmp_path: Path) -> None:
        p = tmp_path / "binary.bin"
        p.write_bytes(b"\xff\xfe\x00invalid utf-8")
        result = srdh.scan_file(p)
        assert result == []

    def test_missing_file_returns_empty(self, tmp_path: Path) -> None:
        p = tmp_path / "nonexistent.txt"
        result = srdh.scan_file(p)
        assert result == []


# ---------------------------------------------------------------------------
# _git_tracked_files
# ---------------------------------------------------------------------------


class TestGitTrackedFiles:
    def test_returns_path_list_on_success(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "CLAUDE.md\nREADME.md\n"
        with patch("subprocess.run", return_value=mock_result):
            result = srdh._git_tracked_files()
        assert result == [Path("CLAUDE.md"), Path("README.md")]

    def test_returns_none_on_git_failure(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "not a git repo"
        with patch("subprocess.run", return_value=mock_result):
            result = srdh._git_tracked_files()
        assert result is None
        captured = capsys.readouterr()
        assert "git ls-files failed" in captured.err

    def test_skips_empty_lines(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "a.md\n\nb.md\n"
        with patch("subprocess.run", return_value=mock_result):
            result = srdh._git_tracked_files()
        assert result == [Path("a.md"), Path("b.md")]

    def test_excludes_agents_skills_prefix(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "CLAUDE.md\n"
            ".agents/skills/brainstorming/SKILL.md\n"
            "README.md\n"
        )
        with patch("subprocess.run", return_value=mock_result):
            result = srdh._git_tracked_files()
        assert result is not None
        paths = [str(p) for p in result]
        assert "CLAUDE.md" in paths
        assert "README.md" in paths
        assert ".agents/skills/brainstorming/SKILL.md" not in paths

    def test_excludes_docs_archive_prefix(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "CLAUDE.md\ndocs/archive/old.md\nREADME.md\n"
        with patch("subprocess.run", return_value=mock_result):
            result = srdh._git_tracked_files()
        assert result is not None
        paths = [str(p) for p in result]
        assert "docs/archive/old.md" not in paths
        assert "CLAUDE.md" in paths

    def test_excludes_docs_generated_prefix(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "CLAUDE.md\ndocs/generated/script.md\nREADME.md\n"
        with patch("subprocess.run", return_value=mock_result):
            result = srdh._git_tracked_files()
        assert result is not None
        paths = [str(p) for p in result]
        assert "docs/generated/script.md" not in paths

    def test_excludes_yml_extension(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "CLAUDE.md\n.github/workflows/verify-pr.yml\nREADME.md\n"
        with patch("subprocess.run", return_value=mock_result):
            result = srdh._git_tracked_files()
        assert result is not None
        paths = [str(p) for p in result]
        assert ".github/workflows/verify-pr.yml" not in paths
        assert "CLAUDE.md" in paths

    def test_excludes_yaml_extension(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "CLAUDE.md\nconfig.yaml\n"
        with patch("subprocess.run", return_value=mock_result):
            result = srdh._git_tracked_files()
        assert result is not None
        paths = [str(p) for p in result]
        assert "config.yaml" not in paths

    def test_excludes_sh_extension(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "CLAUDE.md\nscripts/install.sh\n"
        with patch("subprocess.run", return_value=mock_result):
            result = srdh._git_tracked_files()
        assert result is not None
        paths = [str(p) for p in result]
        assert "scripts/install.sh" not in paths

    def test_excludes_json_extension(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "CLAUDE.md\ndata.json\n"
        with patch("subprocess.run", return_value=mock_result):
            result = srdh._git_tracked_files()
        assert result is not None
        paths = [str(p) for p in result]
        assert "data.json" not in paths

    def test_excludes_toml_extension(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "CLAUDE.md\npyproject.toml\n"
        with patch("subprocess.run", return_value=mock_result):
            result = srdh._git_tracked_files()
        assert result is not None
        paths = [str(p) for p in result]
        assert "pyproject.toml" not in paths

    def test_excludes_lock_extension(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "CLAUDE.md\nuv.lock\n"
        with patch("subprocess.run", return_value=mock_result):
            result = srdh._git_tracked_files()
        assert result is not None
        paths = [str(p) for p in result]
        assert "uv.lock" not in paths

    def test_excludes_sql_extension(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "CLAUDE.md\nschema.sql\n"
        with patch("subprocess.run", return_value=mock_result):
            result = srdh._git_tracked_files()
        assert result is not None
        paths = [str(p) for p in result]
        assert "schema.sql" not in paths


# ---------------------------------------------------------------------------
# _verify / _cmd_verify
# ---------------------------------------------------------------------------


class TestVerify:
    def test_clean_files_exit_0(self, tmp_path: Path) -> None:
        p = tmp_path / "ok.md"
        p.write_text("no prose separator here; semicolon is fine\n", encoding="utf-8")
        assert srdh._verify([p]) == 0

    def test_dirty_file_exit_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = tmp_path / "bad.md"
        p.write_text(f"word{_DH}word\n", encoding="utf-8")
        result = srdh._verify([p])
        assert result == 1
        captured = capsys.readouterr()
        assert "double-hyphen" in captured.err
        assert "FAIL: 1" in captured.err

    def test_multiple_violations_counted(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = tmp_path / "multi.py"
        p.write_text(f"x{_DH}y\nx{_DH}y\nx{_DH}y\n", encoding="utf-8")
        result = srdh._verify([p])
        assert result == 1
        captured = capsys.readouterr()
        assert "FAIL: 3" in captured.err

    def test_directories_skipped(self, tmp_path: Path) -> None:
        result = srdh._verify([tmp_path])
        assert result == 0

    def test_deduplication(self, tmp_path: Path) -> None:
        p = tmp_path / "ok.md"
        p.write_text("clean\n", encoding="utf-8")
        result = srdh._verify([p, p])
        assert result == 0

    def test_noqa_line_not_counted(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = tmp_path / "noqa.py"
        p.write_text(
            f"cmd  # noqa: S603{_DH}reason\n",
            encoding="utf-8",
        )
        result = srdh._verify([p])
        assert result == 0

    def test_table_row_not_counted(self, tmp_path: Path) -> None:
        p = tmp_path / "table.md"
        p.write_text(f"| col1{_DH}col2 |\n", encoding="utf-8")
        result = srdh._verify([p])
        assert result == 0


class TestCmdVerify:
    def test_no_args_returns_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = srdh.main(["verify"])
        assert result == 2
        assert "supply" in capsys.readouterr().err

    def test_explicit_path_clean(self, tmp_path: Path) -> None:
        p = tmp_path / "ok.py"
        p.write_text("# no prose separator\n", encoding="utf-8")
        result = srdh.main(["verify", "--path", str(p)])
        assert result == 0

    def test_explicit_path_dirty(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        p = tmp_path / "bad.py"
        p.write_text(f"# comment{_DH}reason\n", encoding="utf-8")
        result = srdh.main(["verify", "--path", str(p)])
        assert result == 1

    def test_git_tracked_calls_git_ls_files(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            srdh.main(["verify", "--git-tracked"])
        call_args = mock_run.call_args
        assert call_args[0][0] == ["git", "ls-files"]

    def test_git_tracked_exits_1_when_git_fails(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "fatal: not a git repository"
        with patch("subprocess.run", return_value=mock_result):
            result = srdh.main(["verify", "--git-tracked"])
        assert result == 1
        assert "git ls-files failed" in capsys.readouterr().err

    def test_path_and_git_tracked_combined(self, tmp_path: Path) -> None:
        p = tmp_path / "extra.md"
        p.write_text("clean\n", encoding="utf-8")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            result = srdh.main(["verify", "--git-tracked", "--path", str(p)])
        assert result == 0


# ---------------------------------------------------------------------------
# End-to-end regression guard: the live repo tree must be clean
# ---------------------------------------------------------------------------


class TestLiveRepoClean:
    """Regression guard: verify-pr CI gate will fail on any double-hyphen regression.

    This test exercises the actual ``git ls-files`` path against the real
    working tree, proving the repo is currently clean. It will fail whenever
    a commit introduces ` -- ` into any tracked prose file, providing the
    earliest possible feedback. Refs #1903.
    """

    def test_repo_tree_has_no_prose_double_hyphen(self) -> None:
        result = srdh.main(["verify", "--git-tracked"])
        assert result == 0, (
            "Prose ` -- ` separator found in tracked files. "
            "Run: python3 scripts/scan_repo_double_hyphen.py verify --git-tracked"
        )
