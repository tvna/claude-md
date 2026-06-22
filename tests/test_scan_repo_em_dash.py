"""Tests for ``scripts/scan_repo_em_dash.py``.

The ``scripts/`` directory is added to ``sys.path`` via the
``pythonpath`` key under ``[tool.pytest.ini_options]`` in
``pyproject.toml``. Em-dash fixtures use ``"\\u2014"`` escape so this
test file itself stays ASCII-clean and is not flagged by the gate it
tests.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import scan_repo_em_dash as srd

pytestmark = pytest.mark.shard_default
REPO_ROOT = Path(__file__).resolve().parents[1]

_EM_DASH = "\u2014"  # U+2014 EM DASH


# ---------------------------------------------------------------------------
# scan_text
# ---------------------------------------------------------------------------


class TestScanText:
    def test_pure_ascii_is_clean(self) -> None:
        assert srd.scan_text("hello -- world\n") == []

    def test_empty_is_clean(self) -> None:
        assert srd.scan_text("") == []

    def test_double_hyphen_is_clean(self) -> None:
        assert srd.scan_text("*Layer: goal -- desc.*\n") == []

    def test_em_dash_flagged_line_and_column(self) -> None:
        text = f"ab{_EM_DASH}cd\n"
        assert srd.scan_text(text) == [(1, 3)]

    def test_em_dash_on_second_line(self) -> None:
        text = f"clean line\nsecond {_EM_DASH} line\n"
        # "second " is 7 chars, so em-dash is at column 8
        assert srd.scan_text(text) == [(2, 8)]

    def test_multiple_em_dashes_same_line(self) -> None:
        text = f"{_EM_DASH}a{_EM_DASH}\n"
        assert srd.scan_text(text) == [(1, 1), (1, 3)]

    def test_em_dash_only_flag_not_other_non_ascii(self) -> None:
        # Section sign (U+00A7) must not be flagged
        text = "§2 applies\n"
        assert srd.scan_text(text) == []

    def test_newline_advances_line_counter(self) -> None:
        lines = ["a\n", "b\n", f"{_EM_DASH}\n"]
        text = "".join(lines)
        assert srd.scan_text(text) == [(3, 1)]


# ---------------------------------------------------------------------------
# scan_file
# ---------------------------------------------------------------------------


class TestScanFile:
    def test_clean_file(self, tmp_path: Path) -> None:
        p = tmp_path / "clean.md"
        p.write_text("No em-dash here -- ASCII only.\n", encoding="utf-8")
        assert srd.scan_file(p) == []

    def test_file_with_em_dash(self, tmp_path: Path) -> None:
        p = tmp_path / "dirty.py"
        p.write_bytes(b"# comment " + _EM_DASH.encode("utf-8") + b" reason\n")
        assert srd.scan_file(p) == [(1, 11)]

    def test_binary_file_skipped(self, tmp_path: Path) -> None:
        p = tmp_path / "binary.bin"
        p.write_bytes(b"\xff\xfe\x00invalid utf-8")
        # Should return empty list, not raise
        result = srd.scan_file(p)
        assert result == []

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        p = tmp_path / "nonexistent.txt"
        # scan_file reads the file; missing file raises OSError, caught internally
        result = srd.scan_file(p)
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
            result = srd._git_tracked_files()
        assert result == [Path("CLAUDE.md"), Path("README.md")]

    def test_returns_none_on_git_failure(self, capsys: pytest.CaptureFixture[str]) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "not a git repo"
        with patch("subprocess.run", return_value=mock_result):
            result = srd._git_tracked_files()
        assert result is None
        captured = capsys.readouterr()
        assert "git ls-files failed" in captured.err

    def test_skips_empty_lines(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = "a.md\n\nb.md\n"
        with patch("subprocess.run", return_value=mock_result):
            result = srd._git_tracked_files()
        assert result == [Path("a.md"), Path("b.md")]

    def test_excludes_agents_skills_prefix(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = (
            "CLAUDE.md\n"
            ".agents/skills/brainstorming/SKILL.md\n"
            ".agents/skills/writing-plans/SKILL.md\n"
            "README.md\n"
        )
        with patch("subprocess.run", return_value=mock_result):
            result = srd._git_tracked_files()
        paths = [str(p) for p in result]
        assert "CLAUDE.md" in paths
        assert "README.md" in paths
        assert ".agents/skills/brainstorming/SKILL.md" not in paths
        assert ".agents/skills/writing-plans/SKILL.md" not in paths


# ---------------------------------------------------------------------------
# _verify / _cmd_verify
# ---------------------------------------------------------------------------


class TestVerify:
    def test_clean_files_exit_0(self, tmp_path: Path) -> None:
        p = tmp_path / "ok.md"
        p.write_text("no em-dash here\n", encoding="utf-8")
        assert srd._verify([p]) == 0

    def test_dirty_file_exit_1(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = tmp_path / "bad.md"
        p.write_bytes(b"word " + _EM_DASH.encode("utf-8") + b" word\n")
        result = srd._verify([p])
        assert result == 1
        captured = capsys.readouterr()
        assert "em-dash" in captured.err
        assert "FAIL: 1" in captured.err

    def test_multiple_violations_counted(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = tmp_path / "multi.py"
        line = ("x" + _EM_DASH + "y\n").encode("utf-8")
        p.write_bytes(line * 3)
        result = srd._verify([p])
        assert result == 1
        captured = capsys.readouterr()
        assert "FAIL: 3" in captured.err

    def test_directories_skipped(self, tmp_path: Path) -> None:
        # A Path that is a directory should not cause a crash
        result = srd._verify([tmp_path])
        assert result == 0

    def test_deduplication(self, tmp_path: Path) -> None:
        p = tmp_path / "ok.md"
        p.write_text("clean\n", encoding="utf-8")
        # Same path repeated twice -- should only scan once
        result = srd._verify([p, p])
        assert result == 0


class TestCmdVerify:
    def test_no_args_returns_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        result = srd.main(["verify"])
        assert result == 2
        assert "supply" in capsys.readouterr().err

    def test_explicit_path_clean(self, tmp_path: Path) -> None:
        p = tmp_path / "ok.py"
        p.write_text("# no em-dash\n", encoding="utf-8")
        result = srd.main(["verify", "--path", str(p)])
        assert result == 0

    def test_explicit_path_dirty(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        p = tmp_path / "bad.py"
        p.write_bytes(b"# " + _EM_DASH.encode("utf-8") + b" reason\n")
        result = srd.main(["verify", "--path", str(p)])
        assert result == 1

    def test_git_tracked_calls_git_ls_files(self) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result) as mock_run:
            srd.main(["verify", "--git-tracked"])
        # subprocess.run was called with git ls-files
        call_args = mock_run.call_args
        assert call_args[0][0] == ["git", "ls-files"]

    def test_git_tracked_exits_1_when_git_fails(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        mock_result = MagicMock()
        mock_result.returncode = 1
        mock_result.stderr = "fatal: not a git repository"
        with patch("subprocess.run", return_value=mock_result):
            result = srd.main(["verify", "--git-tracked"])
        assert result == 1
        assert "git ls-files failed" in capsys.readouterr().err

    def test_path_and_git_tracked_combined(self, tmp_path: Path) -> None:
        p = tmp_path / "extra.md"
        p.write_text("clean\n", encoding="utf-8")
        mock_result = MagicMock()
        mock_result.returncode = 0
        mock_result.stdout = ""
        with patch("subprocess.run", return_value=mock_result):
            result = srd.main(["verify", "--git-tracked", "--path", str(p)])
        assert result == 0


# ---------------------------------------------------------------------------
# End-to-end regression guard: the live repo tree must be clean
# ---------------------------------------------------------------------------


class TestLiveRepoClean:
    """Regression guard: verify-pr CI gate will fail on any em-dash regression.

    This test exercises the actual ``git ls-files`` path against the real
    working tree, proving the repo is currently clean. It will fail whenever
    a commit introduces U+2014 into any tracked file, providing the earliest
    possible feedback. Refs #1889.
    """

    def test_repo_tree_has_no_em_dash(self) -> None:
        result = srd.main(["verify", "--git-tracked"])
        assert result == 0, (
            "Em-dash (U+2014) found in tracked files. "
            "Run: python3 scripts/scan_repo_em_dash.py verify --git-tracked"
        )
