"""Tests for ``scripts/scan_apm_ascii.py``.

The ``scripts/`` directory is added to ``sys.path`` via the
``pythonpath`` key under ``[tool.pytest.ini_options]`` in
``pyproject.toml``. Non-ASCII fixtures are written with ``\\u`` escapes so
this test file itself stays pure ASCII and unambiguous.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_apm_ascii as saa

pytestmark = pytest.mark.shard_default
REPO_ROOT = Path(__file__).resolve().parents[1]

_EM_DASH = "\u2014"  # EM DASH
_LEFT_DQUOTE = "\u201c"  # LEFT DOUBLE QUOTATION MARK
_LINE_SEP = "\u2028"  # LINE SEPARATOR
_SECTION = "\u00a7"  # SECTION SIGN (allowlisted)

# The artifacts the gate guards in production, scanned end to end below as
# a regression guard so the current tree is provably clean.
_ARTIFACTS = (
    ".apm/instructions/master.instructions.md",
    "CLAUDE.md",
    "AGENTS.md",
)


# ---------------------------------------------------------------------------
# scan_text
# ---------------------------------------------------------------------------


class TestScanText:
    def test_pure_ascii_is_clean(self) -> None:
        text = "Open a GitHub issue before any branch -- no exceptions.\n"
        assert saa.scan_text(text) == []

    def test_empty_text_is_clean(self) -> None:
        assert saa.scan_text("") == []

    def test_em_dash_flagged_with_line_and_column(self) -> None:
        # "ab" then em-dash at column 3 on line 1.
        text = f"ab{_EM_DASH}cd\n"
        assert saa.scan_text(text) == [(1, 3, _EM_DASH)]

    def test_allowlisted_section_sign_is_clean(self) -> None:
        text = f"{_SECTION}2 applies: failure output is the spec.\n"
        assert saa.scan_text(text) == []

    def test_line_numbers_track_newlines_only(self) -> None:
        text = f"clean line\nsecond {_EM_DASH} line\n"
        # em-dash sits at column 8 of line 2 ("second " is 7 chars).
        assert saa.scan_text(text) == [(2, 8, _EM_DASH)]

    def test_unicode_line_separator_is_flagged_not_consumed(self) -> None:
        # U+2028 LINE SEPARATOR would be swallowed by str.splitlines(); the
        # direct scan must report it instead. Only "\n" advances the line
        # counter, so it stays on line 1 at column 2.
        text = f"a{_LINE_SEP}b"
        assert saa.scan_text(text) == [(1, 2, _LINE_SEP)]

    def test_multiple_violations_reported_in_order(self) -> None:
        text = f"x{_EM_DASH}y\nz{_LEFT_DQUOTE}w\n"
        assert saa.scan_text(text) == [
            (1, 2, _EM_DASH),
            (2, 2, _LEFT_DQUOTE),
        ]


# ---------------------------------------------------------------------------
# scan_file
# ---------------------------------------------------------------------------


class TestScanFile:
    def test_clean_file(self, tmp_path: Path) -> None:
        target = tmp_path / "clean.md"
        target.write_text(f"ASCII only -- and a {_SECTION} sign.\n", encoding="utf-8")
        assert saa.scan_file(target) == []

    def test_dirty_file(self, tmp_path: Path) -> None:
        target = tmp_path / "dirty.md"
        target.write_text(f"line one\nbad {_EM_DASH} dash\n", encoding="utf-8")
        assert saa.scan_file(target) == [(2, 5, _EM_DASH)]


# ---------------------------------------------------------------------------
# main / verify
# ---------------------------------------------------------------------------


class TestMain:
    def test_no_path_returns_2(self, capsys: pytest.CaptureFixture[str]) -> None:
        assert saa.main(["verify"]) == 2
        assert "at least one --path is required" in capsys.readouterr().err

    def test_clean_path_returns_0(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        target = tmp_path / "clean.md"
        target.write_text("pure ascii\n", encoding="utf-8")
        assert saa.main(["verify", "--path", str(target)]) == 0
        assert "OK:" in capsys.readouterr().out

    def test_violation_returns_1_with_annotation(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        target = tmp_path / "dirty.md"
        target.write_text(f"bad {_EM_DASH} dash\n", encoding="utf-8")
        assert saa.main(["verify", "--path", str(target)]) == 1
        err = capsys.readouterr().err
        assert "::error file=" in err
        assert "line=1,col=5" in err
        assert "U+2014" in err

    def test_missing_path_returns_1(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        missing = tmp_path / "nope.md"
        assert saa.main(["verify", "--path", str(missing)]) == 1
        assert "missing scan target" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# Regression guard: the live artifacts must already pass.
# ---------------------------------------------------------------------------


class TestLiveArtifacts:
    @pytest.mark.parametrize("rel", _ARTIFACTS)
    def test_artifact_is_clean(self, rel: str) -> None:
        path = REPO_ROOT / rel
        assert saa.scan_file(path) == [], (
            f"{rel} carries disallowed non-ASCII; either normalize it to "
            "ASCII or extend scan_apm_ascii._ALLOWED_NON_ASCII."
        )
