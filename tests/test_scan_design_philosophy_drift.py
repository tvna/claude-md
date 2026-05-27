"""Tests for ``scripts/scan_design_philosophy_drift.py``.

The ``scripts/`` directory is added to ``sys.path`` via the
``pythonpath`` key under ``[tool.pytest.ini_options]`` in
``pyproject.toml``.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import scan_design_philosophy_drift as sdpd

pytestmark = pytest.mark.shard_default
REPO_ROOT = Path(__file__).resolve().parents[1]


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _master(n: int, *, subtitles: dict[int, str] | None = None) -> str:
    """Return a minimal master.instructions.md body with N sections.

    Each section emits a ``*Layer: <text> -- desc.*`` subtitle by
    default (em-dash separator) so the post-#329 label-parity check
    has a subtitle to read. Pass ``subtitles={n: "..."}`` to override
    individual section subtitles; pass ``subtitles={}`` to drop them
    entirely.
    """
    pick = (
        subtitles
        if subtitles is not None
        else {i: f"principle {i}" for i in range(1, n + 1)}
    )
    sections: list[str] = ["# Agent Instructions", ""]
    for i in range(1, n + 1):
        sections.append(f"## {i}. Principle {i}")
        sections.append("")
        sub = pick.get(i)
        if sub is not None:
            sections.append(f"*Layer: {sub} — desc {i}.*")
            sections.append("")
        sections.append(f"body for section {i}.")
        sections.append("")
    return "\n".join(sections)


def _doc(
    matrix_rows: int,
    wording_count: int | None,
    *,
    row_labels: dict[int, str] | None = None,
    glossary: list[str] | None = None,
) -> str:
    """Return a minimal design-philosophy doc body.

    matrix_rows = number of ``P<n>`` rows in Section 3.
    wording_count = the integer expressed by the free-text 'N principles'
    phrase that the doc carries near the top of Section 3, or ``None``
    to omit the phrase entirely.
    row_labels = optional ``{n: label}`` map; defaults to
    ``{i: f"principle {i}"}`` so the label-parity check agrees with
    :func:`_master`'s default subtitles.
    glossary = optional list of bolded entry names to include under
    ``### 2.5 Glossary``; defaults to
    :data:`sdpd.REQUIRED_GLOSSARY_ENTRIES`. Pass ``[]`` to drop the
    section entirely.
    """
    labels = (
        row_labels
        if row_labels is not None
        else {i: f"principle {i}" for i in range(1, matrix_rows + 1)}
    )
    entries = (
        glossary
        if glossary is not None
        else list(sdpd.REQUIRED_GLOSSARY_ENTRIES)
    )
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
    ]
    if entries:
        lines.extend(["### 2.5 Glossary", ""])
        for term in entries:
            lines.append(f"- **{term}**: definition for {term}.")
        lines.append("")
    lines.append("## 3. Responsibility matrix")
    lines.append("")
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
        label = labels.get(i, f"principle {i}")
        lines.append(
            f"| P{i} - {label} | universal | harness | doc | project | risk |"
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
# normalize_label
# ---------------------------------------------------------------------------


class TestNormalizeLabel:
    def test_lowercases(self) -> None:
        assert sdpd.normalize_label("Goal And Plan") == "goal and plan"

    def test_replaces_ampersand_with_and(self) -> None:
        assert sdpd.normalize_label("goal & plan") == "goal and plan"

    def test_collapses_whitespace(self) -> None:
        assert sdpd.normalize_label("  goal   and   plan  ") == "goal and plan"

    def test_ampersand_and_text_compare_equal(self) -> None:
        assert sdpd.normalize_label("goal & plan") == sdpd.normalize_label(
            "goal and plan"
        )


# ---------------------------------------------------------------------------
# parse_master_subtitles
# ---------------------------------------------------------------------------


class TestParseMasterSubtitles:
    def test_returns_one_entry_per_section(self) -> None:
        text = _master(3)
        result = sdpd.parse_master_subtitles(text)
        assert result == {1: "principle 1", 2: "principle 2", 3: "principle 3"}

    def test_skips_section_without_subtitle(self) -> None:
        text = _master(3, subtitles={1: "first", 3: "third"})
        result = sdpd.parse_master_subtitles(text)
        assert result == {1: "first", 3: "third"}

    def test_captures_only_text_before_em_dash(self) -> None:
        text = (
            "## 1. Heading\n"
            "*Layer: layer name — description with em-dash.*\n"
        )
        assert sdpd.parse_master_subtitles(text) == {1: "layer name"}

    def test_returns_empty_when_no_sections(self) -> None:
        assert sdpd.parse_master_subtitles("plain text\n") == {}


# ---------------------------------------------------------------------------
# parse_doc_row_labels
# ---------------------------------------------------------------------------


class TestParseDocRowLabels:
    def test_extracts_label_text(self) -> None:
        doc = _doc(matrix_rows=2, wording_count=2)
        section, _ = sdpd.extract_section_3(doc)
        assert sdpd.parse_doc_row_labels(section) == {
            1: "principle 1",
            2: "principle 2",
        }

    def test_overrides_label_per_row(self) -> None:
        doc = _doc(
            matrix_rows=2,
            wording_count=2,
            row_labels={1: "alpha", 2: "beta"},
        )
        section, _ = sdpd.extract_section_3(doc)
        assert sdpd.parse_doc_row_labels(section) == {1: "alpha", 2: "beta"}

    def test_skips_non_p_rows(self) -> None:
        section = [
            "## 3. Matrix",
            "| Layer | Universal |",
            "|---|---|",
            "| P1 - foo | bar |",
        ]
        assert sdpd.parse_doc_row_labels(section) == {1: "foo"}


# ---------------------------------------------------------------------------
# parse_glossary_entries
# ---------------------------------------------------------------------------


class TestParseGlossaryEntries:
    def test_extracts_bolded_terms(self) -> None:
        doc = _doc(matrix_rows=1, wording_count=1, glossary=["alpha", "beta"])
        assert sdpd.parse_glossary_entries(doc) == {"alpha", "beta"}

    def test_returns_empty_when_section_missing(self) -> None:
        doc = _doc(matrix_rows=1, wording_count=1, glossary=[])
        assert sdpd.parse_glossary_entries(doc) == set()

    def test_stops_at_next_heading(self) -> None:
        doc = (
            "### 2.5 Glossary\n"
            "- **alpha**: first.\n"
            "## 3. Matrix\n"
            "- **beta**: should not be counted.\n"
        )
        assert sdpd.parse_glossary_entries(doc) == {"alpha"}


# ---------------------------------------------------------------------------
# verify: label parity
# ---------------------------------------------------------------------------


class TestVerifyLabelParity:
    def test_aligned_labels_pass(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        master = tmp_path / "master.md"
        doc = tmp_path / "doc.md"
        _write(master, _master(3))
        _write(doc, _doc(matrix_rows=3, wording_count=3))
        rc = sdpd.main(["verify", "--master", str(master), "--doc", str(doc)])
        assert rc == 0

    def test_mismatched_label_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        master = tmp_path / "master.md"
        doc = tmp_path / "doc.md"
        _write(master, _master(3))
        _write(
            doc,
            _doc(
                matrix_rows=3,
                wording_count=3,
                row_labels={1: "principle 1", 2: "wrong label", 3: "principle 3"},
            ),
        )
        rc = sdpd.main(["verify", "--master", str(master), "--doc", str(doc)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "P2 row label 'wrong label'" in err
        assert "principle 2" in err

    def test_ampersand_versus_and_passes(self, tmp_path: Path) -> None:
        master = tmp_path / "master.md"
        doc = tmp_path / "doc.md"
        _write(master, _master(1, subtitles={1: "goal & plan"}))
        _write(
            doc,
            _doc(
                matrix_rows=1,
                wording_count=1,
                row_labels={1: "goal and plan"},
            ),
        )
        assert sdpd.main(
            ["verify", "--master", str(master), "--doc", str(doc)]
        ) == 0

    def test_case_difference_passes(self, tmp_path: Path) -> None:
        master = tmp_path / "master.md"
        doc = tmp_path / "doc.md"
        _write(master, _master(1, subtitles={1: "Safety Boundary"}))
        _write(
            doc,
            _doc(
                matrix_rows=1,
                wording_count=1,
                row_labels={1: "safety boundary"},
            ),
        )
        assert sdpd.main(
            ["verify", "--master", str(master), "--doc", str(doc)]
        ) == 0

    def test_missing_subtitle_skips_check(self, tmp_path: Path) -> None:
        master = tmp_path / "master.md"
        doc = tmp_path / "doc.md"
        _write(master, _master(2, subtitles={1: "first"}))
        _write(
            doc,
            _doc(
                matrix_rows=2,
                wording_count=2,
                row_labels={1: "first", 2: "anything"},
            ),
        )
        assert sdpd.main(
            ["verify", "--master", str(master), "--doc", str(doc)]
        ) == 0


# ---------------------------------------------------------------------------
# verify: glossary presence
# ---------------------------------------------------------------------------


class TestVerifyGlossary:
    def test_required_entries_present_passes(self, tmp_path: Path) -> None:
        master = tmp_path / "master.md"
        doc = tmp_path / "doc.md"
        _write(master, _master(6))
        _write(doc, _doc(matrix_rows=6, wording_count=6))
        assert sdpd.main(
            ["verify", "--master", str(master), "--doc", str(doc)]
        ) == 0

    def test_missing_entry_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        master = tmp_path / "master.md"
        doc = tmp_path / "doc.md"
        _write(master, _master(6))
        partial = [
            e for e in sdpd.REQUIRED_GLOSSARY_ENTRIES if e != "defense-in-depth"
        ]
        _write(
            doc,
            _doc(matrix_rows=6, wording_count=6, glossary=partial),
        )
        rc = sdpd.main(["verify", "--master", str(master), "--doc", str(doc)])
        assert rc == 1
        err = capsys.readouterr().err
        assert "defense-in-depth" in err
        assert "section 2.5 glossary is missing required entries" in err

    def test_glossary_heading_absent_fails(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        master = tmp_path / "master.md"
        doc = tmp_path / "doc.md"
        _write(master, _master(6))
        _write(doc, _doc(matrix_rows=6, wording_count=6, glossary=[]))
        rc = sdpd.main(["verify", "--master", str(master), "--doc", str(doc)])
        assert rc == 1
        err = capsys.readouterr().err
        for term in sdpd.REQUIRED_GLOSSARY_ENTRIES:
            assert term in err


# ---------------------------------------------------------------------------
# Repository self-check: the live files must already be in sync.
# ---------------------------------------------------------------------------


class TestRepositorySelfCheck:
    def test_repository_state_is_clean(self) -> None:
        master = REPO_ROOT / ".apm" / "instructions" / "master.instructions.md"
        doc = REPO_ROOT / "docs" / "prd" / "agent-rules-design-philosophy.md"
        assert master.exists()
        assert doc.exists()
        rc = sdpd.main(["verify", "--master", str(master), "--doc", str(doc)])
        assert rc == 0
