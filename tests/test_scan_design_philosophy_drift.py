"""Tests for ``scripts/scan_design_philosophy_drift.py``.

The ``scripts/`` directory is added to ``sys.path`` via the
``pythonpath`` key under ``[tool.pytest.ini_options]`` in
``pyproject.toml``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_design_philosophy_drift as sdpd

REPO_ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _master(n: int) -> str:
    """Return a minimal master.instructions.md body with N sections."""
    sections: list[str] = ["# Agent Instructions", ""]
    for i in range(1, n + 1):
        sections.extend([f"## {i}. Principle {i}", "", f"body for section {i}.", ""])
    return "\n".join(sections)


def _doc(matrix_rows: int, wording_count: int | None) -> str:
    """Return a minimal design-philosophy doc body.

    matrix_rows = number of ``P<n>`` rows in Section 3.
    wording_count = the integer expressed by the free-text 'N principles'
    phrase that the doc carries near the top of Section 3, or ``None``
    to omit the phrase entirely.
    """
    lines: list[str] = [
        "# Design Philosophy",
        "",
        "## 1. Purpose",
        "",
        "Some prose.",
        "",
        "## 2. Vocabulary",
        "",
        "Some prose.",
        "",
        "## 3. Responsibility matrix",
        "",
    ]
    if wording_count is not None:
        words = {
            1: "one",
            2: "two",
            3: "three",
            4: "four",
            5: "five",
            6: "six",
            7: "seven",
            8: "eight",
        }
        word = words.get(wording_count, str(wording_count))
        lines.append(f"This matrix encodes {word} principles by four lanes.")
        lines.append("")
    lines.append("| Layer | Universal | Harness | Doc | Project | Risk |")
    lines.append("|---|---|---|---|---|---|")
    for i in range(1, matrix_rows + 1):
        lines.append(
            f"| P{i} - row label | universal | harness | doc | project | risk |"
        )
    lines.extend(["", "## 4. Decision tree", "", "Some prose."])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# parse_master_sections
# ---------------------------------------------------------------------------


class TestParseMasterSections:
    def test_returns_section_numbers(self) -> None:
        assert sdpd.parse_master_sections(_master(8)) == {1, 2, 3, 4, 5, 6, 7, 8}

    def test_ignores_non_top_level_headings(self) -> None:
        text = "## 1. A\n### 2. nested heading\n## 2. B\n"
        assert sdpd.parse_master_sections(text) == {1, 2}

    def test_empty_source_yields_empty_set(self) -> None:
        assert sdpd.parse_master_sections("") == set()


# ---------------------------------------------------------------------------
# extract_section_3 and parse_doc_matrix_rows
# ---------------------------------------------------------------------------


class TestExtractSection3:
    def test_returns_lines_and_offset(self) -> None:
        doc = _doc(matrix_rows=2, wording_count=2)
        lines, offset = sdpd.extract_section_3(doc)
        assert offset >= 1
        assert any("## 3." in line for line in lines)
        assert not any(line.startswith("## 4.") for line in lines)

    def test_missing_section_3_returns_empty(self) -> None:
        doc = "# x\n## 1. A\n## 2. B\n"
        lines, offset = sdpd.extract_section_3(doc)
        assert lines == []
        assert offset == 0

    def test_section_3_at_eof(self) -> None:
        doc = "# x\n## 3. Matrix\n| P1 - a | x |\n"
        lines, _ = sdpd.extract_section_3(doc)
        assert any("P1 -" in line for line in lines)


class TestParseDocMatrixRows:
    def test_extracts_p_rows(self) -> None:
        doc = _doc(matrix_rows=3, wording_count=3)
        lines, _ = sdpd.extract_section_3(doc)
        assert sdpd.parse_doc_matrix_rows(lines) == {1, 2, 3}

    def test_skips_table_header_and_separator(self) -> None:
        section = [
            "## 3. Matrix",
            "| Layer | Universal |",
            "|---|---|",
            "| P1 - a | b |",
        ]
        assert sdpd.parse_doc_matrix_rows(section) == {1}


# ---------------------------------------------------------------------------
# parse_doc_wording_counts
# ---------------------------------------------------------------------------


class TestWordingCounts:
    def test_finds_word_count(self) -> None:
        hits = sdpd.parse_doc_wording_counts("the eight principles guide us")
        assert hits == [(1, "eight principles", 8)]

    def test_finds_digit_count(self) -> None:
        hits = sdpd.parse_doc_wording_counts("there are 12 principles total")
        assert hits == [(1, "12 principles", 12)]

    def test_case_insensitive(self) -> None:
        hits = sdpd.parse_doc_wording_counts("Six LAYERS by four lanes")
        assert hits == [(1, "Six LAYERS", 6)]

    def test_no_match_when_phrase_absent(self) -> None:
        assert sdpd.parse_doc_wording_counts("no count here") == []

    def test_reports_line_numbers_1_based(self) -> None:
        text = "line one\nthe six principles\n"
        hits = sdpd.parse_doc_wording_counts(text)
        assert hits == [(2, "six principles", 6)]


# ---------------------------------------------------------------------------
# main / verify (integration)
# ---------------------------------------------------------------------------


class TestVerifySuccess:
    def test_aligned_master_and_doc_returns_zero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        master = tmp_path / "master.md"
        doc = tmp_path / "doc.md"
        _write(master, _master(8))
        _write(doc, _doc(matrix_rows=8, wording_count=8))
        rc = sdpd.main(["verify", "--master", str(master), "--doc", str(doc)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "OK" in out
        assert "8 principles" in out

    def test_aligned_six_principle_baseline(self, tmp_path: Path) -> None:
        master = tmp_path / "master.md"
        doc = tmp_path / "doc.md"
        _write(master, _master(6))
        _write(doc, _doc(matrix_rows=6, wording_count=6))
        assert sdpd.main(
            ["verify", "--master", str(master), "--doc", str(doc)]
        ) == 0


class TestVerifyFailureModes:
    def test_missing_matrix_row(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        master = tmp_path / "master.md"
        doc = tmp_path / "doc.md"
        _write(master, _master(8))
        _write(doc, _doc(matrix_rows=6, wording_count=6))
        rc = sdpd.main(["verify", "--master", str(master), "--doc", str(doc)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "P7" in err and "P8" in err
        assert "missing rows" in err

    def test_extra_matrix_row(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        master = tmp_path / "master.md"
        doc = tmp_path / "doc.md"
        _write(master, _master(6))
        _write(doc, _doc(matrix_rows=8, wording_count=8))
        rc = sdpd.main(["verify", "--master", str(master), "--doc", str(doc)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "P7" in err and "P8" in err
        assert "no corresponding" in err

    def test_wording_count_mismatch(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        master = tmp_path / "master.md"
        doc = tmp_path / "doc.md"
        _write(master, _master(8))
        _write(doc, _doc(matrix_rows=8, wording_count=6))
        rc = sdpd.main(["verify", "--master", str(master), "--doc", str(doc)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "six principles" in err
        assert "implies 6" in err and "8" in err

    def test_missing_section_3(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        master = tmp_path / "master.md"
        doc = tmp_path / "doc.md"
        _write(master, _master(8))
        _write(doc, "# Design\n## 1. Foo\n## 2. Bar\n")
        rc = sdpd.main(["verify", "--master", str(master), "--doc", str(doc)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "Section 3 heading" in err

    def test_missing_master_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        doc = tmp_path / "doc.md"
        _write(doc, _doc(matrix_rows=8, wording_count=8))
        rc = sdpd.main(
            [
                "verify",
                "--master",
                str(tmp_path / "missing.md"),
                "--doc",
                str(doc),
            ]
        )
        assert rc == 1
        assert "missing master file" in capsys.readouterr().err

    def test_missing_doc_file(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        master = tmp_path / "master.md"
        _write(master, _master(8))
        rc = sdpd.main(
            [
                "verify",
                "--master",
                str(master),
                "--doc",
                str(tmp_path / "missing.md"),
            ]
        )
        assert rc == 1
        assert "missing doc file" in capsys.readouterr().err

    def test_master_with_no_sections(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        master = tmp_path / "master.md"
        doc = tmp_path / "doc.md"
        _write(master, "no numbered sections\nat all\n")
        _write(doc, _doc(matrix_rows=8, wording_count=8))
        rc = sdpd.main(["verify", "--master", str(master), "--doc", str(doc)])
        assert rc == 1
        assert "no numbered sections detected" in capsys.readouterr().err

    def test_master_with_non_contiguous_sections(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        master = tmp_path / "master.md"
        doc = tmp_path / "doc.md"
        _write(master, "## 1. A\n## 3. C\n")
        _write(doc, _doc(matrix_rows=3, wording_count=3))
        rc = sdpd.main(["verify", "--master", str(master), "--doc", str(doc)])
        assert rc == 1
        assert "non-contiguous" in capsys.readouterr().err


# ---------------------------------------------------------------------------
# report subcommand
# ---------------------------------------------------------------------------


class TestReport:
    def test_report_prints_sets(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        master = tmp_path / "master.md"
        doc = tmp_path / "doc.md"
        _write(master, _master(8))
        _write(doc, _doc(matrix_rows=6, wording_count=6))
        rc = sdpd.main(["report", "--master", str(master), "--doc", str(doc)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "master sections" in out
        assert "missing in doc:  [7, 8]" in out

    def test_report_missing_file_returns_1(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        rc = sdpd.main(
            [
                "report",
                "--master",
                str(tmp_path / "missing.md"),
                "--doc",
                str(tmp_path / "also-missing.md"),
            ]
        )
        assert rc == 1


# ---------------------------------------------------------------------------
# Repository self-check: the live files must already be in sync.
# ---------------------------------------------------------------------------


class TestRepositorySelfCheck:
    def test_repository_state_is_clean(self) -> None:
        master = REPO_ROOT / ".apm" / "instructions" / "master.instructions.md"
        doc = REPO_ROOT / "docs" / "agent-rules-design-philosophy.md"
        assert master.exists()
        assert doc.exists()
        rc = sdpd.main(["verify", "--master", str(master), "--doc", str(doc)])
        assert rc == 0
